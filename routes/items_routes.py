import hashlib
import hmac
import json
import os

import traceback
from json import JSONDecodeError

import bleach
import pdfkit
from flask import make_response, flash

from flask import Blueprint, render_template, redirect, url_for, request, current_app
from flask_login import login_required, current_user

from app import app
from routes.index_routes import profile
from database.database_functions import get_all_user_locations, \
    get_all_item_types, \
    find_type_by_text, find_inventory_by_slug, find_location_by_name, \
    add_item_to_inventory, find_all_user_inventories, delete_items, move_items, \
    get_all_fields, add_new_user_itemtype, \
    get_user_templates, get_item_custom_field_data, \
    get_users_for_inventory, get_user_inventory_by_id, get_or_add_new_location, edit_items_locations, \
    change_item_access_level, link_items, copy_items, find_items_new, __PUBLIC__, __PRIVATE__, \
    get_user_inventories, add_user_list, \
    get_item_fields, find_template_by_id, save_user_inventory_view, \
    get_related_items, get_all_item_ids_in_inventory, update_item_by_id, find_item_by_slug
from database.database_functions import find_user_by_username
from routes.items_loader import process_field_sets, process_images

from site_globals import _COPY_, _MOVE_

items_routes = Blueprint('items', __name__)


@items_routes.context_processor
def my_utility_processor():
    def item_tag_to_string(item_tag_list):
        tag_arr = []
        for tag in item_tag_list:
            tag_arr.append(tag.tag.replace("@#$", " "))
        return ",".join(tag_arr)

    return dict(item_tag_to_string=item_tag_to_string)


