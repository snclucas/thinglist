import collections
import json
import os
import pathlib

from io import BytesIO
from typing import List

import bleach
from PIL import Image
from flask import Blueprint, render_template, redirect, url_for, request, jsonify, flash
from flask_login import login_required, current_user

from app import app
from database.database_functions import \
    add_images_to_item, delete_images_from_item, set_item_main_image, \
    update_item_fields, \
    set_inventory_default_fields, unrelate_items_by_id, \
    relate_items_by_id

from services.thinglist_services import ItemService, UserService, FieldService, LocationService, InventoryService, \
    FieldTemplateService, ItemTypeService

from utils import correct_image_orientation, generate_item_image_filename

from site_globals import __PUBLIC__, __VIEWER__, __DEFAULT__, __BAD_REQUEST__, __OK__, __NOT_FOUND__, __ALL__

item_routes = Blueprint('item', __name__)


@item_routes.context_processor
def my_utility_processor():
    def item_tag_to_string(item_tag_list):
        tag_arr = []
        for tag in item_tag_list:
            tag_arr.append(tag.tag.replace("@#$", " "))
        return ",".join(tag_arr)

    return dict(item_tag_to_string=item_tag_to_string)


@item_routes.route('/@<string:list_username>/<string:inventory_slug>/<string:item_slug>')
def item_with_username_and_inventory(list_username: str, inventory_slug: str, item_slug: str):
    inventory_owner_username = bleach.clean(list_username)
    inventory_owner = None
    inventory_owner_id = None

    user_is_authenticated = current_user.is_authenticated
    all_user_locations_ = None
    requested_user_id = None

    # normalize default inventory slug early
    if inventory_slug == "d":
        inventory_slug = f"{__DEFAULT__}-{list_username}"

    if user_is_authenticated:
        all_user_locations_ = LocationService.get_all_user_locations(user_id=current_user.id)
        requested_user_id = current_user.id

        # compare username string, not user object
        if getattr(current_user, "username", None) == inventory_owner_username:
            inventory_owner = current_user
            inventory_owner_id = inventory_owner.id

    # fetch inventory owner if not current user
    if inventory_owner is None:
        inventory_owner = UserService.get_user_by_username(username=inventory_owner_username)
        if inventory_owner is not None:
            inventory_owner_id = inventory_owner.id

    user_inventory_ = None
    inventory_ = None
    if inventory_slug != __ALL__:
        inventory_, user_inventory_ = InventoryService.find_inventory_by_slug(
            inventory_slug=inventory_slug,
            inventory_owner_id=inventory_owner_id,
            viewing_user_id=requested_user_id,
        )

        if inventory_ is None:
            return render_template('404.html', message="No such item or you do not have access to this item"), __NOT_FOUND__

    # determine access level
    item_access_level = __VIEWER__
    if inventory_slug != __ALL__:
        if user_inventory_ is None:
            if inventory_.access_level != __PUBLIC__:
                return render_template('404.html', message="No such item or you do not have access to this item"), __NOT_FOUND__
        else:
            item_access_level = user_inventory_.access_level

    # request item (pass requesting user id so service can filter/resolve user-specific data)
    item_data_ = ItemService.get_item_by_slug(item_slug=item_slug, user_id=requested_user_id)
    if item_data_:
        # item_obj, itemtype_obj, inventory_item_obj, userinventory_obj
        item_, itemtype_, inventory_item_ = item_data_
    else:
        item_, itemtype_, inventory_item_ = None, None, None

    if item_ is None or inventory_item_ is None:
        return render_template('404.html', message="No such item or you do not have access to this item"), __NOT_FOUND__

    # build ordered item fields (sorted by template_field.order)
    item_fields_list = ItemService.get_item_fields(item_id=item_.id)
    item_fields = {}
    for field_obj, item_field_obj, template_field in sorted(item_fields_list, key=lambda x: x[2].order):
        item_fields[field_obj] = item_field_obj

    all_item_fields = dict(ItemService.get_all_item_fields(item_id=item_.id))

    # map fields by their `field` attribute
    all_fields = {f.field: f for f in FieldService.get_all_fields()}

    item_location = None
    if user_is_authenticated and item_access_level != __VIEWER__:
        user_location_dict = LocationService.get_user_location_by_id(location_id=item_.location_id, user_id=current_user.id)
        if user_location_dict is not None:
            item_location = user_location_dict

    all_item_types_ = ItemTypeService.get_all_user_and_system_item_types(user_id=current_user.id if user_is_authenticated else None)

    return render_template('item/item.html',
                           name=list_username,
                           inventory_owner_id=inventory_owner_id,
                           item_fields=item_fields,
                           all_item_fields=all_item_fields,
                           list_username=list_username,
                           all_fields=all_fields,
                           inventory_slug=inventory_slug,
                           inventory=inventory_,
                           item=item_,
                           username=list_username,
                           item_type=itemtype_,
                           all_item_types=all_item_types_,
                           all_user_locations=all_user_locations_,
                           item_location=item_location,
                           item_access_level=item_access_level)

