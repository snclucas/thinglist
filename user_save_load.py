import json
import tempfile
from datetime import datetime

import bleach
from flask import current_app
from sqlalchemy.ext.declarative import DeclarativeMeta

from app import app, db
from routes.items_loader import process_images, process_field_sets
from services.field_service import FieldService
from services.field_template_service import FieldTemplateService
from services.inventory_service import InventoryService
from services.item_service import ItemService
from services.item_type_service import ItemTypeService
from services.location_service import LocationService
from models import Item, User

from site_globals import __ERROR__, __DEFAULT__, __ALL__


class AlchemyEncoder(json.JSONEncoder):

    def default(self, obj):
        if isinstance(obj.__class__, DeclarativeMeta):
            # an SQLAlchemy class
            fields = {}
            for field in [x for x in dir(obj) if not x.startswith('_') and x != 'metadata']:
                data = obj.__getattribute__(field)
                try:
                    json.dumps(data)  # this will fail on non-encodable values, like other classes
                    fields[field] = data
                except TypeError:
                    fields[field] = None
            # a json-encodable dict
            return fields

        return json.JSONEncoder.default(self, obj)


def items_load(json_data, current_user, overwrite_or_not, inventory_slug_from_form):
    load_log = ""
    username = current_user.username
    # report collects structured counts of what was restored or skipped
    report = {
        "inventories_created": [],
        "inventories_found": [],
        "templates_created": [],
        "templates_failed": [],
        "locations_created": [],
        "locations_failed": [],
        "items_created": [],
        "items_failed": [],
        "items_updated": [],
        "related_links_created": 0,
        "user_inventory_added": [],
        "user_inventory_skipped": [],
        "images_saved": 0,
        "images_failed": 0
    }

    # normalize incoming export formats: new exports are { ..., 'lists': [ inv_dict, ... ] }
    if isinstance(json_data, dict):
        inventories_iter = json_data.get('lists') or json_data.get('inventories') or []
    else:
        inventories_iter = json_data

    for inventory_ in inventories_iter:
        # support an envelope {'inventory': inv_dict} or the direct inv_dict
        if isinstance(inventory_, dict) and 'inventory' in inventory_:
            inventory_data = inventory_.get('inventory')
        else:
            inventory_data = inventory_
        if inventory_data is None:
            break

        inventory_slug_ = inventory_data.get("slug", None)
        if inventory_slug_ is None:
            continue

        inventory_token_ = inventory_data.get("inventory_token", None)
        if inventory_token_ is None:
            continue

        inventory_slug_ = bleach.clean(inventory_slug_)
        inventory_token_ = bleach.clean(inventory_token_)

        if __DEFAULT__ in inventory_slug_:
            found_inv = InventoryService.get_user_default_inventory(user_id=current_user.id)
            if not found_inv:
                load_log += f"<br>Default inventory not found for user {username}. Creating it...<br>"
                found_inv, status, msg = InventoryService.add_default_user_list(user_id=current_user.id)
                if not status:
                    load_log += f"Error creating default inventory for user {username}.<br>"
                    continue
        else:
            # look for the inventory by slug (was by slub before)
            found_inv, found_userinv = InventoryService.find_inventory_by_token(inventory_token=inventory_token_,
                                                              inventory_owner_id=current_user.id,
                                                              viewing_user_id=current_user.id)

        if found_inv is None:
            load_log += f"<br>Inventory {inventory_token_} not found. Creating it...<br>"
            inventory_name = bleach.clean(inventory_data.get("name"))
            inventory_description = bleach.clean(inventory_data.get("description"))
            inventory_type = int(bleach.clean(str(inventory_data.get("type", 1))))
            inventory_access_level = int(bleach.clean(str(inventory_data.get("access_level", 1))))

            found_inv, status, msg = InventoryService.add_user_list(name=inventory_name,
                                                    description=inventory_description,
                                                    inventory_type=inventory_type,
                                                    slug=inventory_slug_,
                                                    access_level=inventory_access_level,
                                                    user_id=current_user.id,
                                                    token=inventory_token_)
            if not status:
                load_log += f"Error creating inventory {inventory_slug_}.<br>"
                continue
            # after creation, re-fetch the Inventory model by token to obtain its numeric id
            inv_model, _ = InventoryService.find_inventory_by_token(inventory_token=inventory_token_,
                                                                    inventory_owner_id=current_user.id,
                                                                    viewing_user_id=current_user.id)
            if inv_model is None:
                load_log += f"Error finding newly created inventory {inventory_slug_}.<br>"
                continue
            found_inv = inv_model
            # record inventory created
            try:
                report["inventories_created"].append({"slug": inventory_slug_, "token": inventory_token_})
            except Exception:
                pass
        else:
            load_log += f"<br>Inventory {found_inv.name} found...<br>"
            # keep found_inv as the Inventory model instance so we can resolve idents internally
            try:
                report["inventories_found"].append({"slug": found_inv.slug, "ident": getattr(found_inv, 'ident', None)})
            except Exception:
                pass

            # update existing inventory metadata (name/description) from export when possible
            try:
                exported_name = bleach.clean(str(inventory_data.get('name') or ''))
                exported_description = bleach.clean(str(inventory_data.get('description') or ''))
                updated = False
                if exported_name and getattr(found_inv, 'name', None) != exported_name:
                    found_inv.name = exported_name
                    updated = True
                if exported_description and getattr(found_inv, 'description', None) != exported_description:
                    found_inv.description = exported_description
                    updated = True
                if updated:
                    try:
                        db.session.commit()
                        report.setdefault('inventories_updated', []).append({"slug": found_inv.slug, "ident": getattr(found_inv, 'ident', None)})
                    except Exception:
                        try:
                            db.session.rollback()
                        except Exception:
                            pass
            except Exception:
                pass

        # lets sort the field template out - pass numeric inventory_id so process can save mappings
        inventory_id = getattr(found_inv, 'id', None)
        load_log = process_field_sets(inventory_data, current_user, inventory_id, load_log)


        # If we are importing into a specific inventory, only import into that inventory
        if inventory_slug_from_form != "all":
            if inventory_slug_ != inventory_slug_from_form:
                continue

        # ensure we have a numeric inventory_id for item creation
        if not isinstance(inventory_id, int):
            inventory_id = getattr(found_inv, 'id', None)
        if inventory_id is None:
            load_log += f"Could not resolve inventory id for {inventory_slug_}. Skipping.<br>"
            continue

        item_count = 0
        # mapping from exported identifiers/tokens to local DB item ids
        created_item_map = {}
        items_list = inventory_data.get("items", []) or []
        if items_list:
            for item in items_list:
                item_ident = bleach.clean(str(item.get("ident") or ""))
                # normalize empty tokens to None so we don't try to insert empty string into DB unique column
                if not item_ident:
                    item_ident = None
                if not overwrite_or_not:
                    item_ident = None
                item_name = bleach.clean(str(item.get("name") or ""))
                item_description = bleach.clean(str(item.get("description") or ""))
                item_type_slug = item.get("type_slug", "none")
                if item_type_slug is not None:
                    item_type_slug = bleach.clean(str(item_type_slug))
                try:
                    item_quantity = int(bleach.clean(str(item.get("quantity") or "0")))
                except Exception:
                    item_quantity = 1
                item_tags = [bleach.clean(str(x)) for x in (item.get("tags") or [])]
                item_location_raw = item.get("location")
                if isinstance(item_location_raw, dict):
                    item_location = bleach.clean(str(item_location_raw.get('name') or ''))
                else:
                    item_location = bleach.clean(str(item_location_raw or ""))
                item_specific_location = bleach.clean(str(item.get("specific_location") or ""))

                item_type_name = None
                # add item types
                if item_type_slug is not None and item_type_slug != 'none':
                    status, msg, added_item_type = ItemTypeService.get_or_add_new_user_item_type(name=item_type_slug,
                                                                                                 user_id=current_user.id)
                    if status and added_item_type:
                        item_type_name = added_item_type.get("name")

                location_id = None
                if item_location is not None and item_location.strip() != "":
                    location_data_ = LocationService.get_or_add_new_location(location_name=item_location,
                                                                              location_description=item_location,
                                                                              to_user_id=current_user.id)

                    if location_data_.get("status") and location_data_.get("new"):
                        load_log += f"&nbsp;&nbsp;&nbsp;&nbsp;... created location {item_location}.<br>"

                    if not location_data_.get("status"):
                        load_log += f"&nbsp;&nbsp;&nbsp;&nbsp;... could not create location {item_location}.<br>"

                    location_id = location_data_.get("id")

                tag_array = item_tags
                if isinstance(tag_array, list):
                    for t in range(len(tag_array)):
                        tag_array[t] = tag_array[t].strip()
                        tag_array[t] = tag_array[t].replace(" ", "@#$")

                custom_fields = item.get("custom_fields", {})

                if overwrite_or_not:
                    potential_item = ItemService.get_item_by_ident(item_ident=item_ident, user_id=current_user.id)
                    if potential_item is None:
                        new_item_ = InventoryService.add_item_to_inventory(item_name=item_name,
                                                                          item_desc=item_description,
                                                                          item_type_name_or_id=item_type_name,
                                                                          item_quantity=item_quantity,
                                                                          item_tags=tag_array,
                                                                          inventory_id=inventory_id,
                                                                          item_location_id=location_id,
                                                                          item_specific_location=item_specific_location,
                                                                          user_id=current_user.id,
                                                                          custom_fields=custom_fields, item_ident=item_ident)
                        item_count += 1
                        try:
                            report["items_created"].append({"name": item_name, "item_ident": item_ident})
                        except Exception:
                            pass
                    else:
                        new_item_data = {
                            "id": potential_item.id,
                            "name": item_name,
                            "description": item_description,
                            "item_type": added_item_type["id"] if added_item_type else None,
                            "item_quantity": item_quantity,
                            "item_location": location_id,
                            "item_specific_location": item_specific_location,
                            "item_tags": item_tags
                        }
                        new_item_ = ItemService.update_item_by_ident(item_data=new_item_data, item_ident=potential_item.ident,
                                                                     user=current_user)
                        load_log += f"&nbsp;&nbsp;&nbsp;&nbsp;... item {item_name} found and updated if different.<br>"
                        try:
                            report["items_updated"].append({"name": item_name, "item_ident": item_ident})
                        except Exception:
                            pass
                else:
                    new_item_ = InventoryService.add_item_to_inventory(item_name=item_name,
                                                                       item_desc=item_description,
                                                                       item_type_name_or_id=item_type_name, item_quantity=item_quantity,
                                                                       item_tags=tag_array, inventory_id=inventory_id,
                                                                       item_location_id=location_id,
                                                                       item_specific_location=item_specific_location,
                                                                       user_id=current_user.id,
                                                                       custom_fields=custom_fields)
                    item_count += 1
                    try:
                        report["items_created"].append({"name": item_name, "item_ident": item_ident})
                    except Exception:
                        pass

                # record mapping from exported identifiers to the created/updated DB id
                try:
                    created_db_id = new_item_["item"]["id"]
                    db_item = db.session.get(Item, created_db_id)
                    if db_item is not None:
                        if getattr(db_item, 'ident', None):
                            created_item_map[str(db_item.ident)] = db_item.id
                        if getattr(db_item, 'item_token', None):
                            created_item_map[str(db_item.item_token)] = db_item.id
                except Exception:
                    pass

                if new_item_["status"] != __ERROR__:
                    # save images
                    _new_item_id = new_item_["item"]["id"]
                    image_base_path = app.config['USER_IMAGES_BASE_PATH']
                    image_secret_key = app.config['IMAGE_SECRET_KEY'].encode('utf-8')
                    # process_images will skip images when image_data is not present
                    img_ok, img_msg, img_counts = process_images(item, new_item_, _new_item_id, current_user,
                                   app.root_path, image_base_path, image_secret_key)
                    if img_counts:
                        report["images_saved"] += img_counts.get("saved", 0)
                        report["images_failed"] += img_counts.get("failed", 0)

                if new_item_["status"] == "error":
                    # record the failure, log details, but continue with other items
                    try:
                        err_msg = new_item_.get('msg') if isinstance(new_item_, dict) else str(new_item_)
                    except Exception:
                        err_msg = "unknown error"
                    report["items_failed"].append({"name": item_name, "item_ident": item_ident, "msg": err_msg})
                    try:
                        current_app.logger.error(f"Import item failed for user {current_user.username}: {err_msg} | item: {item}")
                    except Exception:
                        try:
                            app.logger.error(f"Import item failed: {err_msg}")
                        except Exception:
                            pass
                    # skip further processing for this failed item
                    continue

            # after all items are created, restore related_items links
            try:
                item_service = ItemService()
                for item in items_list:
                    # find the local id of this item (prefer token then ident)
                    exported_token = item.get('item_token')
                    exported_ident = item.get('ident')
                    main_id = None
                    if exported_token and str(exported_token) in created_item_map:
                        main_id = created_item_map[str(exported_token)]
                    elif exported_ident and str(exported_ident) in created_item_map:
                        main_id = created_item_map[str(exported_ident)]

                    if main_id is None:
                        continue

                    for rel in item.get('related_items', []) or []:
                        rel_token = rel.get('item_token')
                        rel_ident = rel.get('ident')
                        rel_id = None
                        if rel_token and str(rel_token) in created_item_map:
                            rel_id = created_item_map[str(rel_token)]
                        elif rel_ident and str(rel_ident) in created_item_map:
                            rel_id = created_item_map[str(rel_ident)]

                        if rel_id is None or rel_id == main_id:
                            continue

                        try:
                            # create bidirectional relation
                            item_service.relate_items(current_user.id, main_id, rel_id)
                            report["related_links_created"] += 1
                        except Exception:
                            # ignore duplicate/constraint errors
                            pass
            except Exception:
                pass

            # restore UserInventory (sharing) entries for this inventory
            try:
                for ui in inventory_data.get('user_inventory', []) or []:
                    uname = ui.get('username')
                    alevel = ui.get('access_level')
                    if not uname:
                        continue
                    # skip owner
                    if uname == current_user.username:
                        continue
                    user_row = User.query.filter_by(username=uname).one_or_none()
                    if user_row is not None:
                        try:
                            InventoryService.add_user_to_inventory(inventory_id=inventory_id,
                                                                    current_user_id=current_user.id,
                                                                    user_to_add_username=uname,
                                                                    added_user_access_level=alevel)
                            report["user_inventory_added"].append({"username": uname, "access_level": alevel})
                        except Exception:
                            report["user_inventory_skipped"].append({"username": uname, "access_level": alevel})
                            pass
            except Exception:
                pass

        load_log += f"&nbsp;&nbsp;&nbsp;&nbsp;... imported {item_count} items into inventory {inventory_slug_}.<br>"

    # write report to temp file
    try:
        tmpf = tempfile.NamedTemporaryFile(delete=False, suffix='.import_report.json')
        tmpf.close()
        with open(tmpf.name, 'w', encoding='utf-8') as rf:
            json.dump(report, rf, ensure_ascii=False, indent=2)
        # also append path to log
        load_log += f"\nImport report written to: {tmpf.name}\n"
        return load_log, tmpf.name
    except Exception:
        return load_log, None


