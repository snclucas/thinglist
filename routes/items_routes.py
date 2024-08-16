import hashlib
import hmac
import json
import os

import csv

import bleach
import pdfkit
from flask import make_response, flash

from flask import Blueprint, render_template, redirect, url_for, request, current_app
from flask_login import login_required, current_user
from slugify import slugify

from app import app
from database_functions import get_all_user_locations, \
    get_all_item_types, \
    find_type_by_text, find_inventory_by_slug, find_location_by_name, \
    add_item_to_inventory, find_all_user_inventories, delete_items, move_items, \
    get_all_fields, add_new_user_itemtype, \
    get_user_templates, get_item_custom_field_data, \
    get_users_for_inventory, get_user_inventory_by_id, get_or_add_new_location, edit_items_locations, \
    change_item_access_level, link_items, copy_items, commit, find_items_new, __PUBLIC, __PRIVATE, \
    find_user_by_username, add_images_to_item, set_item_main_image, get_user_inventories
from models import FieldTemplate
from utils import generate_item_image_filename

items_routes = Blueprint('items', __name__)


@items_routes.context_processor
def my_utility_processor():
    def item_tag_to_string(item_tag_list):
        tag_arr = []
        for tag in item_tag_list:
            tag_arr.append(tag.tag.replace("@#$", " "))
        return ",".join(tag_arr)

    return dict(item_tag_to_string=item_tag_to_string)


def _find_list_index(list_, value):
    try:
        return list_.index(value)
    except ValueError:
        return -1