def item_with_username_and_inventory2(list_username: str, inventory_slug: str, item_slug: str):
    inventory_owner_username = bleach.clean(list_username)
    inventory_owner = None
    inventory_owner_id = None

    user_is_authenticated = current_user.is_authenticated
    all_user_locations_ = None
    if user_is_authenticated:
        all_user_locations_ = LocationService.get_all_user_locations(user_id=current_user.id)

        requested_user = current_user
        requested_user_id = requested_user.id

        if current_user == inventory_owner_username:
            inventory_owner = current_user
            inventory_owner_id = inventory_owner.id

        # check for default inventory
        if inventory_slug == "d":
            inventory_slug = f"{__DEFAULT__}-{list_username}"

    else:
        requested_user_id = None

    if inventory_owner is None:
        inventory_owner = UserService.get_user_by_username(username=inventory_owner_username)
        if inventory_owner is not None:
            inventory_owner_id = inventory_owner.id

    user_inventory_ = None
    inventory_ = None
    if inventory_slug != __ALL__:

        # get the inventory to check permissions
        inventory_, user_inventory_ = InventoryService.find_inventory_by_slug(inventory_slug=inventory_slug,
                                                             inventory_owner_id=inventory_owner_id,
                                                             viewing_user_id=requested_user_id)

        if inventory_ is None:
            return render_template(template_name_or_list='404.html',
                                   message="No such item or you do not have access to this item"), __NOT_FOUND__

    item_access_level = __VIEWER__
    if user_inventory_ is None and inventory_slug != __ALL__:
        if inventory_.access_level != __PUBLIC__:
            return render_template(template_name_or_list='404.html',
                                   message="No such item or you do not have access to this item"), __NOT_FOUND__
    else:
        if inventory_slug != __ALL__:
            item_access_level = user_inventory_.access_level

    item_data_ = ItemService.get_item_by_slug(item_slug=item_slug)
    if item_data_ is not None:
        item_, item_type_string, inventory_item_ = item_data_
    else:
        item_, item_type_string, inventory_item_ = None, None, None

    if item_ is None or inventory_item_ is None:
        return render_template(template_name_or_list='404.html',
                               message="No such item or you do not have access to this item"), __NOT_FOUND__

    item_fields = ItemService.get_item_fields(item_id=item_.id)

    ii = {}
    for field_data in item_fields:
        field_ = field_data[0]
        item_field_ = field_data[1]
        template_field_ = field_data[2]
        ii[template_field_.order] = [field_, item_field_]

    od = collections.OrderedDict(sorted(ii.items()))

    dfdf = {}
    for k, v in od.items():
        dfdf[v[0]] = v[1]

    item_fields = dict(dfdf)

    all_item_fields = dict(ItemService.get_all_item_fields(item_id=item_.id))
    all_fields = FieldService.get_all_fields()
    # convert to dict with Field.field as key
    all_fields_dict = {}
    for field in all_fields:
        all_fields_dict[field.field] = field
    all_fields = all_fields_dict


    item_location = None
    if user_is_authenticated and item_access_level != __VIEWER__:
        user_location_dict = LocationService.get_user_location_by_id(location_id=item_.location_id, user_id=current_user.id)
        if user_location_dict is not None:
            item_location = user_location_dict

    all_item_types_ = ItemTypeService.get_all_user_and_system_item_types(user_id=current_user.id)

    return render_template(template_name_or_list='item/item.html', name=list_username,
                           inventory_owner_id=inventory_owner_id, item_fields=item_fields,
                           all_item_fields=all_item_fields, list_username=list_username,
                           all_fields=all_fields, inventory_slug=inventory_slug, inventory=inventory_,
                           item=item_, username=list_username, item_type=item_type_string,
                           all_item_types=all_item_types_,
                           all_user_locations=all_user_locations_, item_location=item_location,
                           item_access_level=item_access_level)


