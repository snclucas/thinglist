# python
import json
import os
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app import app, db
from models import (User, Inventory, UserInventory, Item,
                    ItemType, Field, FieldTemplate, TemplateField, Location,
                    Tag, Relateditems, ItemField, Notification)


def get_ident_or_id(obj):
    """Return `ident` if present/non-empty on a model object, else return its numeric id, else None."""
    if obj is None:
        return None
    # prefer ident string if present and truthy
    if hasattr(obj, "ident") and getattr(obj, "ident"):
        return getattr(obj, "ident")
    # fallback to numeric id if present
    if hasattr(obj, "id"):
        return getattr(obj, "id")
    return None


def safe_map_lookup(m, key):
    """
    Lookup key in map `m` trying direct key, int(key) and str(key) variants.
    Returns found value or None.
    """
    if key is None:
        return None
    if key in m:
        return m[key]
    try:
        ik = int(key)
        if ik in m:
            return m[ik]
    except Exception:
        pass
    sk = str(key)
    if sk in m:
        return m[sk]
    return None


def _row_to_dict(instance, include_relationships=False):
    """Serialize simple columns of a SQLAlchemy model instance to dict.
    Do not expose DB `id` when `ident` is available on the instance.
    """
    data = {}
    # decide whether we have an ident
    has_ident = hasattr(instance, "ident") and getattr(instance, "ident")
    for col in instance.__table__.columns:
        if col.name == "id" and has_ident:
            # skip DB id if ident exists
            continue
        data[col.name] = getattr(instance, col.name)
    # add ident explicitly if present and not already included
    if hasattr(instance, "ident") and getattr(instance, "ident"):
        data["ident"] = getattr(instance, "ident")
    if include_relationships:
        if hasattr(instance, "tags"):
            data["tags"] = [t.tag for t in instance.tags]
        if hasattr(instance, "items"):
            data["items"] = [get_ident_or_id(i) for i in instance.items]
        if hasattr(instance, "fields"):
            data["fields"] = [get_ident_or_id(f) for f in instance.fields]
    return data


def export_user_data_to_json(user_id: int, file_path: str) -> (bool, str):
    if user_id is None:
        return False, "user_id cannot be None"
    try:
        with app.app_context():
            payload = {"meta": {"exported_at": datetime.utcnow().isoformat(), "user_id": user_id}}

            payload["item_types"] = [_row_to_dict(it) for it in ItemType.query.filter_by(user_id=user_id).all()]
            payload["fields"] = [_row_to_dict(f) for f in Field.query.filter_by(user_id=user_id).all()]

            payload["templates"] = []
            for t in FieldTemplate.query.filter_by(user_id=user_id).all():
                tdict = _row_to_dict(t)
                # include template fields by ident or id
                tdict["field_idents"] = [get_ident_or_id(f) for f in t.fields]
                payload["templates"].append(tdict)

            payload["locations"] = [_row_to_dict(l) for l in Location.query.filter_by(user_id=user_id).all()]

            # inventories (all inventories where user has a UserInventory row)
            inventories = []
            stmt = select(Inventory, UserInventory).join(UserInventory).where(UserInventory.user_id == user_id)
            for inv, ui in db.session.execute(stmt).all():
                invd = _row_to_dict(inv)
                invd["ident"] = get_ident_or_id(inv)
                invd["userinventory"] = {"access_level": ui.access_level, "view": getattr(ui, "view", None)}
                inventories.append(invd)
            payload["inventories"] = inventories

            payload["tags"] = [_row_to_dict(t) for t in Tag.query.filter_by(user_id=user_id).all()]

            # items (all items belonging to the user) + inventories linkage, tags, images (filenames)
            items_export = []
            items = Item.query.filter_by(user_id=user_id).all()
            for it in items:
                idata = _row_to_dict(it)
                # export item_type by ident/id (use Session.get)
                type_obj = db.session.get(ItemType, it.item_type) if getattr(it, "item_type", None) else None
                idata["item_type"] = get_ident_or_id(type_obj)
                # location by ident/id (use Session.get)
                loc_obj = db.session.get(Location, it.location_id) if getattr(it, "location_id", None) else None
                idata["location"] = get_ident_or_id(loc_obj)
                idata["inventory_idents"] = [get_ident_or_id(inv) for inv in it.inventories]
                idata["tags"] = [t.tag for t in it.tags]
                idata["images"] = [getattr(img, "image_filename", None) for img in getattr(it, "images", [])]
                # item fields: use field ident if available as key
                custom = {}
                for f in ItemField.query.filter_by(item_id=it.id).all():
                    field_obj = db.session.get(Field, f.field_id)
                    key = get_ident_or_id(field_obj) or f.field_id
                    custom[str(key)] = f.value
                idata["custom_fields"] = custom
                items_export.append(idata)
            payload["items"] = items_export

            # relateditems (only those referencing user's items) - export by item idents/idents
            user_item_ids = [i.id for i in items]
            related_q = db.session.query(Relateditems).filter(
                (Relateditems.item_id.in_(user_item_ids)) | (Relateditems.related_item_id.in_(user_item_ids))
            ).all()
            related_export = []
            for r in related_q:
                a = db.session.get(Item, r.item_id)
                b = db.session.get(Item, r.related_item_id)
                related_export.append({
                    "item_ref": get_ident_or_id(a),
                    "related_item_ref": get_ident_or_id(b),
                    "relation_type": getattr(r, "relation_type", None)
                })
            payload["related_items"] = related_export

            # notifications for the user (kept commented, same approach applies)

            os.makedirs(os.path.dirname(file_path) or ".", exist_ok=True)
            with open(file_path, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, default=str, indent=2)

        return True, f"Exported to {file_path}"
    except Exception as e:
        return False, str(e)


