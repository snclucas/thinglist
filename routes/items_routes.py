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
from services.field_service import FieldService
from services.field_template_service import FieldTemplateService
from services.inventory_service import InventoryService
from services.item_service import ItemService
from services.item_type_service import ItemTypeService
from services.location_service import LocationService
from services.user_service import UserService

from site_globals import _COPY_, _MOVE_, __ALL__, __DEFAULT__, __NOT_FOUND__, __PRIVATE__, __PUBLIC__
from user_save_load import items_save, items_load

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
def items_load_endpoint():
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
                        app.logger.error(f"Error loading JSON file: {str(e)}")
                        flash("Uploaded file does not seem to be a valid JSON file.")
                        return profile(username=username)

                    items_load(json_data=data, current_user=current_user, overwrite_or_not=overwrite_or_not_from_form,
                               inventory_slug_from_form=inventory_slug_from_form)

            except Exception as ex:
                app.logger.error(f"Error importing items: {str(ex)}")
    except Exception as ex:
        app.logger.error(f"Error importing items: {str(ex)}")
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
        item_ids = InventoryService.get_all_item_ids_in_inventory(user_id=current_user.id,
                                                                  inventory_id=from_inventory_id)

    if move_type == _MOVE_:
        result = ItemService.move_items(item_ids=item_ids, user=current_user, inventory_id=to_inventory_id)
        if result["status"] == "error":
            flash(_public_err_msg)
    elif move_type == _COPY_:
        result = ItemService.copy_items(item_ids=item_ids, user=current_user, inventory_id=to_inventory_id)
        if result["status"] == "error":
            flash(_public_err_msg)
    else:
        result = ItemService.link_items(item_ids=item_ids, user_id=current_user.id, inventory_id=to_inventory_id)
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

    status, msg = ItemService.edit_items_locations(item_ids=item_ids, user=current_user, location_id=int(location_id),
                                       specific_location=specific_location)
    if not status:
        flash("There was a problem editing your things!")
        return redirect(url_for('items.items_with_username_and_inventory',
                                username=username, inventory_slug=inventory_slug).replace('%40', '@'))

    if access_level != -1:
        ItemService.change_item_access_level(item_ids=item_ids, access_level=access_level, user_id=current_user.id)

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




@items_routes.route(rule='/items/manage', methods=['POST'])
@login_required
def items_manage():
    if request.form.get('export-items-btn', None) is not None:
        return items_save_endpoint()
    else:
        return items_load_endpoint()


@items_routes.route(rule='/items/save', methods=['POST'])
@login_required
def items_save_endpoint():
    try:

        # inventory slug from form, with a safe default
        raw_slug = request.form.get("inventory_slug", __ALL__)
        inventory_slug = bleach.clean(raw_slug or __ALL__)

        # create a safe filename
        from werkzeug.utils import secure_filename
        safe_slug = secure_filename(inventory_slug) or __ALL__
        filename = f"{secure_filename(current_user.username)}_{safe_slug}_export.json"

        request_params = _process_url_query(req_=request, inventory_user=current_user)

        status, json_text = items_save(inventory_slug, current_user, request_params)

        output = make_response(json_text)
        output.headers["Content-Disposition"] = f'attachment; filename="{secure_filename(filename)}"'
        output.mimetype = "application/json; charset=utf-8"
        return output

    except Exception as e:
        current_app.logger.exception("Unhandled error during items export")
        flash("There was a problem exporting your things!")
        return redirect(
            url_for(endpoint='items.items_with_username', list_username=current_user.username).replace('%40', '@'))


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


@items_routes.route(rule='/@<string:list_username>/items', methods=['GET'])
def items_with_username(list_username=None):
    """
    :param list_username: The username of the user whose items are to be retrieved.
    :return: A response containing the items belonging to the user with the specified username.
    """
    return items_with_username_and_inventory(list_username=list_username, inventory_slug=__ALL__)