@items_routes.route('/items/load', methods=['POST'])
@login_required
def items_load():
    username = current_user.username

    if request.method == 'POST':
        inventory_slug_from_form = request.form.get("inventory_slug")
        # inventory_id = request.form.get("inventory_id")

        if request.files:
            uploaded_file = request.files['file']  # This line uses the same variable and worked fine
            filepath = os.path.join(app.config['FILE_UPLOADS'], uploaded_file.filename)
            uploaded_file.save(filepath)

            import mimetypes
            import_file_mimetype = mimetypes.MimeTypes().guess_type(filepath)[0]
            if "application/json" not in import_file_mimetype:
                flash("Uploaded file does not seem to be a JSON file.")

                return redirect(url_for('items.items_with_username_and_inventory',
                                        username=username, inventory_slug=inventory_slug_from_form).replace('%40', '@'))

            try:
                with open(filepath, 'r') as f:
                    data = json.load(f)

                    for inventory_ in data:
                        inventory_data = inventory_.get("inventory", None)
                        if inventory_data is None:
                            break

                        inventory_slug_ = inventory_data.get("slug", None)

                        found_inv = find_inventory_by_slug(inventory_slug=inventory_slug_,
                                                           inventory_owner_id=current_user.id,
                                                           viewing_user_id=current_user.id)

                        if found_inv is None:
                            break

                        # If we are importing into a specific inventory, only import into that inventory
                        if inventory_slug_from_form != "all":
                            if inventory_slug_ != inventory_slug_from_form:
                                break

                        inventory_id = found_inv[0].id

                        if "items" in inventory_data:
                            for item in inventory_data["items"]:
                                item_id = bleach.clean(item.get("id"))
                                item_name = bleach.clean(item.get("name"))
                                item_description = bleach.clean(item.get("description"))
                                item_type = bleach.clean(item.get("types"))
                                item_quantity = bleach.clean(item.get("quantity"))
                                item_tags = bleach.clean(item.get("tags"))
                                item_location = bleach.clean(item.get("location"))
                                item_specific_location = bleach.clean(item.get("specific_location"))

                                # add item types
                                add_new_user_itemtype(name=item_type, user_id=current_user.id)

                                location_id = None
                                if item_location is not None:
                                    if item_location.strip() != "":
                                        location_data_ = get_or_add_new_location(location_name=item_location,
                                                                                 location_description=item_location,
                                                                                 to_user_id=current_user.id)
                                        location_id = location_data_.get("id")

                                tag_array = item_tags

                                for t in range(len(tag_array)):
                                    tag_array[t] = tag_array[t].strip()
                                    tag_array[t] = tag_array[t].replace(" ", "@#$")

                                custom_fields = {}
                                for k in list(item.keys()):
                                    if k not in ["id", "name", "description", "type", "tags", "location", "specific_location", "quantity"]:
                                        if k != "images":
                                            custom_fields[k] = item[k]

                                new_item_ = add_item_to_inventory(item_id=item_id, item_name=item_name,
                                                                  item_desc=item_description,
                                                                  item_type=item_type, item_quantity=item_quantity,
                                                                  item_tags=tag_array, inventory_id=inventory_id,
                                                                  item_location_id=location_id,
                                                                  item_specific_location=item_specific_location,
                                                                  user_id=current_user.id, custom_fields=custom_fields)

                                commit()

                                if new_item_["status"] != "error":
                                    # save images
                                    item_image_filename = []
                                    for img in item["images"]:
                                        #img_type = img.get("img_type", None)
                                        img_filename = img.get("image_filename", None)

                                        item_slug = f"{str(new_item_['item']['id'])}-{slugify(new_item_['item']['name'])}"

                                        if img_filename is None:
                                            img_filename = generate_item_image_filename(item_slug=item_slug, item_id=item_id, img_type="jpg")

                                        img_is_main = img.get("is_main", "false")
                                        img_data = img.get("image_data", None)
                                        img_hash = img.get("image_hash", None)

                                        if img_is_main == "true":
                                            set_item_main_image(main_image_url=img_filename, item_id=item_id, user=current_user)

                                        img_filepath = os.path.join(app.root_path, app.config['UPLOAD_FOLDER'], img_filename)

                                        import base64
                                        imgdata = base64.b64decode(img_data)

                                        raw = img_data.encode('utf-8')#.encode("utf-8")
                                        key = 'SOME_SECRET_KEY'.encode('utf-8')
                                        hashed = hmac.new(key, raw, hashlib.sha1)
                                        img_hmac_hash = base64.encodebytes(hashed.digest()).decode('utf-8')

                                        if img_hash == img_hmac_hash:
                                            with open(img_filepath, 'wb') as f:
                                                f.write(imgdata)
                                                item_image_filename.append(img_filename)


                                    add_images_to_item(new_item_['item']['id'], item_image_filename, user=current_user)




                                if new_item_["status"] == "error":
                                    flash("Sorry, there was an error importing these things.")
                                    return redirect(url_for(endpoint='items.items_with_username_and_inventory',
                                                            username=username, inventory_slug=inventory_slug_from_form).replace('%40',
                                                                                                                      '@'))

            except Exception as e:
                pass


        return redirect(url_for(endpoint='items.items_with_username_and_inventory',
                                username=username, inventory_slug=inventory_slug_from_form).replace('%40', '@'))

