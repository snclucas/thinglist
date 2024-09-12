import collections
import json
import os
import pathlib
import random
import string
from io import BytesIO

import bleach
from PIL import Image
from flask import Blueprint, render_template, redirect, url_for, request, jsonify, flash
from flask_login import login_required, current_user
# from flask_weasyprint import render_pdf, HTML

from app import app
from database_functions import get_all_user_locations, \
    get_all_item_types, \
    update_item_by_id, get_item_by_slug, add_images_to_item, delete_images_from_item, set_item_main_image, \
    find_inventory_by_slug, \
    get_item_fields, get_all_item_fields, \
    get_all_fields, set_field_status, update_item_fields, \
    set_inventory_default_fields, save_inventory_fieldtemplate, get_user_location_by_id, unrelate_items_by_id, \
    find_item_by_slug, relate_items_by_id, find_user_by_username, __PUBLIC__, __PRIVATE__, __VIEWER__, __INVENTORY__, \
    __LIST__
from utils import correct_image_orientation, generate_item_image_filename

item_routes = Blueprint('item', __name__)


@item_routes.context_processor
def my_utility_processor():
    def item_tag_to_string(item_tag_list):
        tag_arr = []
        for tag in item_tag_list:
            tag_arr.append(tag.tag.replace("@#$", " "))
        return ",".join(tag_arr)

    return dict(item_tag_to_string=item_tag_to_string)


@app.context_processor
def inject_globals():
    return dict(
        __PUBLIC__=__PUBLIC__,
        __PRIVATE__=__PRIVATE__,

        __INVENTORY__=__INVENTORY__,
        __LIST__=__LIST__
    )

# @item_routes.route('/item/save-pdf', methods=['POST'])
# @login_required
# def items_save_pdf():
#     if request.method == 'POST':
#         html = item_with_username_and_inventory()
#
#         return render_pdf(HTML(string=html))

        #return item_with_username_and_inventory()


@item_routes.route('/@<username>/<inventory_slug>/<item_slug>')
def item_with_username_and_inventory(username: str, inventory_slug: str, item_slug: str):
    inventory_owner_username = bleach.clean(username)
    inventory_owner = None
    inventory_owner_id = None

    user_is_authenticated = current_user.is_authenticated
    all_user_locations_ = None
    if user_is_authenticated:
        all_user_locations_ = get_all_user_locations(user_id=current_user.id)

        requested_user = current_user
        requested_user_id = requested_user.id

        if current_user == inventory_owner_username:
            inventory_owner = current_user
            inventory_owner_id = inventory_owner.id

        # check for default inventory
        if inventory_slug == "d":
            inventory_slug = f"default-{username}"

    else:
        requested_user = None
        requested_user_id = None

    if inventory_owner is None:
        inventory_owner = find_user_by_username(username=inventory_owner_username)
        if inventory_owner is not None:
            inventory_owner_id = inventory_owner.id

    # get the inventory to check permissions
    inventory_, user_inventory_ = find_inventory_by_slug(inventory_slug=inventory_slug,
                                                         inventory_owner_id=inventory_owner_id,
                                                         viewing_user_id=requested_user_id)

    if inventory_ is None:
        return render_template('404.html', message="No such item or you do not have access to this item"), 404

    item_access_level = __VIEWER__
    if user_inventory_ is None:
        if inventory_.access_level != __PUBLIC__:
            return render_template('404.html', message="No such item or you do not have access to this item"), 404
    else:
        item_access_level = user_inventory_.access_level

    item_data_ = get_item_by_slug(item_slug=item_slug)
    if item_data_ is not None:
        item_, item_type_string, inventory_item_ = item_data_
    else:
        item_, item_type_string, inventory_item_ = None, None, None

    if item_ is None or inventory_item_ is None:
        return render_template('404.html', message="No such item or you do not have access to this item"), 404

    item_fields = get_item_fields(item_id=item_.id)

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

    all_item_fields = dict(get_all_item_fields(item_id=item_.id))
    all_fields = dict(get_all_fields())

    item_location = None
    if user_is_authenticated and item_access_level != __VIEWER__:
        user_location = get_user_location_by_id(location_id=item_.location_id, user_id=current_user.id)
        if user_location is not None:
            item_location = user_location

    all_item_types_ = get_all_item_types()

    return render_template('item/item.html', name=username, inventory_owner_id=inventory_owner_id, item_fields=item_fields, all_item_fields=all_item_fields,
                           all_fields=all_fields, inventory_slug=inventory_.slug, inventory=inventory_,
                           item=item_, username=username, item_type=item_type_string,
                           all_item_types=all_item_types_,
                           all_user_locations=all_user_locations_, item_location=item_location,
                           item_access_level=item_access_level)


