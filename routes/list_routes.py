import json
import uuid

import bleach
from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_required, current_user

from app import app
from database_functions import get_user_inventories, delete_item_from_inventory, \
    add_item_to_inventory, \
    find_inventory_by_slug, \
    find_user_by_username, edit_inventory_data, \
    delete_list_by_id, add_user_to_inventory, delete_user_to_inventory, find_inventory_by_id, add_user_list, \
    regenerate_inventory_token, find_inventory_by_access_token, add_user_to_inventory_from_token, \
    get_user_public_lists, get_user_unlisted_item_count

from site_globals import __INVENTORY__, __LIST__, __URL_LIST__, __PUBLIC__, __PRIVATE__, __VIEWER__, __READ_ONLY__

inv = Blueprint('inv', __name__)

@inv.context_processor
def my_utility_processor():
    def item_tag_to_string(item_tag_list):
        tag_arr = []
        for tag in item_tag_list:
            tag_arr.append(tag.tag.replace("@#$", " "))
        return ",".join(tag_arr)
    return dict(item_tag_to_string=item_tag_to_string)


@inv.route('/lists', methods=['GET'])
@login_required
def lists():
    """
    Route to retrieve the inventories.

    Returns:
        The rendered HTML template with the following variables:
            - username (str): The current user's username.
            - inventories (list): The inventories for the current user.
            - user_is_authenticated (bool): Indicates if the user is authenticated.
            - number_inventories (int): The number of inventories minus one (excluding the 'hidden' default inventory).
    """
    user_is_authenticated: bool = current_user.is_authenticated
    user_invs, status, msg = get_user_inventories(current_user_id=current_user.id,
                                     requesting_user_id=current_user.id, access_level=-1)

    number_inventories: int = len(user_invs) - 1  # -1 to count for the 'hidden' default inventory
    unlisted_item_count: int = get_user_unlisted_item_count(user_id=current_user.id)

    return render_template(template_name_or_list='inventory/inventories.html',
                           username=current_user.username,
                           inventories=user_invs,
                           unlisted_item_count=unlisted_item_count,
                           user_is_authenticated=user_is_authenticated,
                           number_inventories=number_inventories)


@inv.route('/@<string:username>/lists')
def inventories_for_username(username):
    current_user_id = None
    requesting_user_id = None
    if current_user is not None:
        user_is_authenticated = current_user.is_authenticated
    else:
        user_is_authenticated = False

    user_ = find_user_by_username(username=username)

    if user_is_authenticated:
        current_user_id = current_user.id
        if username != current_user.username:

            if user_ is not None:
                requesting_user_id = user_.id
                username = user_.username
            else:
                return render_template(template_name_or_list='404.html', message="No such inventory"), 404
        else:
            requesting_user_id = current_user.id
            username = current_user.username

    user_invs, status, msg = get_user_inventories(current_user_id=current_user_id,
                                     requesting_user_id=requesting_user_id,
                                     access_level=-1)

    if user_is_authenticated and current_user_id == requesting_user_id:
        public_lists = []
    else:
        public_lists = get_user_public_lists(for_user_id=user_.id)

    lists_ = user_invs + public_lists

    if len(lists_) == 0:
        return render_template(template_name_or_list='404.html', message="No inventories"), 404

    number_inventories = len(lists_) - 1  # -1 to count for the 'hidden' default inventory

    unlisted_item_count = get_user_unlisted_item_count(user_id=user_.id)

    return render_template(template_name_or_list='inventory/inventories.html',
                           unlisted_item_count=unlisted_item_count,
                           inventories=lists_, username=username,
                           user_is_authenticated=user_is_authenticated,
                           number_inventories=number_inventories)


@inv.route('/list/<int:inventory_id>')
@login_required
def list_by_id(inventory_id: int):
    """
    Args:
        inventory_id: The ID of the inventory to list
    """
    inventory_, user_inventory_ = find_inventory_by_id(inventory_id=inventory_id, user_id=current_user.id)
    if inventory_ is not None:
        if inventory_.owner_id == current_user.id:
            return redirect(url_for(endpoint='items.items_with_username_and_inventory',
                                    username=current_user.username, inventory_slug=inventory_.slug))

    return render_template(template_name_or_list='404.html', message="No such inventory"), 404