@items_routes.route('/items/load', methods=['POST'])
@login_required
def items_load_orig():
    username = current_user.username

    if request.method == 'POST':
        inventory_slug = request.form.get("inventory_slug")
        inventory_id = request.form.get("inventory_id")

        if request.files:
            uploaded_file = request.files['file']  # This line uses the same variable and worked fine
            filepath = os.path.join(app.config['FILE_UPLOADS'], uploaded_file.filename)
            uploaded_file.save(filepath)

            import mimetypes
            import_file_mimetype = mimetypes.MimeTypes().guess_type(filepath)[0]
            if "text/csv" not in import_file_mimetype:
                flash("Uploaded file does not seem to be a CSV file.")

                return redirect(url_for('items.items_with_username_and_inventory',
                                        username=username, inventory_slug=inventory_slug).replace('%40', '@'))

            with open(filepath) as csvfile:
                line_count = 0
                reader = csv.reader(csvfile, delimiter=',', quotechar='"')
                column_headers = None
                custom_fields = {}
                name_col_index = None
                description_col_index = None
                type_col_index = None
                tags_col_index = None
                location_col_index = None
                specific_location_col_index = None
                quantity_col_index = None

                item_location = None
                item_specific_location = None

                base_column_headers = 0

                for row in reader:
                    number_columns = len(row)
                    if line_count == 0:  # Header
                        #  Get column headers and convert to lower case
                        column_headers = row
                        column_headers = [str(x).lower() for x in column_headers]

                        id_col_index = _find_list_index(column_headers, "id")
                        name_col_index = _find_list_index(column_headers, "name")
                        description_col_index = _find_list_index(column_headers, "description")

                        if name_col_index == -1 or description_col_index == -1:
                            return redirect(url_for('items.items_with_username_and_inventory',
                                                    username=username,
                                                    inventory_slug=inventory_slug).replace('%40', '@'))

                        type_col_index = _find_list_index(column_headers, "type")
                        tags_col_index = _find_list_index(column_headers, "tags")
                        location_col_index = _find_list_index(column_headers, "location")
                        specific_location_col_index = _find_list_index(column_headers, "specific location")
                        quantity_col_index = _find_list_index(column_headers, "quantity")

                    else:
                        if len(row) < number_columns:
                            break

                        if id_col_index != -1:
                            item_id = row[id_col_index]
                            base_column_headers += 1
                        if name_col_index != -1:
                            item_name = row[name_col_index]
                            base_column_headers += 1
                        if description_col_index != -1:
                            item_description = row[description_col_index]
                            base_column_headers += 1
                        if type_col_index != -1:
                            base_column_headers += 1
                            item_type = row[type_col_index]
                        if tags_col_index != -1:
                            item_tags = row[tags_col_index]
                            base_column_headers += 1
                        if location_col_index != -1:
                            item_location = row[location_col_index]
                            base_column_headers += 1
                        if specific_location_col_index != -1:
                            item_specific_location = row[specific_location_col_index]
                            base_column_headers += 1
                        if quantity_col_index != -1:
                            item_quantity = row[quantity_col_index]
                            base_column_headers += 1
                        else:
                            item_quantity = 1

                        # add item types
                        add_new_user_itemtype(name=item_type, user_id=current_user.id)

                        location_id = None
                        if item_location is not None:
                            if item_location.strip() != "":
                                location_data_ = get_or_add_new_location(location_name=item_location,
                                                                         location_description=item_location,
                                                                         to_user_id=current_user.id)
                                location_id = location_data_.get("id")

                        tag_array = item_tags.split(",")

                        remaining_data_columns = number_columns - base_column_headers
                        for data_column_index in range(0, remaining_data_columns):
                            custom_field_name = column_headers[base_column_headers + data_column_index]
                            custom_field_value = row[base_column_headers + data_column_index]
                            custom_fields[custom_field_name] = custom_field_value

                        for t in range(len(tag_array)):
                            tag_array[t] = tag_array[t].strip()
                            tag_array[t] = tag_array[t].replace(" ", "@#$")

                        new_item_ = add_item_to_inventory(item_id=item_id, item_name=item_name,
                                                          item_desc=item_description,
                                                          item_type=item_type, item_quantity=item_quantity,
                                                          item_tags=tag_array, inventory_id=inventory_id,
                                                          item_location_id=location_id,
                                                          item_specific_location=item_specific_location,
                                                          user_id=current_user.id, custom_fields=custom_fields)

                        commit()

                        if new_item_["status"] == "error":
                            flash("Sorry, there was an error importing these things.")
                            return redirect(url_for(endpoint='items.items_with_username_and_inventory',
                                                    username=username, inventory_slug=inventory_slug).replace('%40',
                                                                                                              '@'))

                    line_count += 1

        return redirect(url_for(endpoint='items.items_with_username_and_inventory',
                                username=username, inventory_slug=inventory_slug).replace('%40', '@'))