@items_routes.route('/items/load', methods=['POST'])
@login_required
def items_load():
    load_log = ""
    username = current_user.username

    try:
        inventory_slug_from_form = request.form.get("inventory_slug")
        inventory_slug_from_form = bleach.clean(inventory_slug_from_form)
        overwrite_or_not_from_form = bleach.clean(str(request.form.get("overwrite_or_not")))
        overwrite_or_not_from_form = True if overwrite_or_not_from_form == "on" else False

        if request.files:
            uploaded_file = request.files['file']  # This line uses the same variable and worked fine
            filepath = os.path.join(app.config['FILE_UPLOADS'], uploaded_file.filename)
            try:
                uploaded_file.save(filepath)
            except FileNotFoundError as fnfe:
                app.logger.error(f"Error saving uploaded file: {str(fnfe)} for user {current_user.username}")
                flash(message="Sorry, there was an error saving the uploaded file.")

            import mimetypes
            import_file_mimetype = mimetypes.MimeTypes().guess_type(filepath)[0]
            if "application/json" not in import_file_mimetype:
                flash("Uploaded file does not seem to be a JSON file.")
                return profile(username=username)

            try:
                with open(filepath, 'r') as f:
                    try:
                        data = json.load(f)
                    except JSONDecodeError as e:
                        flash("Uploaded file does not seem to be a valid JSON file.")
                        return profile(username=username)

                    for inventory_ in data:
                        inventory_data = inventory_.get("inventory", None)
                        if inventory_data is None:
                            break

                        inventory_slug_ = inventory_data.get("slug", None)
                        if inventory_slug_ is None:
                            continue

                        inventory_slug_ = bleach.clean(inventory_slug_)

                        # look for the inventory by slug
                        found_inv, found_userinv = find_inventory_by_slug(inventory_slug=inventory_slug_,
                                                                          inventory_owner_id=current_user.id,
                                                                          viewing_user_id=current_user.id)

                        if found_inv is None:
                            load_log += f"<br>Inventory {inventory_slug_} not found. Creating it...<br>"
                            inventory_name = bleach.clean(inventory_data.get("name"))
                            inventory_description = bleach.clean(inventory_data.get("description"))
                            inventory_type = int(bleach.clean(str(inventory_data.get("type", 1))))
                            inventory_access_level = int(bleach.clean(str(inventory_data.get("access_level", 1))))

                            found_inv, status, msg = add_user_list(name=inventory_name,
                                                                   description=inventory_description,
                                                                   inventory_type=inventory_type,
                                                                   slug=inventory_slug_,
                                                                   access_level=inventory_access_level,
                                                                   user_id=current_user.id)
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
                                item_id = int(bleach.clean(str(item.get("id"))))
                                if not overwrite_or_not_from_form:
                                    item_id = None
                                item_name = bleach.clean(item.get("name"))
                                item_slug = bleach.clean(item.get("slug"))
                                item_description = bleach.clean(item.get("description"))
                                item_type = item.get("type", "none")
                                if item_type is not None:
                                    item_type = bleach.clean(item_type)
                                item_quantity = int(bleach.clean(str(item.get("quantity"))))
                                item_tags = [bleach.clean(str(x)) for x in item.get("tags")]
                                item_location = bleach.clean(item.get("location"))
                                item_specific_location = bleach.clean(item.get("specific_location"))

                                # add item types
                                if item_type is not None and item_type != 'none':
                                    status, add_item_type_msg = add_new_user_itemtype(name=item_type,
                                                                                      user_id=current_user.id)

                                location_id = None
                                if item_location is not None:
                                    if item_location.strip() != "":
                                        location_data_ = get_or_add_new_location(location_name=item_location,
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

                                if overwrite_or_not_from_form:
                                    potential_item = find_item_by_slug(item_slug=item_slug, user_id=current_user.id)
                                    if potential_item is None:
                                        new_item_ = add_item_to_inventory(item_id=item_id, item_name=item_name,
                                                                          item_desc=item_description,
                                                                          item_type=item_type,
                                                                          item_quantity=item_quantity,
                                                                          item_tags=tag_array,
                                                                          inventory_id=inventory_id,
                                                                          item_location_id=location_id,
                                                                          item_specific_location=item_specific_location,
                                                                          user_id=current_user.id,
                                                                          custom_fields=custom_fields)
                                        item_count += 1
                                    else:
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
                                        new_item_ = update_item_by_id(item_data=new_item_data, item_id=int(item_id),
                                                                          user=current_user)
                                        load_log += f"&nbsp;&nbsp;&nbsp;&nbsp;... item {item_name} found and updated if different.<br>"
                                else:
                                    new_item_ = add_item_to_inventory(item_id=item_id, item_name=item_name,
                                                                      item_desc=item_description,
                                                                      item_type=item_type, item_quantity=item_quantity,
                                                                      item_tags=tag_array, inventory_id=inventory_id,
                                                                      item_location_id=location_id,
                                                                      item_specific_location=item_specific_location,
                                                                      user_id=current_user.id,
                                                                      custom_fields=custom_fields)
                                    item_count += 1

                                if new_item_["status"] != "error":
                                    # save images
                                    process_images(item, new_item_, item_id, current_user, app)

                                if new_item_["status"] == "error":
                                    flash("Sorry, there was an error importing these things.")
                                    return profile(username=username)


                        load_log += f"&nbsp;&nbsp;&nbsp;&nbsp;... imported {item_count} items into inventory {inventory_slug_}.<br>"


            except Exception as ex:
                app.logger.error(f"Error importing items: {str(ex)}")
    except Exception as e:
        traceback.print_exc()

    flash(message=load_log)
    return profile(username=username)





@items_routes.route(rule='/items/move', methods=['POST'])
@login_required
def items_move():
    _public_err_msg = "There was a problem moving your things!"
    json_data = request.json

    item_ids = json_data.get('item_ids', None)
    username = json_data.get('username', None)
    to_inventory_id = json_data.get('to_inventory_id', None)
    from_inventory_id = json_data.get('inventory_id', None)
    move_type = json_data.get('move_type', None)

    if not all(v is not None for v in [item_ids, username, to_inventory_id, from_inventory_id, move_type]):
        flash("There was a problem moving your things!")
        return redirect(url_for(endpoint='item.items_with_username', username=username).replace('%40', '@'))

    try:
        username = bleach.clean(username)
        to_inventory_id = bleach.clean(str(to_inventory_id))
        to_inventory_id = int(to_inventory_id)

        from_inventory_id = int(bleach.clean(str(from_inventory_id)))
        move_type = bleach.clean(move_type)
        move_type = int(move_type)
        item_ids = [bleach.clean(str(x)) for x in item_ids]
        item_ids = [int(x) for x in item_ids]
    except ValueError:
        flash(_public_err_msg)

    """
    link - just add new line in ItemInventory
    move - change inventory id in ItemInventory
    copy - duplicate item, add new line in ItemInventory
    """
    if len(item_ids) == 1 and item_ids[0] == -1:
        item_ids = get_all_item_ids_in_inventory(user_id = current_user.id, inventory_id = from_inventory_id)

    if move_type == _MOVE_:
        result = move_items(item_ids=item_ids, user=current_user, inventory_id=to_inventory_id)
        if result["status"] == "error":
            flash(_public_err_msg)
    elif move_type == _COPY_:
        result = copy_items(item_ids=item_ids, user=current_user, inventory_id=to_inventory_id)
        if result["status"] == "error":
            flash(_public_err_msg)
    else:
        result = link_items(item_ids=item_ids, user=current_user, inventory_id=to_inventory_id)
        if result["status"] == "error":
            flash(_public_err_msg)

    return redirect(url_for(endpoint='items.items_with_username', username=username).replace('%40', '@'))


@items_routes.route(rule='/items/edit', methods=['POST'])
@login_required
def items_edit():

    # get the form data
    json_data = request.json
    username = json_data.get('username', None)
    item_ids = json_data.get('item_ids', None)
    inventory_slug = json_data.get('inventory_slug', None)
    location_id = json_data.get('location_id', None)
    item_visibility = json_data.get('item_visibility', None)
    specific_location = json_data.get('specific_location', None)

    if None in [username, inventory_slug] or "" in [username, inventory_slug]:
        flash("There was a problem editing your things!")
        return redirect(url_for('items.items_with_username',
                                username=current_user.username).replace('%40', '@'))

    if None in [item_ids, location_id, item_visibility]:
        flash("There was a problem editing your things!")
        return redirect(url_for(endpoint='items.items_with_username_and_inventory',
                                username=username, inventory_slug=inventory_slug).replace('%40', '@'))

    try:
        # clean the form data
        username = bleach.clean(username)
        inventory_slug = bleach.clean(inventory_slug)
        item_ids = [int(bleach.clean(str(x))) for x in item_ids]
        location_id = int(bleach.clean(str(location_id)))
        item_visibility = bleach.clean(str(item_visibility))
        specific_location = bleach.clean(specific_location)
    except ValueError:
        flash("There was a problem editing your things!")
        return redirect(url_for('items.items_with_username_and_inventory',
            username=username, inventory_slug=inventory_slug).replace('%40', '@'))

    access_level = int(item_visibility)

    if specific_location == "" or specific_location == "None":
        specific_location = None

    status, msg = edit_items_locations(item_ids=item_ids, user=current_user, location_id=int(location_id),
                           specific_location=specific_location)
    if not status:
        flash("There was a problem editing your things!")
        return redirect(url_for('items.items_with_username_and_inventory',
                                username=username, inventory_slug=inventory_slug).replace('%40', '@'))

    if access_level != -1:
        change_item_access_level(item_ids=item_ids, access_level=access_level, user_id=current_user.id)

    return redirect(url_for(endpoint='items.items_with_username_and_inventory',
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
                    json.dumps(data)  # this will fail on non-encodable values, like other classes
                    fields[field] = data
                except TypeError:
                    fields[field] = None
            # a json-encodable dict
            return fields

        return json.JSONEncoder.default(self, obj)


@items_routes.route(rule='/items/manage', methods=['POST'])
@login_required
def items_manage():
    if request.method == 'POST':
        if request.form.get('export-items-btn', None) is not None:
            return items_save()
        else:
            return items_load()


@items_routes.route(rule='/items/save', methods=['POST'])
@login_required
def items_save():
    inventory_slug = request.form.get("inventory_slug")
    inventory_slug = bleach.clean(inventory_slug)

    filename = f"{current_user.username}_{inventory_slug}_export.json"

    request_params = _process_url_query(req_=request, inventory_user=current_user)

    inventory_list = []

    if inventory_slug == "all":
        user_inventories, status, msg = (
            get_user_inventories(current_user_id=current_user.id, requesting_user_id=current_user.id))
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

        dd, slugs, newdd = get_item_custom_field_data(user_id=current_user.id, item_list=item_id_list)

        # save the json items with a flag stating if they are just links to other items in the inventroy
        if inventory_default_fields is not None:
            inventory_field_template_name = inventory_default_fields.name
        else:
            inventory_field_template_name = None

        field_set = set()
        field_set2 = list()

        for dn, dv in dd.items():
            dv_lower = [x.lower() for x in list(dv.keys())]
            field_set.update(dv_lower)

        wewe = {}
        for dfdf, dvvv in newdd.items():

            for df in dvvv:
                wewe[df['slug']] = df
                d = 3


        headers_ = ["id", "name", "description", "tags", "type", "location", "specific location", "quantity"]
        headers_.extend(field_set)

        if inventory_ is not None:
            json_output = {
                "inventory": {"id": inventory_id, "name": inventory_.name, "description": inventory_.description,
                              "slug": inv_slug,
                              "custom_field_set": wewe,
                              "std_fields": headers_,
                              "field_set": {
                                  "name": inventory_field_template_name,
                                  "fields": list(field_set),
                                  "slugs": slugs
                              },
                              "items": []
                              }}
        else:
            json_output = {
                "inventory": {"items": []}}

        for row in data_dict:
            item_ = row["item"]
            item_custom_fields_ = get_item_fields(item_id=item_.id)

            related_items_ = get_related_items(item_id=item_.id)
            related_items_dict = {}
            if len(related_items_) > 0:
                for related_item in related_items_:
                    related_items_dict[related_item.item_id] = related_item.related_item_id

            ddd = {}
            for field_data in item_custom_fields_:
                field_ = field_data[0]
                item_field_ = field_data[1]
                template_field_ = field_data[2]
                ddd[field_.slug] = item_field_.value

            tmp_json = {
                "id": item_.id,
                "name": item_.name,
                "slug": item_.slug,
                "description": item_.description,
                "tags": [x.tag.replace("@#$", " ") for x in item_.tags],
                "type": row["types"],
                "location": row["location"],
                "specific_location": item_.specific_location,
                "quantity": item_.quantity,
                "is_link": row["item_is_link"],
                "custom_fields": ddd,
                "related_items": related_items_dict
            }

            current_user_id = str(current_user.id)
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

            json_output["inventory"]["items"].append(tmp_json)

        entire_json.append(json_output)

    output = make_response(entire_json)
    output.headers["Content-Disposition"] = f"attachment; filename={filename}"
    output.headers["Content-types"] = "text/json"

    return output


@items_routes.route('/items')
@login_required
def items():
    """
    Endpoint method for displaying items page for the current logged in user.

    This method requires user to be logged in before accessing. It redirects the user to the items page associated with their username.

    Parameters:
    - None

    Returns:
    - Redirect: Redirects the user to their personalized items page.

    """
    username = current_user.username
    return redirect(url_for(endpoint='items.items_with_username', list_username=username).replace('%40', '@'))


@items_routes.route('/@<string:list_username>/items')
def items_with_username(list_username=None):
    """
    :param list_username: The username of the user whose items are to be retrieved.
    :return: A response containing the items belonging to the user with the specified username.
    """
    return items_with_username_and_inventory(list_username=list_username, inventory_slug="all")


@items_routes.route(rule='/@<string:list_username>/<string:inventory_slug>', methods=['GET'])
def items_with_username_and_inventory(list_username: str=None, inventory_slug: str=None):

    list_username = bleach.clean(list_username.strip())
    inventory_slug = bleach.clean(inventory_slug.strip())

    user_is_authenticated = current_user.is_authenticated

    inventory_owner = None
    inventory_owner_id = None

    logged_in_user = None
    requested_user = None
    logged_in_user_id = None

    user_locations_ = None
    inventory_templates = None
    users_in_this_inventory = None

    if user_is_authenticated:
        logged_in_user = current_user
        logged_in_user_id = logged_in_user.id
        user_locations_ = get_all_user_locations(user_id=logged_in_user.id)
        inventory_templates = get_user_templates(user_id=current_user.id)

        if current_user == list_username:
            inventory_owner = current_user
            inventory_owner_id = inventory_owner.id


    if requested_user is not None:
        requested_user_id = requested_user.id
    else:
        requested_user = current_user

    request_params = _process_url_query(req_=request, inventory_user=requested_user)
    view = request_params.get("view", "list")  # 0 - list, 1 - grid

    if user_is_authenticated:
        all_user_inventories = find_all_user_inventories(user_id=current_user.id)
    else:
        all_user_inventories = None

    if inventory_owner is None:
        inventory_owner = find_user_by_username(username=list_username)
        if inventory_owner is not None:
            inventory_owner_id = inventory_owner.id

    inventory_id, inventory_, inventory_field_template = _get_inventory(inventory_slug=inventory_slug,
                                                                        inventory_owner_id=inventory_owner_id,
                                                                        logged_in_user_id=logged_in_user_id)

    if user_is_authenticated:
        users_in_this_inventory = get_users_for_inventory(inventory_id=inventory_id)
        if users_in_this_inventory is None:
            users_in_this_inventory = {}

    if inventory_ is None and inventory_slug != "all":
        return render_template('404.html', message="No such inventory"), 404

    if not user_is_authenticated and inventory_.access_level == __PRIVATE__:
        return render_template('404.html', message="No such inventory"), 404

    if not user_is_authenticated and inventory_.access_level == __PUBLIC__:
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

                if view is None:
                    user_inv_view_int = user_inventory_[0].view
                    if user_inv_view_int == 0:
                        view = "list"
                    else:
                        view = "grid"
                else:
                    _saved_view = user_inventory_[0].view
                    if _saved_view != view:
                        _new_view = 0 if view == "list" else 1
                        save_user_inventory_view(user_id=current_user.id,
                                                 inventory_id=inventory_id, view=_new_view)

            else:
                return render_template(template_name_or_list='404.html', message="No inventory or no permissions to view inventory"), 404

            is_inventory_owner = (inventory_.owner_id == logged_in_user_id) or inventory_access_level == 0
        else:
            is_inventory_owner = True
            inventory_access_level = 0

    item_types_ = get_all_item_types()
    all_fields = dict(get_all_fields())

    data_dict = {}
    inventory_id = -1
    if inventory_ is not None:
        inventory_id = inventory_.id

    if user_is_authenticated:
        current_username = current_user.username
    else:
        current_username = None

    if view is None:
        view = "list"


    return render_template(template_name_or_list='item/items.html',
                           inventory_id=inventory_id,
                           current_username=current_username,
                           list_username=list_username,
                           inventory_owner_id=inventory_owner_id,
                           inventory=inventory_,
                           data_dict=data_dict,
                           item_types=item_types_,
                           inventory_templates=inventory_templates,
                           inventory_field_template=inventory_field_template,
                           tags=request_params["requested_tag_strings"],
                           view=view,
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
    return items_with_username_and_inventory(list_username=None, inventory_slug=inventory_slug)


def _get_inventory(inventory_slug: str, logged_in_user_id: int, inventory_owner_id: int):
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
                field_template_ = find_template_by_id(template_id=field_template_id_)

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
        'page': request_params.get("page", 1),
    }

    items_ = find_items_new(inventory_id=inventory_id,
                            query_params=query_params,
                            requested_username=requested_username,
                            logged_in_user=logged_in_user)

    item_id_list = []
    data_dict = []
    for i in items_:

        if inventory_id is not None and logged_in_user is not None:
            item_ = i[0]
            types_ = i[1]
            location_ = i[2]
            item_access_level_ = i[3]
            item_is_link_ = i[4]
            user_inventory_ = i[5]
        else:
            item_ = i[0]
            types_ = i[1]
            location_ = i[2]
            item_access_level_ = i[3]
            item_is_link_ = i[4]
            user_inventory_ = None

        item_id_list.append(item_.id)
        dat = {"item": item_, "types": types_, "location": location_,
               "item_access_level": item_access_level_, "item_is_link": item_is_link_}

        data_dict.append(
            dat
        )

    return data_dict, item_id_list


def _process_url_query(req_, inventory_user):
    requested_item_type_string = req_.args.get('type')
    requested_tag_strings = req_.args.get('tags')
    requested_item_location_string = req_.args.get('location')
    view = req_.args.get('view')

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
        "requested_item_specific_location": requested_item_specific_location,
        "view": view
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
    user_is_authenticated = current_user.is_authenticated

    if request.json and all(key in request.json for key in ('item_ids', 'username')):
        json_data = request.json
        username = json_data.get('username')
        item_ids = json_data.get('item_ids')

        # sanitize inputs
        username = bleach.clean(username)
        item_ids = [int(bleach.clean(str(x))) for x in item_ids]

        inventory_id = json_data.get('inventory_id')
        if inventory_id == '':
            inventory_id = None
        else:
            inventory_id = int(bleach.clean(str(json_data.get('inventory_id'))))

        if item_ids is not None and username is not None:
            delete_items(item_ids=item_ids, user_id=current_user.id, inventory_id=inventory_id)
        else:
            flash("There was a problem deleting your things!")
            current_app.logger.error("Error deleting items - missing item_ids or username")

        # create redirect_url and ensure it has an '@' symbol before the user
        redirect_url = url_for(endpoint='items.items_with_username',
                               username=username).replace('%40', '@')
        return redirect(redirect_url)