def items_save(inventory_slug, current_user, request_params):
    entire_json = {}

    def serialise_field_data() -> list:
        try:
            _field_data = []
            _user_templates = FieldTemplateService.get_user_templates(user_id=current_user.id)
            # save user_templates to the json
            for ut in _user_templates:
                _field_data.append(
                    {
                        "ident": ut.ident,
                        "name": ut.name,
                        "fields": [{"ident": f.ident, "name": f.field, "slug": f.slug, "type": f.type} for f in ut.fields]
                    }
                )
            return _field_data

        except Exception as e:
            current_app.logger.error("Error fetching user templates: %s", str(e))
            return []

    include_images = bool(request_params.get('include_images', True)) if isinstance(request_params, dict) else True
    sdsd = InventoryService.get_user_inventories2(current_user_id=current_user.id,
                                           requesting_user_id=current_user.id)

    ddd = InventoryService.get_serialized_user_inventories(inventories=sdsd, include_images=include_images)

    try:
        if inventory_slug == __ALL__:
            try:
                uinv_inv_list = InventoryService.find_all_user_inventories(user_id=current_user.id)
            except Exception as e:
                current_app.logger.error("Error fetching user inventories: %s", str(e))
        else:
            inventory_, user_inventory_ = InventoryService.find_inventory_by_slug(inventory_slug=inventory_slug)
            uinv_inv_list = [(inventory_, user_inventory_)]



        # fetch user-level data defensively
        try:
            _user_fields = FieldService.get_all_user_fields(user_id=current_user.id)
        except Exception as e:
            current_app.logger.error("Error fetching user fields: %s", str(e))
            _user_fields = []

        entire_json["field_templates"] = serialise_field_data()


        # top-level metadata
        entire_json["metadata"] = {
            "format_version": 1,
            "exported_at": datetime.utcnow().isoformat() + 'Z',
            "source_user": current_user.username,
            "include_images": include_images
        }


        def serialise_locations(location_data):
            _user_locations = []
            for ul in location_data:
                _user_locations.append(
                    {
                        "ident": ul.ident,
                        "name": ul.name,
                        "description": ul.description,
                    }
                )
            return _user_locations


        user_locations = LocationService.get_all_user_locations(user_id=current_user.id)
        entire_json["locations"] = serialise_locations(user_locations)

        entire_json["lists"] = ddd



        # produce JSON text; use the AlchemyEncoder for SQLAlchemy objects
        try:
            json_text = json.dumps(entire_json, cls=AlchemyEncoder, ensure_ascii=False)
        except Exception as e:
            current_app.logger.error("Error serializing export JSON: %s", str(e))
            json_text = "[]"

        return True, json_text

    except Exception as e:
        current_app.logger.exception("Unhandled error during items export")
        return False, {}