@inv.route(rule='/list/add', methods=['POST'])
@login_required
def add_inventory():
    """

    Add new inventory based on user input.

    This method handles the POST request to add new inventory with the provided details. It validates the input data, sanitizes it, and then calls the 'add_user_inventory' function to add
    * the inventory to the database.

    Returns:
        Redirects to the inventory list page after successfully adding the new inventory. If the new inventory data is not added, it redirects back to the inventory list page.

    """
    inventory_name_ = request.form.get("inventory_name", None)
    inventory_description_ = request.form.get("inventory_description")
    if inventory_name_ is None or inventory_name_ == "":
        flash("Inventory name cannot be empty")
        return redirect(url_for('inv.inventories'))
    else:
        inventory_name_ = bleach.clean(inventory_name_)

    if inventory_description_ is None:
        inventory_description_ = ""
    inventory_description_ = bleach.clean(inventory_description_)

    # 1- inventory, 2 - list, 3- url list
    inventory_type_ = request.form.get("inventory_type", __INVENTORY__)
    inventory_type_ = int(bleach.clean(str(inventory_type_)))

    access_level_ = __PRIVATE__
    if "inventory_public" in request.form:
        access_level_ = __PUBLIC__

    show_default_fields = 1
    if "hide_default_fields" in request.form:
        show_default_fields = 0


    show_item_images = 1
    if "show_item_images" not in request.form:
        show_item_images = 0

    show_item_type = 1
    if "show_item_type" not in request.form:
        show_item_type = 0

    show_item_location = 1
    if "show_item_location" not in request.form:
        show_item_location = 0

    show_item_tags = 1
    if "show_item_tags" not in request.form:
        show_item_tags = 0

    show_item_url = 1
    if "show_item_url" not in request.form:
        show_item_url = 0

    new_inventory_data, status, msg = add_user_list(name=inventory_name_,
                                                    description=inventory_description_,
                                                    inventory_type=inventory_type_,
                                                    show_default_fields=show_default_fields,
                                                    show_item_images=show_item_images,
                                                    show_item_type=show_item_type,
                                                    show_item_location=show_item_location,
                                                    show_item_tags=show_item_tags,
                                                    show_item_url=show_item_url,
                                                    access_level=access_level_,
                                                    user_id=current_user.id)

    if new_inventory_data is None:
        return redirect(url_for('inv.lists'))

    return redirect(url_for(endpoint='inv.inventories_for_username', username=current_user.username))


@inv.route(rule='/list/delete', methods=['POST'])
@login_required
def del_inventory():
    if request.method == 'POST':
        json_data = request.json
        inventory_ids = json_data['inventory_ids']
        inventory_ids = [int(bleach.clean(str(x))) for x in inventory_ids]
        delete_list_by_id(inventory_ids=inventory_ids, user_id=current_user.id)

        return redirect(url_for('inv.lists'))



