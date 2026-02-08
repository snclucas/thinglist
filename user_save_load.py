import hashlib
import hmac
import json
import os
from typing import Dict

import bleach
from flask import current_app
from sqlalchemy.ext.declarative import DeclarativeMeta

from app import app
from routes.items_loader import process_images, process_field_sets
from services.field_service import FieldService
from services.field_template_service import FieldTemplateService
from services.inventory_service import InventoryService
from services.item_service import ItemService
from services.item_type_service import ItemTypeService
from services.location_service import LocationService

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

    for inventory_ in json_data:
        inventory_data = inventory_.get("inventory", None)
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

        else:
            load_log += f"<br>Inventory {found_inv.name} found...<br>"
            found_inv = {
                "id": found_inv.id,
                "name": found_inv.name,
                "description": found_inv.description,
                "slug": found_inv.slug,
                "type": found_inv.type,
                "token": found_inv.inventory_token,
                "access_level": found_inv.access_level,
                "owner_id": found_inv.owner_id
            }

        # lets sort the field template out
        load_log = process_field_sets(inventory_data, current_user, found_inv, load_log)


        # If we are importing into a specific inventory, only import into that inventory
        if inventory_slug_from_form != "all":
            if inventory_slug_ != inventory_slug_from_form:
                continue

        inventory_id = found_inv["id"]

        item_count = 0
        if "items" in inventory_data:
            for item in inventory_data["items"]:
                item_token = bleach.clean(str(item.get("item_token")))
                if not overwrite_or_not:
                    item_token = None
                item_name = bleach.clean(item.get("name"))
                item_description = bleach.clean(item.get("description"))
                item_type_slug = item.get("type_slug", "none")
                if item_type_slug is not None:
                    item_type_slug = bleach.clean(item_type_slug)
                item_quantity = int(bleach.clean(str(item.get("quantity"))))
                item_tags = [bleach.clean(str(x)) for x in item.get("tags")]
                item_location = bleach.clean(item.get("location"))
                item_specific_location = bleach.clean(item.get("specific_location"))

                item_type_name = None
                # add item types
                if item_type_slug is not None and item_type_slug != 'none':
                    status, msg, added_item_type = ItemTypeService.get_or_add_new_user_item_type(name=item_type_slug,
                                                                                 user_id=current_user.id)
                    item_type_name = added_item_type["name"]

                location_id = None
                if item_location is not None:
                    if item_location.strip() != "":
                        location_data_ = LocationService.get_or_add_new_location(location_name=item_location,
                                                                 location_description=item_location,
                                                                 to_user_id=current_user.id)

                        if location_data_["status"] and location_data_["new"]:
                            load_log += f"&nbsp;&nbsp;&nbsp;&nbsp;... created location {item_location}.<br>"

                        if not location_data_["status"]:
                            load_log += f"&nbsp;&nbsp;&nbsp;&nbsp;... could not create location {item_location}.<br>"

                        location_id = location_data_.get("id")

                tag_array = item_tags

                if isinstance(tag_array, list):
                    for t in range(len(tag_array)):
                        tag_array[t] = tag_array[t].strip()
                        tag_array[t] = tag_array[t].replace(" ", "@#$")

                custom_fields = item.get("custom_fields", {})

                if overwrite_or_not:
                    potential_item = ItemService.get_item_by_token(item_token=item_token, user_id=current_user.id)
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
                                                          custom_fields=custom_fields, item_token=item_token)
                        item_count += 1
                    else:
                        new_item_data = {
                            "id": potential_item.id,
                            "name": item_name,
                            "description": item_description,
                            "item_type": added_item_type["id"],
                            "item_quantity": item_quantity,
                            "item_location": item_location,
                            "item_specific_location": item_specific_location,
                            "item_tags": item_tags
                        }
                        new_item_ = ItemService.update_item_by_token(item_data=new_item_data, item_token=potential_item.item_token,
                                                          user=current_user)
                        load_log += f"&nbsp;&nbsp;&nbsp;&nbsp;... item {item_name} found and updated if different.<br>"
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

                if new_item_["status"] != __ERROR__:
                    # save images
                    _new_item_id = new_item_["item"]["id"]
                    image_base_path = app.config['USER_IMAGES_BASE_PATH']
                    image_secret_key = app.config['IMAGE_SECRET_KEY'].encode('utf-8')
                    process_images(item, new_item_, _new_item_id, current_user,
                                   app.root_path, image_base_path, image_secret_key)

                if new_item_["status"] == "error":
                    return "Sorry, there was an error importing these things."


        load_log += f"&nbsp;&nbsp;&nbsp;&nbsp;... imported {item_count} items into inventory {inventory_slug_}.<br>"




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

    def proc_img(current_user_id, item_, tmp_json):
        item_images = []
        # save images
        for img in item_.images:
            tmp_img_dict = {"is_main": False}
            img_path = os.path.join(app.config['USER_IMAGES_BASE_PATH'],
                                    current_user_id,
                                    img.image_filename)

            import base64

            with open(img_path, "rb") as image_file:
                encoded_string = base64.b64encode(image_file.read())
                raw = encoded_string.decode("utf-8")
                tmp_img_dict["image_data"] = raw

            raw = raw.encode("utf-8")
            key = app.config['IMAGE_SECRET_KEY'].encode('utf-8')
            hashed = hmac.new(key, raw, hashlib.sha1)
            img_hmac_hash = base64.encodebytes(hashed.digest()).decode('utf-8')
            tmp_img_dict["image_hash"] = img_hmac_hash

            item_images.append(tmp_img_dict)
        tmp_json["images"] = item_images

    uinv_inv_list = []

    sdsd = InventoryService.get_user_inventories2(current_user_id=current_user.id,
                                           requesting_user_id=current_user.id)

    ddd = InventoryService.get_serialized_user_inventories(inventories=sdsd)

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

        entire_json["fields"] = serialise_field_data()

        # temp remove first item from list
        uinv_inv_list = uinv_inv_list[1:] if len(uinv_inv_list) > 1 else uinv_inv_list

        inventory_data_ = []
        # loop over inventories
        for inventory_, user_inventory_ in uinv_inv_list:
            try:
                field_template_ = None
                if inventory_ is None:
                    return None, None, None
                else:
                    inventory_id = inventory_.id

                    field_template_id_ = inventory_.field_template

                    if field_template_id_ is not None:
                        field_template_ = FieldTemplateService.find_template_by_id(template_id=field_template_id_)

                data_dict, item_id_list = ItemService.find_items_query(
                    requested_username=current_user.username,
                    logged_in_user=current_user,
                    inventory_id=inventory_id,
                    request_params=request_params
                )

                newdd = ItemService.get_item_custom_field_data(user_id=current_user.id, item_list=item_id_list)

                field_set = [f.field for f in field_template_.fields]

                headers_ = ["id", "name", "description", "tags", "type",
                            "location", "specific location", "quantity", "url"]
                headers_.extend(sorted(field_set))

                json_output = {
                    "inventory": {
                        "ident": inventory_.ident,
                        "inventory_token": inventory_.inventory_token,
                        "name": inventory_.name,
                        "description": inventory_.description,
                        "slug": inventory_.slug,
                        #"custom_field_set": wewe,
                        "standard_fields": headers_,
                        "field_set": {
                            "name": field_template_.name,
                            "ident": field_template_.ident,
                            "fields": field_set,
                        },
                        "items": []
                    }
                }

                # process each item, isolating per-item errors
                for row in data_dict:
                    try:
                        item_ = row["item"]
                        item_custom_fields_ = ItemService.get_item_fields(item_id=item_.id)

                        related_items_ = ItemService.get_related_items(item_id=item_.id)
                        related_items_list = []
                        if related_items_:
                            for _r, related_item in related_items_:
                                if getattr(related_item, "item_token", None):
                                    related_items_list.append(related_item.item_token)

                        ddd = {}
                        for field_data in item_custom_fields_:
                            field_ = field_data[0]
                            item_field_ = field_data[1]
                            ddd[field_.slug] = item_field_.value

                        tmp_json = {
                            "ident": item_.ident,
                            "item_token": item_.item_token,
                            "name": item_.name,
                            "slug": item_.slug,
                            "description": item_.description,
                            "tags": [x.tag.replace("@#$", " ") for x in item_.tags],
                            "type": row.get("types"),
                            "location": row.get("location"),
                            "specific_location": item_.specific_location,
                            "quantity": item_.quantity,
                            "is_link": row.get("item_is_link"),
                            "custom_fields": ddd,
                            "related_items": related_items_list
                        }

                        current_user_id = str(current_user.id)
                        # proc_img already logs/raises; catch issues locally
                        try:
                            proc_img(current_user_id, item_, tmp_json)
                        except Exception as e:
                            current_app.logger.error("Error exporting images for item %s: %s", getattr(item_, "id", "?"), str(e))
                            # continue without images

                        json_output["inventory"]["items"].append(tmp_json)
                    except Exception as e:
                        current_app.logger.error("Error processing item for export: %s", str(e))
                        continue

                entire_json.append(json_output)

            except Exception as e:
                current_app.logger.error("Error exporting inventory %s: %s", inventory_.slug, str(e))
                continue

        # produce JSON text; use the AlchemyEncoder for SQLAlchemy objects
        try:
            json_text = json.dumps(entire_json, cls=AlchemyEncoder, ensure_ascii=False)
        except Exception as e:
            current_app.logger.error("Error serializing export JSON: %s", str(e))
            json_text = "[]"

        return True, json_text

    except Exception:
        current_app.logger.exception("Unhandled error during items export")
        return False, {}