@item_routes.route('/item/edit/<item_id>', methods=['POST'])
@login_required
def edit_item(item_id):
    form_data = dict(request.form)
    del form_data["csrf_token"]
    #item_id = form_data["item_id"]
    #del form_data["item_id"]

    item_slug = form_data["item_slug"]
    del form_data["item_slug"]

    inventory_slug = form_data["inventory_slug"]
    del form_data["inventory_slug"]

    username = form_data["list_username"]
    del form_data["list_username"]

    item_name = request.form.get("item_name")
    item_description = request.form.get("item_description")
    item_quantity = request.form.get("item_quantity")
    item_url = request.form.get("item_url")
    item_url = bleach.clean(item_url)

    item_name = bleach.clean(item_name)
    item_description = item_description

    description_limit = app.config['ITEM_DESCRIPTION_CHAR_LIMIT']

    if len(item_description) > int(description_limit):
        flash(f"Description must be less than {description_limit} characters")
        return redirect(url_for(endpoint='item.item_with_username_and_inventory',
                                list_username=username,
                                inventory_slug=inventory_slug,
                                item_slug=item_slug))

    item_quantity = bleach.clean(item_quantity)

    del form_data["item_name"]
    del form_data["item_description"]
    del form_data["item_quantity"]
    del form_data["item_url"]

    item_tags = request.form.get("item_tags")
    item_tags = bleach.clean(item_tags)
    if item_tags != '':
        item_tags = [x.strip() for x in item_tags.split(",")]
    else:
        item_tags = []
    del form_data["item_tags"]

    item_type = request.form.get("item_type")
    item_location = request.form.get("item_location")
    item_specific_location = request.form.get("item_specific_location")

    del form_data["item_type"]
    del form_data["item_location"]
    del form_data["item_specific_location"]

    form_data = {int(k): v for k, v in form_data.items()}



    new_item_data = {
        "id": item_id,
        "name": item_name,
        "description": item_description,
        "item_type": item_type,
        "item_quantity": item_quantity,
        "item_location": item_location,
        "item_specific_location": item_specific_location,
        "item_tags": item_tags,
        "item_url": item_url
    }

    new_item_slug = None
    update_result = ItemService.update_item_by_id(item_data=new_item_data, item_id=int(item_id), user=current_user)
    if update_result["status"] == "success":
        item_dict = update_result["item"]
        new_item_slug = item_dict['slug']
        update_item_fields(data=form_data, item_id=int(item_id))
    else:
        flash("Error updating item")

    return redirect(url_for(endpoint='item.item_with_username_and_inventory',
                            list_username=username,
                            inventory_slug=inventory_slug,
                            item_slug=new_item_slug))


@item_routes.route('/item/fields', methods=['POST'])
@login_required
def edit_item_fields():
    json_data = request.json
    item_id = json_data['item_id']
    field_ids = json_data['field_ids']
    FieldService.set_field_status(item_id, field_ids, is_visible=True)

    return True


@item_routes.route('/default-inventory_fields', methods=['POST'])
@login_required
def edit_inv_default_fields():
    json_data = request.json
    inventory_id = json_data['inventory_id']
    field_ids = json_data['field_ids']

    field_ids = [str(x) for x in field_ids]

    set_inventory_default_fields(inventory_id=inventory_id, user=current_user, default_fields=field_ids)

    return True