@items_routes.route(rule='/items/move', methods=['POST'])
@login_required
def items_move():
    if request.method == 'POST':
        json_data = request.json
        item_ids = json_data['item_ids']
        username = json_data['username']
        to_inventory_id = json_data['to_inventory_id']
        move_type = int(json_data['move_type'])
        """
        link - just add new line in ItemInventory
        move - change inventory id in ItemInventory
        copy - duplicate item, add new line in ItemInventory
        """

        if move_type == 0:
            result = move_items(item_ids=item_ids, user=current_user, inventory_id=int(to_inventory_id))
            if result["status"] == "error":
                flash("There was a problem moving your things!")
        elif move_type == 1:
            result = copy_items(item_ids=item_ids, user=current_user, inventory_id=int(to_inventory_id))
            if result["status"] == "error":
                flash("There was a problem copying your things!")
        else:
            result = link_items(item_ids=item_ids, user=current_user, inventory_id=int(to_inventory_id))
            if result["status"] == "error":
                flash("There was a problem copying your things!")

        return redirect(url_for('item.items_with_username', username=username).replace('%40', '@'))


@items_routes.route(rule='/items/edit', methods=['POST'])
@login_required
def items_edit():
    if request.method == 'POST':
        json_data = request.json
        username = json_data['username']
        item_ids = json_data['item_ids']
        inventory_slug = json_data['inventory_slug']
        location_id = json_data['location_id']
        item_visibility = json_data['item_visibility']
        specific_location = json_data['specific_location']

        access_level = int(item_visibility)

        specific_location = bleach.clean(specific_location)
        if specific_location == "" or specific_location == "None":
            specific_location = None

        edit_items_locations(item_ids=item_ids, user=current_user, location_id=int(location_id),
                             specific_location=specific_location)
        if access_level != -1:
            change_item_access_level(item_ids=item_ids, access_level=access_level, user_id=current_user.id)

        return redirect(url_for('items.items_with_username_and_inventory',
                                username=username, inventory_slug=inventory_slug).replace('%40', '@'))


@items_routes.route('/items/save-pdf', methods=['POST'])
@login_required
def items_save_pdf():
    if request.method == 'POST':
        # json_data = request.json
        # inventory_slug = json_data['inventory_slug']
        # username = json_data['username']

        html = items_with_username_and_inventory(username="simon", inventory_slug="simon-s-inventory")

        config = pdfkit.configuration(
            wkhtmltopdf='C:\\Users\\simon clucas\\Downloads\\wkhtmltox-0.12.6-1.msvc2015-win64\\bin\\wkhtmltopdf.exe')

        pdf = pdfkit.from_string(html, False, configuration=config)
        response = make_response(pdf)
        response.headers["Content-Type"] = "application/pdf"
        response.headers["Content-Disposition"] = "inline; filename=output.pdf"
        return response


from sqlalchemy.ext.declarative import DeclarativeMeta

class AlchemyEncoder(json.JSONEncoder):

    def default(self, obj):
        if isinstance(obj.__class__, DeclarativeMeta):
            # an SQLAlchemy class
            fields = {}
            for field in [x for x in dir(obj) if not x.startswith('_') and x != 'metadata']:
                data = obj.__getattribute__(field)
                try:
                    json.dumps(data) # this will fail on non-encodable values, like other classes
                    fields[field] = data
                except TypeError:
                    fields[field] = None
            # a json-encodable dict
            return fields

        return json.JSONEncoder.default(self, obj)