@item_routes.route('/item/edit/<item_id>', methods=['POST'])
@login_required
def edit_item(item_id):
    if request.method == 'POST':
        form_data = dict(request.form)
        del form_data["csrf_token"]
        item_id = form_data["item_id"]
        del form_data["item_id"]

        item_slug = form_data["item_slug"]
        del form_data["item_slug"]

        inventory_slug = form_data["inventory_slug"]
        del form_data["inventory_slug"]

        username = form_data["username"]
        del form_data["username"]

        item_name = request.form.get("item_name")
        item_description = request.form.get("item_description")
        item_quantity = request.form.get("item_quantity")

        item_name = bleach.clean(item_name)
        item_description = item_description

        description_limit = app.config['ITEM_DESCRIPTION_CHAR_LIMIT']

        if len(item_description) > int(description_limit):
            flash(f"Description must be less than {description_limit} characters")
            return redirect(url_for('item.item_with_username_and_inventory',
                                    username=username,
                                    inventory_slug=inventory_slug,
                                    item_slug=item_slug))

        item_quantity = bleach.clean(item_quantity)

        del form_data["item_name"]
        del form_data["item_description"]
        del form_data["item_quantity"]

        item_tags = request.form.get("item_tags")
        item_tags = bleach.clean(item_tags)
        if item_tags != '':
            item_tags = item_tags.strip().split(",")
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

        update_item_fields(data=form_data, item_id=int(item_id))

        new_item_data = {
            "id": item_id,
            "name": item_name,
            "description": item_description,
            "item_type": item_type,
            "item_quantity": item_quantity,
            "item_location": item_location,
            "item_specific_location": item_specific_location,
            "item_tags": item_tags
        }

        new_item_slug = update_item_by_id(item_data=new_item_data, item_id=int(item_id), user=current_user)
        return redirect(url_for('item.item_with_username_and_inventory',
                                username=username,
                                inventory_slug=inventory_slug,
                                item_slug=new_item_slug))


@item_routes.route('/item/fields', methods=['POST'])
@login_required
def edit_item_fields():
    if request.method == 'POST':
        json_data = request.json
        item_id = json_data['item_id']
        field_ids = json_data['field_ids']
        set_field_status(item_id, field_ids, is_visible=True)

    return True


@item_routes.route('/default-inventory_fields', methods=['POST'])
@login_required
def edit_inv_default_fields():
    if request.method == 'POST':
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

    result = save_inventory_fieldtemplate(inventory_id=inventory_id,
                                          inventory_template=inventory_template, user_id=current_user.id)

    if not result:
        flash("Error saving inventory template")

    return redirect(url_for(endpoint='items.items_with_username_and_inventory',
                            username=current_user.username, inventory_slug=inventory_slug))