@inv.route(rule='/list/edit', methods=['POST'])
@login_required
def edit_inventory():

    inventory_id = request.form.get("inventory_id", None)
    if inventory_id is None:
        flash("Issue editing inventory")
        return redirect(url_for('inv.lists'))

    inventory_id = bleach.clean(inventory_id)

    inventory_name = request.form.get("inventory_name", None)
    inventory_description = request.form.get("inventory_description", "")
    inventory_description = bleach.clean(inventory_description)

    inventory_type = request.form.get("inventory_type", __INVENTORY__)
    inventory_type = bleach.clean(inventory_type)

    try:
        inventory_id = int(inventory_id)
        inventory_type = int(inventory_type)
    except ValueError:
        flash("Issue editing inventory")
        return redirect(url_for('inv.lists'))

    if inventory_name is None:
        flash("Issue editing inventory, inventory name cannot be blank")
        return redirect(url_for('inv.lists'))
    inventory_name = bleach.clean(request.form.get("inventory_name"))

    if inventory_type == __LIST__ or inventory_type == __INVENTORY__ or inventory_type == __URL_LIST__:
        inventory_type = int(bleach.clean(request.form.get("inventory_type")))
    else:
        flash("Issue editing inventory, inventory type needs to be 1 (inventory), 2 (list) or 3 (URL list)")
        return redirect(url_for('inv.lists'))

    access_level_ = __PRIVATE__
    if "inventory_public" in request.form:
        access_level_ = __PUBLIC__

    show_default_fields = 1
    if "edit_form_hide_default_fields" in request.form:
        show_default_fields = 0

    show_item_images = 1
    if "show_item_images" not in request.form:
        show_item_images = 0

    show_item_type = 1
    if "show_item_type" not in request.form:
        show_item_type = 0

    show_item_location = 1
    if "show_item_location" not in request.form:
        show_item_location = 0

    show_item_tags = 1
    if "show_item_tags" not in request.form:
        show_item_tags = 0

    show_item_url = 1
    if "show_item_url" not in request.form:
        show_item_url = 0

    edit_inventory_data(user_id=current_user.id, inventory_id=int(inventory_id),
                        name=inventory_name,
                        description=inventory_description,
                        inventory_type=inventory_type,
                        show_default_fields=show_default_fields,
                        show_item_images=show_item_images,
                        show_item_type=show_item_type,
                        show_item_location=show_item_location,
                        show_item_tags=show_item_tags,
                        show_item_url=show_item_url,
                        access_level=int(access_level_))

    return redirect(url_for('inv.lists'))


@inv.route(rule='/inventory/deleteuser', methods=['POST'])
@login_required
def delete_user_to_inv():
    inventory_id = request.json.get("inventory_id")
    user_id = request.json.get("user_id")

    inventory_id = bleach.clean(inventory_id)
    user_id = bleach.clean(user_id)

    try:
        inventory_id = int(inventory_id)
        user_id = int(user_id)
    except ValueError:
        flash("Issue deleting user from inventory")
        return redirect(url_for('inv.inventories'))

    result, msg = delete_user_to_inventory(inventory_id=inventory_id, user_to_delete_id=user_id)

    inventory_, user_inventory_ = find_inventory_by_id(inventory_id=inventory_id, user_id=current_user.id)

    if result:
        return redirect(url_for(endpoint='items.items_with_username_and_inventory',
                                inventory_slug=inventory_.slug, username=current_user.username).replace('%40', '@'))
    else:
        return redirect(url_for(endpoint='items.items_with_username_and_inventory',
                                inventory_slug=inventory_.slug, username=current_user.username).replace('%40', '@'))


@inv.route("/regenerate-token>", methods=["POST"])
@login_required
def regenerate_token():
    json_data = request.json
    inventory_id = json_data['inventory_id']
    new_token = uuid.uuid4().hex
    status, msg = regenerate_inventory_token(user_id=current_user.id,
                                        inventory_id=inventory_id,
                                        new_token=new_token)

    if status:
        return json.dumps({'success': True, "new-token": new_token}), 200, \
               {'ContentType': 'application/json'}
    else:
        app.logger.error(msg)
        return json.dumps({'success': False, "new-token": ""}), 400, \
               {'ContentType': 'application/json'}


@inv.route('/list/access', methods=['POST'])
@login_required
def register_for_inventory_access():
    if request.method == 'POST':
        access_token = bleach.clean(request.form.get("access_token"))

        inventory_ = find_inventory_by_access_token(access_token=access_token)
        if inventory_ is not None:
            result = add_user_to_inventory_from_token(inventory_id=inventory_.id, user_to_add=current_user,
                                                      added_user_access_level=__VIEWER__)
            flash(f"Inventory {inventory_.name} added...")
        else:
            flash("Invalid inventory access token")

    return redirect(url_for('inv.lists'))