@items_routes.route('/items/save', methods=['POST'])
@login_required
def items_save():
    inventory_slug = request.form.get("inventory_slug")

    filename = f"{current_user.username}_{inventory_slug}_export.json"

    request_params = _process_url_query(req_=request, inventory_user=current_user)

    inventory_list = []

    if inventory_slug == "all":
        user_inventories = get_user_inventories(current_user_id=current_user.id, requesting_user_id=current_user.id)
        for ui in user_inventories:
            inventory_list.append(ui["inventory_slug"])
    else:
        inventory_list = [inventory_slug]

    entire_json = []
    for inv_slug in inventory_list:

        inventory_id, inventory_, inventory_default_fields = _get_inventory(inventory_slug=inv_slug,
                                                                            logged_in_user_id=current_user.id,
                                                                            inventory_owner_id=current_user.id)

        data_dict, item_id_list = find_items_query(current_user.username,
                                                   current_user, inventory_id, request_params=request_params)

        dd = get_item_custom_field_data(user_id=current_user.id, item_list=item_id_list)

        field_set = set()

        for dn, dv in dd.items():
            dv_lower = [x.lower() for x in list(dv.keys())]
            field_set.update(dv_lower)

        headers_ = ["id", "name", "description", "tags", "type", "location", "specific location", "quantity"]
        headers_.extend(field_set)

        if inventory_ is not None:
            json_output = {
                "inventory": {"id": inventory_id, "name": inventory_.name, "description": inventory_.description,
                              "slug": inv_slug, "field_set": headers_, "items": []}}
        else:
            json_output = {
                "inventory": {"items": []}}

        for row in data_dict:
            item_ = row["item"]

            tmp_json = {
                "id": item_.id,
                "name": item_.name,
                "description": item_.description,
                "tags": [x.tag.replace("@#$", " ") for x in item_.tags],
                "types": row["types"],
                "location": row["location"],
                "specific_location": item_.specific_location,
                "quantity": item_.quantity
            }

            item_images = []
            #save images
            for img in item_.images:
                tmp_img_dict = {"is_main": False}
                img_path = os.path.join(app.config['UPLOAD_FOLDER'], img.image_filename)

                import base64

                with open(img_path, "rb") as image_file:
                    encoded_string = base64.b64encode(image_file.read())
                    raw = encoded_string.decode("utf-8")
                    tmp_img_dict["image_data"] = raw

                raw = raw.encode("utf-8")
                key = 'SOME_SECRET_KEY'.encode('utf-8')
                hashed = hmac.new(key, raw, hashlib.sha1)
                img_hmac_hash = base64.encodebytes(hashed.digest()).decode('utf-8')
                tmp_img_dict["image_hash"] = img_hmac_hash

                item_images.append(tmp_img_dict)

            tmp_json["images"] = item_images

            json_output["inventory"]["items"].append(tmp_json)

        entire_json.append(json_output)

    output = make_response(entire_json)
    output.headers["Content-Disposition"] = f"attachment; filename={filename}"
    output.headers["Content-types"] = "text/json"

    return output


@items_routes.route('/items')
@login_required
def items():
    username = current_user.username
    return redirect(url_for(endpoint='items.items_with_username', username=username).replace('%40', '@'))


@items_routes.route('/@<string:username>/items')
def items_with_username(username=None):
    """
    :param username: The username of the user whose items are to be retrieved.
    :return: A response containing the items belonging to the user with the specified username.
    """
    return items_with_username_and_inventory(username=username, inventory_slug="all")