@item_routes.route('/inventory/save-inventory-template', methods=['POST'])
@login_required
def save_inventory_template():
    form_data = dict(request.form)
    inventory_id = form_data.get('inventory_id')
    if inventory_id is None:
        app.logger.error("No inventory ID provided")
        return redirect(url_for('inventory.inventories'))

    inventory_id = int(inventory_id)

    inventory_slug = form_data.get('inventory_slug')
    inventory_template = form_data.get('inventory_template')
    if inventory_template == '-1':
        inventory_template = None
    else:
        inventory_template = int(inventory_template)

    result = FieldTemplateService.save_inventory_fieldtemplate(inventory_id=inventory_id,
                                          inventory_template=inventory_template, user_id=current_user.id)
    #fix field templates - set back to None if requested and remove the feild data
    if not result:
        flash("Error saving inventory template")

    return redirect(url_for(endpoint='items.items_with_username_and_inventory',
                            list_username=current_user.username, inventory_slug=inventory_slug))

@login_required
@item_routes.route("/item/relate-items", methods=["POST"])
def relate_items():
    item_id = request.form.get("item_id")
    relateditem_slug = request.form.get("relateditem")
    inventory_slug = request.form.get("inventory_slug")
    item_slug = request.form.get("item_slug")

    if item_id is None or relateditem_slug is None or inventory_slug is None or item_slug is None:
        return jsonify({"message": "All fields are required"}), __BAD_REQUEST__

    item_id = bleach.clean(item_id)
    item_id = int(item_id)
    relateditem_slug = bleach.clean(relateditem_slug)
    inventory_slug = bleach.clean(inventory_slug)
    item_slug = bleach.clean(item_slug)

    relateditem_ = ItemService.get_item_by_slug(item_slug=relateditem_slug, user_id=current_user.id)
    if relateditem_ is None:
        return jsonify({"message": "No such item"}), __NOT_FOUND__

    if relateditem_.id != item_id:
        relate_items_by_id(item1_id=item_id, item2_id=relateditem_.id)

    return redirect(url_for(endpoint='item.item_with_username_and_inventory',
                            list_username=current_user.username,
                            inventory_slug=inventory_slug,
                            item_slug=item_slug))


@item_routes.route(rule='/unrelate-items', methods=['POST'])
def unrelate_items():
    user_is_authenticated = current_user.is_authenticated
    if user_is_authenticated:
        json_data = request.json
        item1_id = json_data['item1']
        item1_id = bleach.clean(str(item1_id))
        item2_id = json_data['item2']
        item2_id = bleach.clean(str(item2_id))
        item1 = int(item1_id)
        item2 = int(item2_id)
        status, message = unrelate_items_by_id(item1_id=item1, item2_id=item2)
        return json.dumps({'success': True}), __OK__, {'ContentType': 'application/json'}
    else:
        return json.dumps({'success': False}), __OK__, {'ContentType': 'application/json'}


@item_routes.route(rule="/item/images/remove", methods=["POST"])
def delete_images():
    json_data = request.json
    item_id = json_data.get('item_id', None)
    item_slug = json_data.get('item_slug', None)
    inventory_slug = json_data.get('inventory_slug', None)

    if item_id is not None and item_slug is not None and inventory_slug is not None:
        item_id = int(bleach.clean(str(item_id)))
        item_slug = bleach.clean(str(item_slug))
        inventory_slug = bleach.clean(str(inventory_slug))
    else:
        return jsonify({"message": "Item ID is required"}), __BAD_REQUEST__

    username = json_data['username']
    username = bleach.clean(str(username))

    image_list = json_data['image_id_list']
    image_list = [bleach.clean(str(x)) for x in image_list]

    status, message = delete_images_from_item(item_id=item_id, image_ids=image_list, user=current_user)

    if not status:
        flash(message=f"There was a problem deleting the images")

    return redirect(url_for(endpoint='item.item_with_username_and_inventory',
                            list_username=username,
                            inventory_slug=inventory_slug,
                            item_slug=item_slug))


