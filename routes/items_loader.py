import hashlib
import hmac
import os

import bleach
from slugify import slugify

from database.database_functions import save_template_fields, save_inventory_fieldtemplate, set_item_main_image, \
    add_images_to_item
from utils import generate_item_image_filename


def process_field_sets(inventory_data, current_user, found_inv, load_log):
    field_set_ = inventory_data.get("field_set", None)
    if field_set_ is not None:
        template_name_ = bleach.clean(inventory_data.get("name"))

        if template_name_ is not None:
            template_slugs_ = field_set_.get("slugs", [])
            if len(template_slugs_) > 0:
                template_slugs_ = [bleach.clean(str(x)) for x in template_slugs_]
                field_template_id_ = save_template_fields(template_name=template_name_,
                                                          fields=template_slugs_, user=current_user)

                status, save_inv_fieldtemplate_msg = save_inventory_fieldtemplate(inventory_id=found_inv["id"],
                                                                                  inventory_template=field_template_id_,
                                                                                  user_id=current_user.id)
                if status:
                    load_log += f"&nbsp;&nbsp;&nbsp;&nbsp;... created field template {template_name_}.<br>"
                else:
                    load_log += f"&nbsp;&nbsp;&nbsp;&nbsp;... could no create field template {template_name_}.<br>"

        else:
            load_log += f"&nbsp;&nbsp;&nbsp;&nbsp;... no field template found/used.<br>"

    return load_log

def process_images(item, new_item_, item_id, current_user, app):
    item_image_filename = []
    for img in item["images"]:
        img_filename = img.get("image_filename", None)

        item_slug = f"{str(new_item_['item']['id'])}-{slugify(new_item_['item']['name'])}"

        if img_filename is None:
            img_filename = generate_item_image_filename(item_slug=item_slug,
                                                        item_id=item_id, img_type="jpg")

        img_is_main = img.get("is_main", "false")
        img_data = img.get("image_data", None)
        img_hash = img.get("image_hash", None)

        if img_is_main == "true":
            set_item_main_image(main_image_url=img_filename, item_id=item_id,
                                user_id=current_user.id)

        img_filepath = os.path.join(app.root_path, app.config['USER_IMAGES_BASE_PATH'],
                                    str(current_user.id), img_filename)

        import base64
        imgdata = base64.b64decode(img_data)

        raw = img_data.encode('utf-8')
        key = app.config['IMAGE_SECRET_KEY'].encode('utf-8')
        hashed = hmac.new(key, raw, hashlib.sha1)
        img_hmac_hash = base64.encodebytes(hashed.digest()).decode('utf-8')

        if img_hash == img_hmac_hash:
            try:
                with open(img_filepath, 'wb') as img_file:
                    img_file.write(imgdata)
                    item_image_filename.append(img_filename)
            except Exception as ex:
                app.logger.error(f"Error saving image: {str(ex)}")

    add_images_to_item(new_item_['item']['id'], item_image_filename, user=current_user)