@items_routes.route('/@<string:username>/<inventory_slug>')
def items_with_username_and_inventory(username=None, inventory_slug=None):
    inventory_owner_username = username
    inventory_owner = None
    inventory_owner_id = None

    user_is_authenticated = current_user.is_authenticated
    logged_in_user = None
    requested_user = None
    logged_in_user_id = None

    # remove spurious whitespace (if any)
    inventory_slug = inventory_slug.strip()

    user_locations_ = None
    inventory_templates = None
    users_in_this_inventory = None

    if user_is_authenticated:
        logged_in_user = current_user
        user_locations_ = get_all_user_locations(user=logged_in_user)
        inventory_templates = get_user_templates(user=current_user)

        if current_user == inventory_owner_username:
            inventory_owner = current_user
            inventory_owner_id = inventory_owner.id

    requested_username = username

    # if username is None:
    #     username = current_user.username
    # else:
    #     requested_user = find_user(username_or_email=username)
    #     if requested_user is not None:
    #         username = requested_user.username
    #     else:
    #         return render_template('404.html', message="Not found"), 404

    if logged_in_user is not None:
        logged_in_user_id = logged_in_user.id

    if requested_user is not None:
        requested_user_id = requested_user.id
    else:
        requested_user = current_user

    if user_is_authenticated:
        all_user_inventories = find_all_user_inventories(user=current_user)
    else:
        all_user_inventories = None

    if inventory_owner is None:
        inventory_owner = find_user_by_username(username=inventory_owner_username)
        if inventory_owner is not None:
            inventory_owner_id = inventory_owner.id

    inventory_id, inventory_, inventory_field_template = _get_inventory(inventory_slug=inventory_slug,
                                                                        inventory_owner_id=inventory_owner_id,
                                                                        logged_in_user_id=logged_in_user_id)

    if user_is_authenticated:
        users_in_this_inventory = get_users_for_inventory(inventory_id=inventory_id, current_user_id=current_user.id)

    if inventory_ is None and inventory_slug != "all":
        return render_template('404.html', message="No such inventory"), 404

    if not user_is_authenticated and inventory_.access_level == __PRIVATE:
        return render_template('404.html', message="No such inventory"), 404

    if not user_is_authenticated and inventory_.access_level == __PUBLIC:
        is_inventory_owner = False
        inventory_access_level = 2
    else:

        # Get the user inventory entry
        # 0 - owner
        # 1 - view
        if inventory_slug != "all":
            user_inventory_ = get_user_inventory_by_id(user_id=current_user.id, inventory_id=inventory_id)
            if user_inventory_ is not None:
                inventory_access_level = user_inventory_[0].access_level
            else:
                return render_template('404.html', message="No inventory or no permissions to view inventory"), 404

            is_inventory_owner = (inventory_.owner_id == logged_in_user_id) or inventory_access_level == 0
        else:
            is_inventory_owner = True
            inventory_access_level = 0

    item_types_ = get_all_item_types()
    all_fields = dict(get_all_fields())

    request_params = _process_url_query(req_=request, inventory_user=requested_user)
    data_dict, item_id_list = find_items_query(requested_username=requested_username, logged_in_user=logged_in_user, inventory_id=inventory_id,
                                               request_params=request_params)

    inventory_id = -1
    if inventory_ is not None:
        inventory_id = inventory_.id

    if user_is_authenticated:
        current_username = current_user.username
    else:
        current_username = None

    return render_template('item/items.html',
                           inventory_id=inventory_id,
                           current_username=current_username,
                           username=username,
                           inventory=inventory_,
                           data_dict=data_dict,
                           item_types=item_types_,
                           inventory_templates=inventory_templates,
                           inventory_field_template=inventory_field_template,
                           tags=request_params["requested_tag_strings"],
                           all_fields=all_fields, is_inventory_owner=is_inventory_owner,
                           inventory_access_level=inventory_access_level,
                           user_locations=user_locations_,
                           item_specific_location=request_params["requested_item_specific_location"],
                           selected_item_type=request_params["requested_item_type_string"],
                           selected_item_location_id=request_params["requested_item_location_id"],
                           all_user_inventories=all_user_inventories, users_in_this_inventory=users_in_this_inventory,
                           user_is_authenticated=user_is_authenticated, inventory_slug=inventory_slug)


@items_routes.route('/items/<inventory_slug>')
def items_with_inventory(inventory_slug=None):
    return items_with_username_and_inventory(username=None, inventory_slug=inventory_slug)