@item_routes.route("/item/images/setmainimage", methods=["POST"])
def set_main_image():
    """
    Sets the main image for an item.

    This method is used to set the main image for an item in the inventory. It takes in a JSON payload containing the following fields:
    - 'main_image': The URL of the main image for the item.
    - 'item_slug': The slug of the item.
    - 'inventory_slug': The slug of the inventory.
    - 'item_id': The ID of the item.
    - 'username': The username of the user.

    If any of the required fields are missing in the JSON payload, a response with status code 400 and a JSON message indicating that all fields are required is returned.

    The 'main_image' field is processed by removing the '/uploads/' part of the URL.

    After processing the JSON payload and validating the fields, the method calls the 'set_item_main_image' function passing in the processed main image URL, the item ID, and the current
    * user.

    Finally, a redirect response is returned to the route 'item.item_with_username_and_inventory' with the necessary route parameters: 'username', 'inventory_slug', and 'item_slug'.

    Returns:
        A redirect response to the route 'item.item_with_username_and_inventory' with the necessary route parameters.

    """
    json_data = request.json
    main_image = json_data.get('main_image')
    item_slug = json_data.get('item_slug')
    inventory_slug = json_data.get('inventory_slug')
    item_id = json_data.get('item_id')
    username = json_data.get('username')

    if not all([main_image, item_slug, inventory_slug, item_id, username]):
        return jsonify({"message": "All fields are required"}), __BAD_REQUEST__

    main_image = main_image.replace('/uploads/', '')

    set_item_main_image(main_image_url=main_image, item_id=item_id, user_id=current_user.id)

    return redirect(url_for(endpoint='item.item_with_username_and_inventory',
                            list_username=username,
                            inventory_slug=inventory_slug,
                            item_slug=item_slug))

@login_required
@item_routes.route("/item/images/upload", methods=["POST"])
def upload():
    new_filename_list: List[str] = []

    username_: str = request.form.get("username")
    item_id_: str = request.form.get("item_id")
    item_slug_: str = request.form.get("item_slug")
    inventory_slug_: str = request.form.get("inventory_slug")

    username: str = bleach.clean(username_)
    item_id_: str = bleach.clean(str(item_id_))
    item_slug: str = bleach.clean(item_slug_)
    inventory_slug: str = bleach.clean(inventory_slug_)

    if username != current_user.username:
        return redirect(url_for(endpoint='item.item_with_username_and_inventory',
                                list_username=username,
                                inventory_slug=inventory_slug,
                                item_slug=item_slug))

    try:
        item_id: int = int(item_id_)
    except ValueError:
        pass # for now

    uploaded_files = request.files.getlist("file[]")
    for file in uploaded_files:

        if not file.filename.lower().endswith(('.png', '.jpg', '.jpeg', '.tiff', '.bmp', '.gif')):
            flash("Only image files are allowed")
            return redirect(url_for(endpoint='item.item_with_username_and_inventory',
                                    list_username=username,
                                    inventory_slug=inventory_slug,
                                    item_slug=item_slug))

        if "image" not in file.mimetype:
            flash("Only image files are allowed")
            return redirect(url_for(endpoint='item.item_with_username_and_inventory',
                                    list_username=username,
                                    inventory_slug=inventory_slug,
                                    item_slug=item_slug))

        new_filename = generate_item_image_filename(item_slug=item_slug, item_id=item_id, img_type="jpg")
        new_filename_list.append(new_filename)

        in_mem_file = BytesIO(file.read())
        image = Image.open(in_mem_file)

        image = correct_image_orientation(image=image)

        image = image.convert('RGB')
        image.thumbnail((int(app.config['PROCESS_IMAGE_WIDTH']), int(app.config['PROCESS_IMAGE_HEIGHT'])))
        in_mem_file = BytesIO()
        image.save(in_mem_file, format=app.config['PROCESS_IMAGE_FORMAT'])
        in_mem_file.seek(0)

        user_id = str(current_user.id)

        pathlib.Path(os.path.join(app.config['USER_IMAGES_BASE_PATH'], user_id, new_filename)).write_bytes(
            in_mem_file.getbuffer().tobytes())

    add_images_to_item(item_id=item_id, filenames=new_filename_list, user=current_user)

    return redirect(url_for(endpoint='item.item_with_username_and_inventory',
                            list_username=username,
                            inventory_slug=inventory_slug,
                            item_slug=item_slug))
