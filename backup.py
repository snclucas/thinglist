
import json
import os
from datetime import datetime
from sqlalchemy.exc import SQLAlchemyError

from app import app, db
# Import models, db and app from your project. Adjust the module path if required.
from models import (User, Inventory, UserInventory, Item, InventoryItem,
                    ItemType, Field, FieldTemplate, TemplateField, Location,
                    Tag, Relateditems, ItemField, Notification)


def _row_to_dict(instance, include_relationships=False):
    """Serialize simple columns of a SQLAlchemy model instance to dict."""
    data = {}
    for col in instance.__table__.columns:
        data[col.name] = getattr(instance, col.name)
    if include_relationships:
        # minimal support: common relationship collections as lists of primary keys or values
        if hasattr(instance, "tags"):
            data["tags"] = [t.tag for t in instance.tags]
        if hasattr(instance, "items"):
            data["items"] = [i.id for i in instance.items]
        if hasattr(instance, "fields"):
            data["fields"] = [f.id for f in instance.fields]
    return data


def export_user_data_to_json(user_id: int, file_path: str) -> (bool, str):
    """
    Export user-specific data to `file_path` (JSON).
    Exports item types, fields, templates, locations, inventories (with useraccess levels),
    items (and their tags, images filenames), item fields and relateditems and notifications.
    """
    if user_id is None:
        return False, "user_id cannot be None"
    try:
        with app.app_context():
            # Collect data
            payload = {"meta": {"exported_at": datetime.utcnow().isoformat(), "user_id": user_id}}
            # item types, fields, tags, locations
            payload["item_types"] = [_row_to_dict(it) for it in ItemType.query.filter_by(user_id=user_id).all()]
            payload["fields"] = [_row_to_dict(f) for f in Field.query.filter_by(user_id=user_id).all()]
            payload["templates"] = []
            for t in FieldTemplate.query.filter_by(user_id=user_id).all():
                tdict = _row_to_dict(t)
                # include template fields by id
                tdict["field_ids"] = [f.id for f in t.fields]
                payload["templates"].append(tdict)

            payload["locations"] = [_row_to_dict(l) for l in Location.query.filter_by(user_id=user_id).all()]

            # inventories (all inventories where user has a UserInventory row)
            inventories = []
            stmt = db.session.query(Inventory, UserInventory).join(UserInventory).filter(UserInventory.user_id == user_id)
            for inv, ui in db.session.execute(stmt).all():
                invd = _row_to_dict(inv)
                invd["userinventory"] = {"access_level": ui.access_level, "view": getattr(ui, "view", None)}
                inventories.append(invd)
            payload["inventories"] = inventories

            # tags
            payload["tags"] = [_row_to_dict(t) for t in Tag.query.filter_by(user_id=user_id).all()]

            # items (all items belonging to the user) + inventories linkage, tags, images (filenames)
            items_export = []
            items = Item.query.filter_by(user_id=user_id).all()
            for it in items:
                idata = _row_to_dict(it)
                idata["inventory_ids"] = [inv.id for inv in it.inventories]
                idata["tags"] = [t.tag for t in it.tags]
                idata["images"] = [getattr(img, "image_filename", None) for img in getattr(it, "images", [])]
                # item fields
                idata["custom_fields"] = {f.field_id: f.value for f in ItemField.query.filter_by(item_id=it.id).all()}
                items_export.append(idata)
            payload["items"] = items_export

            # relateditems (only those referencing user's items)
            user_item_ids = [i.id for i in items]
            related = db.session.query(Relateditems).filter(
                (Relateditems.item_id.in_(user_item_ids)) | (Relateditems.related_item_id.in_(user_item_ids))
            ).all()
            payload["related_items"] = [_row_to_dict(r) for r in related]

            # notifications for the user
            #payload["notifications"] = [_row_to_dict(n) for n in Notification.query.filter_by(user_id=user_id).all()]

            # Write file
            os.makedirs(os.path.dirname(file_path) or ".", exist_ok=True)
            with open(file_path, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, default=str, indent=2)

        return True, f"Exported to {file_path}"
    except Exception as e:
        return False, str(e)