@items_routes.route(rule='/@<string:list_username>/<string:inventory_slug>', methods=['GET'])
def items_with_username_and_inventory(list_username: str = None, inventory_slug: str = None):
    list_username = bleach.clean(list_username.strip())
    inventory_slug = bleach.clean(inventory_slug.strip())

    user_is_authenticated = current_user.is_authenticated

    inventory_owner = None
    inventory_owner_id = None

    requested_user = None
    logged_in_user_id = None

    users_in_this_inventory = None

    if user_is_authenticated:
        logged_in_user = current_user
        logged_in_user_id = logged_in_user.id

        if current_user.username == list_username:
            inventory_owner = current_user
            inventory_owner_id = inventory_owner.id

    if requested_user is not None:
        requested_user_id = requested_user.id
    else:
        requested_user = current_user

    request_params = _process_url_query(req_=request, inventory_user=requested_user)
    view = request_params.get("view", "list")  # 0 - list, 1 - grid

    if user_is_authenticated:
        all_user_inventories_meta = InventoryService.find_all_user_inventory_meta(user_id=current_user.id)
    else:
        all_user_inventories_meta = None

    if inventory_owner is None:
        inventory_owner = UserService.get_user_by_username(username=list_username)
        if inventory_owner is not None:
            inventory_owner_id = inventory_owner.id

    if inventory_slug == __DEFAULT__:
        _inventory_slug = f"{__DEFAULT__}-{list_username}"
    else:
        _inventory_slug = inventory_slug

    inventory_meta = InventoryService.find_inventory_meta_by_slug(inventory_slug=_inventory_slug,
                                                              inventory_owner_id=inventory_owner_id,
                                                              viewing_user_id=logged_in_user_id)

    inventory_ = None
    user_inventory_ = None

    if inventory_meta is None:
        # not found or not permitted
        if _inventory_slug != __ALL__:
            return render_template(template_name_or_list='404.html', message="No such inventory"), __NOT_FOUND__
    else:
        # meta exists; check permission and then fetch full Inventory only if needed
        inv_id = inventory_meta['inventory_id']
        inv_access = inventory_meta['inventory_access_level']
        ui_access = inventory_meta.get('user_access_level')

        # if not logged in and private, deny
        if not user_is_authenticated and inv_access == __PRIVATE__:
            return render_template(template_name_or_list='404.html', message="No such inventory"), __NOT_FOUND__

        # if logged in and user has no access and it's not public, deny
        if user_is_authenticated and ui_access is None and inv_access != __PUBLIC__:
            return render_template(template_name_or_list='404.html', message="No such inventory or no permissions to view inventory"), __NOT_FOUND__

        # allowed — load full inventory and user_inventory for later use
        inventory_, user_inventory_ = InventoryService.find_inventory_by_slug(inventory_slug=_inventory_slug,
                                                                              inventory_owner_id=inventory_owner_id,
                                                                              viewing_user_id=logged_in_user_id)

    field_template_ = None
    inventory_id = None

    if inventory_ is not None:
        inventory_id = inventory_.id

        field_template_id_ = inventory_.field_template

        if field_template_id_ is not None:
            field_template_ = FieldTemplateService.find_template_by_id(template_id=field_template_id_)

    if user_is_authenticated:
        users_in_this_inventory = InventoryService.get_users_for_inventory(inventory_id=inventory_id)
        if users_in_this_inventory is None:
            users_in_this_inventory = {}

    if inventory_ is None and inventory_slug != __ALL__:
        return render_template(template_name_or_list='404.html', message="No such inventory"), __NOT_FOUND__

    if not user_is_authenticated and inventory_.access_level == __PRIVATE__:
        return render_template(template_name_or_list='404.html', message="No such inventory"), __NOT_FOUND__

    if not user_is_authenticated and inventory_.access_level == __PUBLIC__:
        is_inventory_owner = False
        inventory_access_level = 2
    else:

        # Get the user inventory entry
        # 0 - owner
        # 1 - view
        if inventory_slug != __ALL__:
            user_inventory_ = InventoryService.get_user_inventory_by_id(user_id=current_user.id,
                                                                        inventory_id=inventory_id)
            if user_inventory_ is not None:
                inventory_access_level = user_inventory_.access_level

                if view is None:
                    user_inv_view_int = user_inventory_.view
                    if user_inv_view_int == 0:
                        view = "list"
                    else:
                        view = "grid"
                else:
                    _saved_view = user_inventory_.view
                    if _saved_view != view:
                        _new_view = 0 if view == "list" else 1
                        InventoryService.save_user_inventory_view(user_id=current_user.id,
                                                                  inventory_id=inventory_id, view=_new_view)

            else:
                return render_template(template_name_or_list='404.html',
                                       message="No inventory or no permissions to view inventory"), 404

            is_inventory_owner = (inventory_.owner_id == logged_in_user_id) or inventory_access_level == 0
        else:
            is_inventory_owner = True
            inventory_access_level = 0

    inventory_id = -1
    if inventory_ is not None:
        inventory_id = inventory_.id

    if user_is_authenticated:
        current_username = current_user.username
    else:
        current_username = None

    if view is None:
        view = "list"

    # collect all the data needed to populate the add items form
    item_types_ = ItemTypeService.get_all_user_and_system_item_types(user_id=inventory_owner_id)
    all_fields = FieldService.get_all_fields()

    user_locations_ = None
    inventory_templates = None

    if user_is_authenticated:
        user_locations_ = LocationService.get_all_user_locations(user_id=logged_in_user.id)
        inventory_templates = FieldTemplateService.get_user_templates(user_id=current_user.id)

    return render_template(template_name_or_list='items/items.html',
                           inventory_id=inventory_id,
                           current_username=current_username,
                           list_username=list_username,
                           inventory_owner_id=inventory_owner_id,
                           inventory=inventory_,
                           item_types=item_types_,
                           inventory_templates=inventory_templates,
                           inventory_field_template=field_template_,
                           tags=request_params["requested_tag_strings"],
                           view=view,
                           all_fields=all_fields, is_inventory_owner=is_inventory_owner,
                           inventory_access_level=inventory_access_level,
                           user_locations=user_locations_,
                           item_specific_location=request_params["requested_item_specific_location"],
                           selected_item_type=request_params["requested_item_type_string"],
                           selected_item_location_id=request_params["requested_item_location_id"],
                           all_user_inventories=all_user_inventories_meta, users_in_this_inventory=users_in_this_inventory,
                           user_is_authenticated=user_is_authenticated, inventory_slug=inventory_slug)