@login_required
@item_routes.route("/item/relate-items", methods=["POST"])
def relate_items():
    item_id = request.form.get("item_id")
    relateditem_slug = request.form.get("relateditem")
    inventory_slug = request.form.get("inventory_slug")
    item_slug = request.form.get("item_slug")

    if item_id is None or relateditem_slug is None or inventory_slug is None or item_slug is None:
        return jsonify({"message": "All fields are required"}), 400

    item_id = bleach.clean(item_id)
    item_id = int(item_id)
    relateditem_slug = bleach.clean(relateditem_slug)
    inventory_slug = bleach.clean(inventory_slug)
    item_slug = bleach.clean(item_slug)

    relateditem_ = find_item_by_slug(item_slug=relateditem_slug, user_id=current_user.id)
    if relateditem_ is None:
        return jsonify({"message": "No such item"}), 404

    if relateditem_.id != item_id:
        relate_items_by_id(item1_id=item_id, item2_id=relateditem_.id)

    return redirect(url_for(endpoint='item.item_with_username_and_inventory',
                            username=current_user.username,
                            inventory_slug=inventory_slug,
                            item_slug=item_slug))


@item_routes.route(rule='/unrelate-items', methods=['POST'])
def unrelate_items():
    user_is_authenticated = current_user.is_authenticated
    if user_is_authenticated:
        if request.method == 'POST':
            json_data = request.json
            item1_id = json_data['item1']
            item1_id = bleach.clean(str(item1_id))
            item2_id = json_data['item2']
            item2_id = bleach.clean(str(item2_id))
            item1 = int(item1_id)
            item2 = int(item2_id)
            status, message = unrelate_items_by_id(item1_id=item1, item2_id=item2)
            return json.dumps({'success': True}), 200, {'ContentType': 'application/json'}
    else:
        return json.dumps({'success': False}), 200, {'ContentType': 'application/json'}


@item_routes.route("/item/images/remove", methods=["POST"])
def delete_images():
    if request.method == 'POST':
        json_data = request.json
        item_id = json_data['item_id']
        item_slug = json_data['item_slug']
        inventory_slug = json_data['inventory_slug']
        username = json_data['username']
        image_list = json_data['image_id_list']

        delete_images_from_item(item_id=item_id, image_ids=image_list, user=current_user)

        return redirect(url_for('item.item_with_username_and_inventory',
                                username=username,
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
        return jsonify({"message": "All fields are required"}), 400

    main_image = main_image.replace('/uploads/', '')

    set_item_main_image(main_image_url=main_image, item_id=item_id, user=current_user)

    return redirect(url_for(endpoint='item.item_with_username_and_inventory',
                            username=username,
                            inventory_slug=inventory_slug,
                            item_slug=item_slug))

@login_required
@item_routes.route("/item/images/upload", methods=["POST"])
def upload():
    new_filename_list = []

    username = request.form.get("username")
    item_id = request.form.get("item_id")
    item_slug = request.form.get("item_slug")
    inventory_slug = request.form.get("inventory_slug")

    username = bleach.clean(username)
    item_id = bleach.clean(str(item_id))
    item_slug = bleach.clean(item_slug)
    inventory_slug = bleach.clean(inventory_slug)

    if username != current_user.username:
        return redirect(url_for('item.item_with_username_and_inventory',
                                username=username,
                                inventory_slug=inventory_slug,
                                item_slug=item_slug))

    try:
        item_id = int(item_id)
    except ValueError:
        pass # for now

    uploaded_files = request.files.getlist("file[]")
    for file in uploaded_files:

        new_filename = generate_item_image_filename(item_slug=item_slug, item_id=item_id, img_type="jpg")
        new_filename_list.append(new_filename)

        in_mem_file = BytesIO(file.read())
        image = Image.open(in_mem_file)

        image = correct_image_orientation(image=image)

        image = image.convert('RGB')
        image.thumbnail((600, 600))
        in_mem_file = BytesIO()
        image.save(in_mem_file, format="JPEG")
        in_mem_file.seek(0)

        user_id = str(current_user.id)

        pathlib.Path(os.path.join(app.config['USER_IMAGES_BASE_PATH'], user_id, new_filename)).write_bytes(
            in_mem_file.getbuffer().tobytes())

    add_images_to_item(item_id=item_id, filenames=new_filename_list, user=current_user)

    return redirect(url_for('item.item_with_username_and_inventory',
                            username=username,
                            inventory_slug=inventory_slug,
                            item_slug=item_slug))
