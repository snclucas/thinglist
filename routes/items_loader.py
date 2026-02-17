import hashlib
import hmac
import os
from typing import Tuple

import bleach
from slugify import slugify

from services.field_template_service import FieldTemplateService
from services.image_service import ImageService
from utils import generate_item_image_filename


def process_field_sets(inventory_data, current_user, inventory_id, load_log):
    field_set_ = inventory_data.get("field_set", None)
    if field_set_ is not None and inventory_id is not None:
        template_name_ = bleach.clean(inventory_data.get("name"))

        if template_name_ is not None:
            template_slugs_ = field_set_.get("slugs", [])
            if len(template_slugs_) > 0:
                template_slugs_ = [bleach.clean(str(x)) for x in template_slugs_]
                status, msg, field_template_id_ = FieldTemplateService.save_template_fields(
                    template_name=template_name_,
                    fields=template_slugs_, user_id=current_user.id)

                # Attach the field template to the inventory directly (we have numeric inventory_id here)
                try:
                    from models import Inventory, FieldTemplate, TemplateField
                    from app import db
                    inv = db.session.query(Inventory).filter(Inventory.id == inventory_id).one_or_none()
                    if inv is not None and field_template_id_ is not None:
                        inv.field_template = field_template_id_
                        # set field 'show' status for items in this inventory
                        template_obj = db.session.query(FieldTemplate).filter(FieldTemplate.id == field_template_id_).one_or_none()
                        if template_obj is not None:
                            temp_fields = template_obj.fields
                            field_ids = [x.id for x in temp_fields]
                            # set fields on items
                            from services.field_service import FieldService as _FS
                            for item in inv.items:
                                _FS.set_field_status(item_id=item.id, field_ids=field_ids)
                        db.session.commit()
                        load_log += f"&nbsp;&nbsp;&nbsp;&nbsp;... created field template {template_name_}.<br>"
                    else:
                        load_log += f"&nbsp;&nbsp;&nbsp;&nbsp;... could not create field template {template_name_}.<br>"
                except Exception:
                    try:
                        db.session.rollback()
                    except Exception:
                        pass
                    load_log += f"&nbsp;&nbsp;&nbsp;&nbsp;... could not create field template {template_name_}.<br>"

        else:
            load_log += f"&nbsp;&nbsp;&nbsp;&nbsp;... no field template found/used.<br>"

    return load_log


def process_images(item, new_item_, item_id, current_user, root_path,
                   image_base_path, image_secret_key) -> Tuple[bool, str, dict]:
    """
    Save images for a created item. Returns (ok, message, counts)
    counts: {saved: int, failed: int}
    If an image has no 'image_data' we skip writing the binary but still include the filename entry.
    """
    item_image_filename = []
    saved = 0
    failed = 0
    import base64

    for img in item.get("images", []) or []:
        img_filename = img.get("image_filename", None)

        item_slug = f"{str(new_item_['item']['id'])}-{slugify(new_item_['item']['name'])}"

        if img_filename is None:
            img_filename = generate_item_image_filename(item_slug=item_slug,
                                                        item_id=item_id, img_type="jpg")

        img_is_main = img.get("is_main", "false")
        img_data = img.get("image_data", None)
        img_hash = img.get("image_hash", None)

        if img_is_main == "true":
            try:
                ImageService.set_item_main_image(main_image_url=img_filename, item_id=item_id,
                                                 user_id=current_user.id)
            except Exception:
                pass

        img_filepath = os.path.join(root_path, image_base_path,
                                    str(current_user.id), img_filename)

        # if no binary data supplied, skip writing file and just record filename
        if not img_data:
            item_image_filename.append(img_filename)
            continue

        try:
            imgdata = base64.b64decode(img_data)
        except Exception:
            failed += 1
            continue

        try:
            raw = img_data.encode('utf-8')
            hashed = hmac.new(image_secret_key, raw, hashlib.sha1)
            img_hmac_hash = base64.encodebytes(hashed.digest()).decode('utf-8')
        except Exception:
            img_hmac_hash = None

        if img_hash is not None and img_hmac_hash is not None and img_hash != img_hmac_hash:
            failed += 1
            continue

        try:
            # ensure directory exists
            os.makedirs(os.path.dirname(img_filepath), exist_ok=True)
            with open(img_filepath, 'wb') as img_file:
                img_file.write(imgdata)
            item_image_filename.append(img_filename)
            saved += 1
        except Exception:
            failed += 1
            continue

    if item_image_filename:
        try:
            ImageService.add_images_to_item(new_item_['item']['id'], item_image_filename, user=current_user)
        except Exception:
            pass

    return True, "images processed", {"saved": saved, "failed": failed}