@items_routes.route('/items/<inventory_slug>')
def items_with_inventory(inventory_slug=None):
    return items_with_username_and_inventory(list_username=None, inventory_slug=inventory_slug)


def find_items_query(requested_username: str, logged_in_user, inventory_id: int, request_params):
    query_params = {
        'item_type': request_params["requested_item_type_id"],
        'item_location': request_params["requested_item_location_id"],
        'item_specific_location': request_params["requested_item_specific_location"],
        'item_tags': request_params["requested_tag_strings"],
        'page': request_params.get("page", 1),
    }

    items_ = ItemService.find_items_new(inventory_id=inventory_id,
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
            # user_inventory_ = i[5]
        else:
            item_ = i[0]
            types_ = i[1]
            location_ = i[2]
            item_access_level_ = i[3]
            item_is_link_ = i[4]
            # user_inventory_ = None

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
    location_model = LocationService.get_location_by_name(location_name=requested_item_location_string)
    if location_model is not None:
        requested_item_location_id = location_model.id
    else:
        requested_item_location_id = None

    # convert the text 'types' to an id
    if requested_item_type_string is not None:
        item_type_ = ItemTypeService.find_item_type_by_text(type_text=requested_item_type_string,
                                                            user_id=inventory_user.id)
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
    Expects JSON or form data with keys:
    - item_ids: list of item IDs (or JSON string)
    - username: username string
    - inventory_id: optional inventory id (empty string means default)
    """
    data = request.get_json(silent=True)
    if not data:
        # support form submissions (fields may be strings or repeated)
        form = request.form
        if not form:
            flash("There was a problem deleting your things!")
            current_app.logger.error("No JSON or form data provided to delete endpoint")
            return redirect(
                url_for(endpoint='items.items_with_username', list_username=current_user.username).replace('%40', '@'))
        # build data dict from form; allow comma-separated or repeated values for item_ids
        data = {}
        data['username'] = form.get('username')
        item_ids_form = form.getlist('item_ids') or form.get('item_ids')
        data['item_ids'] = item_ids_form
        data['inventory_id'] = form.get('inventory_id', "")
    # basic presence check
    if not data or 'item_ids' not in data or 'username' not in data:
        flash("There was a problem deleting your things!")
        current_app.logger.error("Missing required keys in delete request")
        return redirect(
            url_for(endpoint='items.items_with_username', list_username=current_user.username).replace('%40', '@'))

    # sanitize username
    username = bleach.clean(data.get('username') or "")
    # normalize item_ids to a list
    raw_item_ids = data.get('item_ids')
    if isinstance(raw_item_ids, str):
        try:
            raw_item_ids = json.loads(raw_item_ids)
        except Exception:
            # allow comma-separated string
            raw_item_ids = [x.strip() for x in raw_item_ids.split(',') if x.strip()]
    elif raw_item_ids is None:
        raw_item_ids = []

    # convert to ints, skipping invalid entries
    item_ids = []
    for x in raw_item_ids:
        try:
            item_ids.append(int(bleach.clean(str(x))))
        except (ValueError, TypeError):
            current_app.logger.warning("Skipping invalid item id when deleting: %r", x)

    # determine inventory_id
    inventory_id_raw = data.get('inventory_id', "")
    try:
        if inventory_id_raw == "" or inventory_id_raw is None:
            inventory_id = InventoryService.get_user_default_inventory_id(user_id=current_user.id)
        else:
            inventory_id = int(bleach.clean(str(inventory_id_raw)))
    except (ValueError, TypeError):
        inventory_id = InventoryService.get_user_default_inventory_id(user_id=current_user.id)

    if not item_ids:
        flash("There was a problem deleting your things!")
        current_app.logger.error("Error deleting items - no valid item_ids provided")
        return redirect(
            url_for(endpoint='items.items_with_username', list_username=username or current_user.username).replace(
                '%40', '@'))

    try:
        ItemService.delete_items(item_ids=item_ids, user_id=current_user.id, inventory_id=inventory_id)
    except Exception as e:
        flash("There was a problem deleting your things!")
        current_app.logger.error("Exception deleting items: %s", str(e))

    redirect_url = url_for(endpoint='items.items_with_username',
                           list_username=username or current_user.username).replace('%40', '@')
    return redirect(redirect_url)