def import_user_data_from_json(file_path: str, user_id: int) -> (bool, str):
    if user_id is None:
        return False, "user_id cannot be None"
    if not os.path.exists(file_path):
        return False, f"file not found: {file_path}"

    try:
        with app.app_context():
            with open(file_path, "r", encoding="utf-8") as fh:
                payload = json.load(fh)

            # mapping exported_key (ident or id) -> new DB id
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
                exported_key = it.get("ident") if it.get("ident") is not None else it.get("id")
                existing = None
                if it.get("ident"):
                    existing = ItemType.query.filter_by(user_id=user_id, ident=it.get("ident")).one_or_none()
                if not existing:
                    # fallback by name
                    existing = ItemType.query.filter_by(user_id=user_id, name=it.get("name")).one_or_none()
                if existing:
                    maps["item_type"][exported_key] = existing.id
                else:
                    new = ItemType(name=it.get("name"), user_id=user_id, slug=it.get("slug"))
                    if it.get("ident"):
                        setattr(new, "ident", it.get("ident"))
                    db.session.add(new)
                    db.session.flush()
                    maps["item_type"][exported_key] = new.id
            db.session.commit()

            # Fields
            for f in payload.get("fields", []):
                exported_key = f.get("ident") if f.get("ident") is not None else f.get("id")
                existing = None
                if f.get("ident"):
                    existing = Field.query.filter_by(user_id=user_id, ident=f.get("ident")).one_or_none()
                if not existing:
                    existing = Field.query.filter_by(user_id=user_id, slug=f.get("slug")).one_or_none()
                if existing:
                    maps["field"][exported_key] = existing.id
                else:
                    new = Field(field=f.get("field"), type=f.get("type"), user_id=user_id, slug=f.get("slug"))
                    if f.get("ident"):
                        setattr(new, "ident", f.get("ident"))
                    db.session.add(new)
                    db.session.flush()
                    maps["field"][exported_key] = new.id
            db.session.commit()

            # Templates (need fields map)
            for t in payload.get("templates", []):
                exported_key = t.get("ident") if t.get("ident") is not None else t.get("id")
                existing = None
                if t.get("ident"):
                    existing = FieldTemplate.query.filter_by(user_id=user_id, ident=t.get("ident")).one_or_none()
                if not existing:
                    existing = FieldTemplate.query.filter_by(user_id=user_id, name=t.get("name")).one_or_none()
                if existing:
                    maps["template"][exported_key] = existing.id
                else:
                    new = FieldTemplate(name=t.get("name"), user_id=user_id)
                    if t.get("ident"):
                        setattr(new, "ident", t.get("ident"))
                    db.session.add(new)
                    db.session.flush()
                    # attach fields by mapping (field_idents)
                    for old_fid in t.get("field_idents", []):
                        new_field_id = safe_map_lookup(maps["field"], old_fid)
                        if new_field_id:
                            fobj = db.session.get(Field, new_field_id)
                            if fobj and fobj not in new.fields:
                                new.fields.append(fobj)
                    db.session.flush()
                    maps["template"][exported_key] = new.id
            db.session.commit()

            # Locations
            for l in payload.get("locations", []):
                exported_key = l.get("ident") if l.get("ident") is not None else l.get("id")
                existing = None
                if l.get("ident"):
                    existing = Location.query.filter_by(user_id=user_id, ident=l.get("ident")).one_or_none()
                if not existing:
                    existing = Location.query.filter_by(user_id=user_id, name=l.get("name")).one_or_none()
                if existing:
                    maps["location"][exported_key] = existing.id
                else:
                    new = Location(name=l.get("name"), description=l.get("description"), user_id=user_id)
                    if l.get("ident"):
                        setattr(new, "ident", l.get("ident"))
                    db.session.add(new)
                    db.session.flush()
                    maps["location"][exported_key] = new.id
            db.session.commit()

            # Inventories
            for inv in payload.get("inventories", []):
                exported_key = inv.get("ident") if inv.get("ident") is not None else inv.get("id")
                existing = None
                if inv.get("ident"):
                    existing = Inventory.query.filter_by(owner_id=user_id, ident=inv.get("ident")).one_or_none()
                if not existing:
                    existing = Inventory.query.filter_by(owner_id=user_id, name=inv.get("name")).one_or_none()
                if existing:
                    maps["inventory"][exported_key] = existing.id
                    ui = UserInventory.query.filter_by(inventory_id=existing.id, user_id=user_id).one_or_none()
                    if not ui:
                        db.session.add(UserInventory(user_id=user_id, inventory_id=existing.id, access_level=0))
                else:
                    new = Inventory(name=inv.get("name"), description=inv.get("description"),
                                    owner_id=user_id, slug=inv.get("slug") or None,
                                    access_level=inv.get("access_level", 0), type=inv.get("type", 1))
                    if inv.get("ident"):
                        setattr(new, "ident", inv.get("ident"))
                    db.session.add(new)
                    db.session.flush()
                    db.session.add(UserInventory(user_id=user_id, inventory_id=new.id, access_level=0))
                    maps["inventory"][exported_key] = new.id
            db.session.commit()

            # Tags
            for t in payload.get("tags", []):
                exported_key = t.get("ident") if t.get("ident") is not None else t.get("id")
                existing = None
                if t.get("ident"):
                    existing = Tag.query.filter_by(user_id=user_id, ident=t.get("ident")).one_or_none()
                if not existing:
                    existing = Tag.query.filter_by(user_id=user_id, tag=t.get("tag")).one_or_none()
                if existing:
                    maps["tag"][exported_key] = existing.id
                else:
                    new = Tag(tag=t.get("tag"), user_id=user_id)
                    if t.get("ident"):
                        setattr(new, "ident", t.get("ident"))
                    db.session.add(new)
                    db.session.flush()
                    maps["tag"][exported_key] = new.id
            db.session.commit()

            # Items
            for it in payload.get("items", []):
                exported_key = it.get("ident") if it.get("ident") is not None else it.get("id")
                old_item_key = exported_key

                mapped_type = safe_map_lookup(maps["item_type"], it.get("item_type"))
                mapped_location = safe_map_lookup(maps["location"], it.get("location"))

                new_item = Item(
                    name=it.get("name"),
                    description=it.get("description"),
                    user_id=user_id,
                    quantity=it.get("quantity") or 1,
                    url=it.get("url"),
                    item_type=mapped_type,
                    location_id=mapped_location,
                    specific_location=it.get("specific_location"),
                    slug=it.get("slug") or None,
                )
                # set ident if provided
                if it.get("ident"):
                    setattr(new_item, "ident", it.get("ident"))
                db.session.add(new_item)
                db.session.flush()
                maps["item"][old_item_key] = new_item.id

                # tags by tag string (payload stores tag strings)
                for tag_val in it.get("tags", []):
                    ttag = Tag.query.filter_by(user_id=user_id, tag=tag_val).one_or_none()
                    if not ttag:
                        ttag = Tag(tag=tag_val, user_id=user_id)
                        db.session.add(ttag)
                        db.session.flush()
                    if ttag not in new_item.tags:
                        new_item.tags.append(ttag)

                # link to inventories (use inventory mapping)
                for old_inv_ref in it.get("inventory_idents", []):
                    new_inv_id = safe_map_lookup(maps["inventory"], old_inv_ref)
                    if new_inv_id:
                        inv = db.session.get(Inventory, new_inv_id)
                        if inv and new_item not in inv.items:
                            inv.items.append(new_item)

            db.session.commit()

            # ItemFields (custom_fields)
            for it in payload.get("items", []):
                new_item_id = safe_map_lookup(maps["item"], it.get("ident") if it.get("ident") is not None else it.get("id"))
                for old_fkey, value in (it.get("custom_fields") or {}).items():
                    # old_fkey may be an ident string or numeric string
                    new_field_id = safe_map_lookup(maps["field"], old_fkey)
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
                old_a = r.get("item_ref")
                old_b = r.get("related_item_ref")
                new_a = safe_map_lookup(maps["item"], old_a)
                new_b = safe_map_lookup(maps["item"], old_b)
                if new_a and new_b:
                    existing = Relateditems.query.filter_by(item_id=new_a, related_item_id=new_b).one_or_none()
                    if not existing:
                        db.session.add(Relateditems(item_id=new_a, related_item_id=new_b))
            db.session.commit()

        return True, "Import complete"
    except SQLAlchemyError as e:
        db.session.rollback()
        return False, f"DB error: {str(e)}"
    except Exception as e:
        return False, str(e)


if __name__ == '__main__':
    success, message = export_user_data_to_json(user_id=1, file_path="user_1_export.json")
    #success, message = import_user_data_from_json(user_id=1, file_path="user_1_export.json")
    print("Export:", success, message)