@inv.route('/list/add-user', methods=['POST'])
@login_required
def add_user_to_list():
    """

    Add a user to a specified inventory list.

    Endpoint: /list/add-user
    Method: POST
    Requires login

    Parameters:
    - inventory_id: ID of the inventory list to add the user to
    - access_level: Access level for the user (default value: __READ_ONLY__)
    - user_to_add: Username of the user to add to the list

    Returns:
    - Redirects to 'inv.lists' if user is successfully added to the list
    - Redirects to 'inv.lists' with a flash message if there is an issue adding the user to the list

    """
    _err_msg = "Issue adding user to this list"

    list_id = request.form.get("inventory_id", None)
    access_level = request.form.get("access_level", __READ_ONLY__)
    user_to_add = request.form.get("user_to_add", None)

    if list_id is None or user_to_add is None:
        flash(_err_msg)
        app.logger.error(f"Issue adding user. (User from form: {user_to_add}) to list (list ID: {list_id}). [list_id or user_to_add is None]")
        return redirect(url_for('inv.lists'))

    list_id = bleach.clean(list_id)
    access_level = bleach.clean(access_level)
    user_to_add = bleach.clean(user_to_add)

    # Get rid of the '@' symbol if it's in the username
    if '@' in user_to_add:
        user_to_add = user_to_add.replace('@', '')

    try:
        list_id = int(list_id)
        access_level = int(access_level)
    except ValueError:
        flash(_err_msg)
        app.logger.error(f"Issue adding user. (User from form: {user_to_add}) to list (list ID: {list_id}). [Error converting list_id or access_level to int]")
        return redirect(url_for('inv.lists'))

    result, message = add_user_to_inventory(inventory_id=list_id, current_user_id=current_user.id,
                                   user_to_add_username=user_to_add,
                                   added_user_access_level=access_level)

    if result:
        return redirect(url_for('inv.lists'))
    else:
        flash(_err_msg)
        app.logger.error(f"Issue adding user. (User from form: {user_to_add}) to list (list ID: {list_id}). [{message}]")
        return redirect(url_for('inv.lists'))


@inv.route('/list/@<username>/<inventory_slug>/delete/<item_id>', methods=['POST'])
@login_required
def delete_from_inventory(username: str, inventory_slug: str, item_id):
    inventory_, user_inventory_ = find_inventory_by_slug(inventory_slug=inventory_slug,
                                                         inventory_owner_id=current_user.id)
    delete_item_from_inventory(user=current_user, inventory_id=int(inventory_.id), item_id=int(item_id))
    return redirect(url_for(endpoint='inv.inventory_by_slug', username=username, inventory_slug=inventory_.slug))


@inv.route('/list/additem', methods=['POST'])
@login_required
def add_to_inventory():

    item_name = bleach.clean(request.form.get("name"))
    item_description = bleach.clean(request.form.get("description"))
    inventory_id = request.form.get("inventory_id")
    item_quantity = request.form.get("quantity", 1)
    item_url = request.form.get("url", "")
    item_url = bleach.clean(item_url)

    username = request.form.get("username").lower()
    inventory_slug = request.form.get("inventory_slug").lower()
    item_type = request.form.get("type").lower()
    if item_type == '':
        item_type = 'none'
    item_location = request.form.get("location_id").lower()
    item_specific_location = bleach.clean(request.form.get("specific_location")).lower()
    item_tags = bleach.clean(request.form.get("tags")).lower()
    item_tags = item_tags.lower().split(",")

    item_custom_fields = dict(request.form)
    to_remove = ['username', 'name', 'id', 'description', 'inventory_id', 'location_id',
                 'inventory_slug', 'specific_location', 'csrf_token', 'tags', 'type']
    for field in to_remove:
        del item_custom_fields[field]

    add_item_to_inventory(item_name=item_name, item_desc=item_description, item_type=item_type,
                          item_tags=item_tags, item_quantity=item_quantity, item_url=item_url,
                          item_location_id=int(item_location), item_specific_location=item_specific_location,
                          inventory_id=inventory_id, user_id=current_user.id,
                          custom_fields=item_custom_fields)

    if inventory_id == '' or inventory_slug == '' or inventory_id is None or inventory_slug is None:
        return redirect(url_for(endpoint='items.items_with_username',
                                username=username))
    else:
        return redirect(url_for(endpoint='items.items_with_username_and_inventory',
                                list_username=username, inventory_slug=inventory_slug))