def _get_inventory(inventory_slug: str, logged_in_user_id, inventory_owner_id):
    if inventory_slug == "default":
        inventory_slug_to_use = f"default-{current_user.username}"
    elif inventory_slug is None or inventory_slug == '':
        inventory_slug_to_use = 'all'
    else:
        inventory_slug_to_use = inventory_slug

    field_template_ = None

    if inventory_slug_to_use != "all":
        inventory_, user_inventory_ = find_inventory_by_slug(inventory_slug=inventory_slug_to_use,
                                                             inventory_owner_id=inventory_owner_id,
                                                             viewing_user_id=logged_in_user_id)
        if inventory_ is None:
            return None, None, None
        else:
            inventory_id = inventory_.id

            field_template_id_ = inventory_.field_template

            if field_template_id_ is not None:
                field_template_ = FieldTemplate.query.filter_by(id=field_template_id_).one_or_none()

    else:
        inventory_id = None
        inventory_ = None

    return inventory_id, inventory_, field_template_


def find_items_query(requested_username: str, logged_in_user, inventory_id: int, request_params):

    query_params = {
        'item_type': request_params["requested_item_type_id"],
        'item_location': request_params["requested_item_location_id"],
        'item_specific_location': request_params["requested_item_specific_location"],
        'item_tags': request_params["requested_tag_strings"],
    }

    items_ = find_items_new(inventory_id=inventory_id,
                            query_params=query_params,
                            requested_username=requested_username,
                            logged_in_user=logged_in_user)

    # items_ = find_items(inventory_id=inventory_id,
    #                     item_type=request_params["requested_item_type_id"],
    #                     item_location=request_params["requested_item_location_id"],
    #                     item_tags=request_params["requested_tag_strings"],
    #                     item_specific_location=request_params["requested_item_specific_location"],
    #                     request_user=requested_user,
    #                     logged_in_user=logged_in_user)

    item_id_list = []
    data_dict = []
    for i in items_:
        item_id_list.append(i[0].id)
        dat = {"item": i[0], "types": i[1], "location": i[2], "item_access_level": i[3]}

        data_dict.append(
            dat
        )

    return data_dict, item_id_list


def _process_url_query(req_, inventory_user):
    requested_item_type_string = req_.args.get('type')
    requested_tag_strings = req_.args.get('tags')
    requested_item_location_string = req_.args.get('location')
    requested_item_specific_location = req_.args.get('specific_location')

    # convert the text 'location_' to an id
    location_model = find_location_by_name(location_name=requested_item_location_string)
    if location_model is not None:
        requested_item_location_id = location_model.id
    else:
        requested_item_location_id = None

    # convert the text 'types' to an id
    if requested_item_type_string is not None:
        item_type_ = find_type_by_text(type_text=requested_item_type_string, user_id=inventory_user.id)
        if item_type_ is not None:
            requested_item_type_id = item_type_['id']
        else:
            requested_item_type_id = None
    else:
        requested_item_type_id = None

    if requested_item_type_string is None:
        requested_item_type_string = ""

    if requested_tag_strings is None:
        requested_tag_strings = ""

    return {
        "requested_tag_strings": requested_tag_strings,
        "requested_item_type_id": requested_item_type_id,
        "requested_item_type_string": requested_item_type_string,
        "requested_item_location_id": requested_item_location_id,
        "requested_item_location_string": requested_item_location_string,
        "requested_item_specific_location": requested_item_specific_location
    }


@items_routes.route(rule='/item/delete', methods=['POST'])
@login_required
def del_items():
    """
    Deletes items associated with a username.

    Parameters:
    - item_ids: A list of item IDs to delete. (Type: list)
    - username: The username associated with the items. (Type: str)

    Returns:
    - None
    """

    if request.json and all(key in request.json for key in ('item_ids', 'username')):
        json_data = request.json
        item_ids = json_data.get('item_ids')
        username = json_data.get('username')

        if item_ids is not None and username is not None:
            delete_items(item_ids=item_ids, user=current_user)
        else:
            flash("There was a problem deleting your things!")
            current_app.logger.error("Error deleting items - missing item_ids or username")

        # create redirect_url and ensure it has an '@' symbol before the user
        redirect_url = url_for(endpoint='items.items_with_username',
                               username=username).replace(__old='%40', __new='@')

        return redirect(redirect_url)