def import_user_data_from_json(file_path: str, user_id: int) -> (bool, str):
    """
    Import JSON previously created by `export_user_data_to_json`.
    Recreates ItemTypes, Fields, Templates, Locations, Inventories, Tags, Items, ItemFields, Relateditems and Notifications.
    Uses mapping from exported (old) IDs to newly created DB IDs.
    """
    if user_id is None:
        return False, "user_id cannot be None"
    if not os.path.exists(file_path):
        return False, f"file not found: {file_path}"

    try:
        with app.app_context():
            with open(file_path, "r", encoding="utf-8") as fh:
                payload = json.load(fh)

            # mapping old_id -> new_id
            maps = {
                "item_type": {},
                "field": {},
                "template": {},
                "location": {},
                "inventory": {},
                "tag": {},
                "item": {}
            }

            # ItemTypes
            for it in payload.get("item_types", []):
                # try find existing by name for user
                existing = ItemType.query.filter_by(user_id=user_id, name=it.get("name")).one_or_none()
                if existing:
                    maps["item_type"][it["id"]] = existing.id
                else:
                    new = ItemType(name=it.get("name"), user_id=user_id, slug=it.get("slug"))
                    db.session.add(new)
                    db.session.flush()
                    maps["item_type"][it["id"]] = new.id
            db.session.commit()

            # Fields
            for f in payload.get("fields", []):
                existing = Field.query.filter_by(user_id=user_id, slug=f.get("slug")).one_or_none()
                if existing:
                    maps["field"][f["id"]] = existing.id
                else:
                    new = Field(field=f.get("field"), type=f.get("type"), user_id=user_id, slug=f.get("slug"))
                    db.session.add(new)
                    db.session.flush()
                    maps["field"][f["id"]] = new.id
            db.session.commit()

            # Templates (need fields map)
            for t in payload.get("templates", []):
                existing = FieldTemplate.query.filter_by(user_id=user_id, name=t.get("name")).one_or_none()
                if existing:
                    maps["template"][t["id"]] = existing.id
                else:
                    new = FieldTemplate(name=t.get("name"), user_id=user_id)
                    db.session.add(new)
                    db.session.flush()
                    # attach fields by mapping
                    for old_fid in t.get("field_ids", []):
                        new_field_id = maps["field"].get(old_fid)
                        if new_field_id:
                            fobj = Field.query.get(new_field_id)
                            if fobj and fobj not in new.fields:
                                new.fields.append(fobj)
                    db.session.flush()
                    maps["template"][t["id"]] = new.id
            db.session.commit()

            # Locations
            for l in payload.get("locations", []):
                existing = Location.query.filter_by(user_id=user_id, name=l.get("name")).one_or_none()
                if existing:
                    maps["location"][l["id"]] = existing.id
                else:
                    new = Location(name=l.get("name"), description=l.get("description"), user_id=user_id)
                    db.session.add(new)
                    db.session.flush()
                    maps["location"][l["id"]] = new.id
            db.session.commit()

            # Inventories
            for inv in payload.get("inventories", []):
                # try to find by name + owner
                existing = Inventory.query.filter_by(owner_id=user_id, name=inv.get("name")).one_or_none()
                if existing:
                    maps["inventory"][inv["id"]] = existing.id
                    # ensure user inventory exists
                    ui = UserInventory.query.filter_by(inventory_id=existing.id, user_id=user_id).one_or_none()
                    if not ui:
                        db.session.add(UserInventory(user_id=user_id, inventory_id=existing.id, access_level=0))
                else:
                    new = Inventory(name=inv.get("name"), description=inv.get("description"),
                                    owner_id=user_id, slug=inv.get("slug") or None,
                                    access_level=inv.get("access_level", 0), type=inv.get("type", 1))
                    db.session.add(new)
                    db.session.flush()
                    # create owner row
                    db.session.add(UserInventory(user_id=user_id, inventory_id=new.id, access_level=0))
                    maps["inventory"][inv["id"]] = new.id
            db.session.commit()

            # Tags
            for t in payload.get("tags", []):
                existing = Tag.query.filter_by(user_id=user_id, tag=t.get("tag")).one_or_none()
                if existing:
                    maps["tag"][t["id"]] = existing.id
                else:
                    new = Tag(tag=t.get("tag"), user_id=user_id)
                    db.session.add(new)
                    db.session.flush()
                    maps["tag"][t["id"]] = new.id
            db.session.commit()

            # Items
            for it in payload.get("items", []):
                # create item with mapped item_type and location
                old_item_id = it["id"]
                mapped_type = maps["item_type"].get(it.get("item_type")) or None
                mapped_location = maps["location"].get(it.get("location_id")) or None

                new_item = Item(
                    name=it.get("name"),
                    description=it.get("description"),
                    user_id=user_id,
                    quantity=it.get("quantity") or 1,
                    url=it.get("url"),
                    item_type=mapped_type,
                    location_id=mapped_location,
                    specific_location=it.get("specific_location"),
                )
                db.session.add(new_item)
                db.session.flush()
                maps["item"][old_item_id] = new_item.id

                # tags by tag string (payload stores tag strings)
                for tag_val in it.get("tags", []):
                    # find or create tag
                    ttag = Tag.query.filter_by(user_id=user_id, tag=tag_val).one_or_none()
                    if not ttag:
                        ttag = Tag(tag=tag_val, user_id=user_id)
                        db.session.add(ttag)
                        db.session.flush()
                    if ttag not in new_item.tags:
                        new_item.tags.append(ttag)

                # link to inventories (use inventory mapping)
                for old_inv_id in it.get("inventory_ids", []):
                    new_inv_id = maps["inventory"].get(old_inv_id)
                    if new_inv_id:
                        inv = Inventory.query.get(new_inv_id)
                        if inv and new_item not in inv.items:
                            inv.items.append(new_item)

                # Note: images were exported as filenames only; copying image files not included here.

            db.session.commit()

            # ItemFields (custom_fields)
            for it in payload.get("items", []):
                new_item_id = maps["item"].get(it["id"])
                for old_fid_str, value in (it.get("custom_fields") or {}).items():
                    # exported key might be string; ensure int
                    old_fid = int(old_fid_str)
                    new_field_id = maps["field"].get(old_fid)
                    if new_field_id and new_item_id:
                        instance = ItemField.query.filter_by(item_id=new_item_id, field_id=new_field_id).one_or_none()
                        if instance:
                            instance.value = value
                            instance.show = True
                            instance.user_id = user_id
                        else:
                            new_if = ItemField(item_id=new_item_id, field_id=new_field_id, value=value, show=True, user_id=user_id)
                            db.session.add(new_if)
            db.session.commit()

            # Relateditems
            for r in payload.get("related_items", []):
                old_a = r.get("item_id")
                old_b = r.get("related_item_id")
                new_a = maps["item"].get(old_a)
                new_b = maps["item"].get(old_b)
                if new_a and new_b:
                    # avoid duplicates
                    existing = Relateditems.query.filter_by(item_id=new_a, related_item_id=new_b).one_or_none()
                    if not existing:
                        db.session.add(Relateditems(item_id=new_a, related_item_id=new_b))
            db.session.commit()

            # Notifications
            # for n in payload.get("notifications", []):
            #     # add notification to the user
            #     text = n.get("text") or n.get("message") or ""
            #     from_user = n.get("from_user_username")
            #     notif = Notification(text=text, from_user_username=from_user)
            #     db.session.add(notif)
            #     db.session.flush()
            #     user_obj = User.query.get(user_id)
            #     if user_obj:
            #         user_obj.notifications.append(notif)
            # db.session.commit()

        return True, "Import complete"
    except SQLAlchemyError as e:
        db.session.rollback()
        return False, f"DB error: {str(e)}"
    except Exception as e:
        return False, str(e)

if __name__ == '__main__':
    # Example usage
    success, message = export_user_data_to_json(user_id=1, file_path="user_1_export.json")
    print("Export:", success, message)

    #success, message = import_user_data_from_json(file_path="user_1_export.json", user_id=1)
    #print("Import:", success, message)