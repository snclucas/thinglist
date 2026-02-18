import json
import re
import uuid

import bleach
from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_required, current_user

from app import app
from services.inventory_service import InventoryService
from services.item_service import ItemService
from services.user_service import UserService

from site_globals import __INVENTORY__, __LIST__, __URL_LIST__, __PUBLIC__, __PRIVATE__, __VIEWER__, __READ_ONLY__, \
    __NOT_FOUND__, __OK__, __BAD_REQUEST__

from utils import CLEANR

inv = Blueprint('inv', __name__)

@inv.context_processor
def my_utility_processor():
    """
    Context processor to add utility functions to templates.

    Returns:
        dict: A dictionary containing utility functions for use in templates.
    """
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
    user_invs, status, msg = InventoryService.get_user_inventories(current_user_id=current_user.id,
                                     requesting_user_id=current_user.id, access_level=-1)

    number_inventories: int = len(user_invs)
    if not current_user.preferences.show_default_list:
        number_inventories: int = len(user_invs) - 1  # -1 to count for the 'hidden' default inventory

    unlisted_item_count: int = ItemService.get_user_unlisted_item_count(user_id=current_user.id)

    return render_template(template_name_or_list='list/lists.html',
                           list_username=current_user.username,
                           inventories=user_invs,
                           unlisted_item_count=unlisted_item_count,
                           user_is_authenticated=user_is_authenticated,
                           number_inventories=number_inventories)


@inv.route('/@<string:list_username>/lists')
def inventories_for_username(list_username: str):
    # sanitize and validate input
    safe_username = (bleach.clean(list_username or "")).strip()
    if not safe_username or len(safe_username) > 150:
        app.logger.warning("inventories_for_username: invalid username provided: %r", list_username)
        return render_template(template_name_or_list='404.html', message="No such inventory"), __NOT_FOUND__

    user_is_authenticated = current_user.is_authenticated
    current_user_id = None
    requesting_user_id = None
    user_ = None

    try:
        # fast-path: viewing your own lists
        if user_is_authenticated and safe_username == current_user.username:
            current_user_id = current_user.id
            requesting_user_id = current_user.id
            user_ = current_user
        else:
            # lookup the owner of the requested username
            user_ = UserService.get_user_by_username(username=safe_username)
            if user_ is None:
                app.logger.info("inventories_for_username: no user found for %r", safe_username)
                return render_template(template_name_or_list='404.html', message="No such inventory"), __NOT_FOUND__
            requesting_user_id = user_.id
            if user_is_authenticated:
                current_user_id = current_user.id
    except Exception as exc:
        app.logger.exception("inventories_for_username: error resolving user %r: %s", safe_username, exc)
        return render_template(template_name_or_list='404.html', message="Error loading inventories"), __NOT_FOUND__

    # fetch inventories (service may apply access checks based on the ids passed)
    try:
        user_invs, status, msg = InventoryService.get_user_inventories(
            current_user_id=current_user_id,
            requesting_user_id=requesting_user_id,
            access_level=-1
        )
    except Exception as exc:
        app.logger.exception("inventories_for_username: failed to load inventories for %r: %s", safe_username, exc)
        return render_template(template_name_or_list='404.html', message="Error loading inventories"), __NOT_FOUND__

    # only fetch public lists for others; avoid calling service with a None user_
    public_lists = []
    try:
        if not (user_is_authenticated and current_user_id == requesting_user_id):
            public_lists = InventoryService.get_user_public_lists(for_user_id=requesting_user_id)
    except Exception as exc:
        app.logger.exception("inventories_for_username: failed to load public lists for user %s: %s", requesting_user_id, exc)
        public_lists = []

    lists_ = (user_invs or []) + (public_lists or [])

    if not lists_:
        return render_template(template_name_or_list='404.html', message="No inventories"), __NOT_FOUND__

    number_inventories = max(0, len(lists_))
    if not current_user.preferences.show_default_list:
        # remove default inventory from lists_
        for l_ in lists_:
            if l_["is_default"]:
                lists_.remove(l_)
                break

        number_inventories -= 1

    try:
        unlisted_item_count = ItemService.get_user_unlisted_item_count(user_id=requesting_user_id)
    except Exception as exc:
        app.logger.exception("inventories_for_username: failed to get unlisted item count for %s: %s", requesting_user_id, exc)
        unlisted_item_count = 0

    return render_template(
        template_name_or_list='list/lists.html',
        unlisted_item_count=unlisted_item_count,
        inventories=lists_,
        list_username=safe_username,
        user_is_authenticated=user_is_authenticated,
        number_inventories=number_inventories
    )


@inv.route('/list/<int:inventory_id>')
@login_required
def list_by_id(inventory_id: int):
    """
    Args:
        inventory_id: The ID of the inventory to list
    """
    inventory_, user_inventory_ = InventoryService.find_inventory_by_id(inventory_id=inventory_id, user_id=current_user.id)
    if inventory_ is not None:
        if inventory_.owner_id == current_user.id:
            return redirect(url_for(endpoint='items.items_with_username_and_inventory',
                                    list_username=current_user.username, inventory_slug=inventory_.slug))

    return render_template(template_name_or_list='404.html', message="No such inventory"), __NOT_FOUND__


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

    if inventory_description_ is None or inventory_description_ == "":
        inventory_description_ = inventory_name_
    else:
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

    new_inventory_data, status, msg = InventoryService.add_user_list(name=inventory_name_,
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

    return redirect(url_for(endpoint='inv.inventories_for_username', list_username=current_user.username))


@inv.route(rule='/list/delete', methods=['POST'])
@login_required
def delete_list_endpoint():
    json_data = request.get_json(silent=True)
    if not json_data:
        flash("No data provided for deletion")
        app.logger.error("del_inventory: empty request.json")
        return redirect(url_for('inv.lists'))

    inventory_ids = json_data.get('inventory_ids')
    if not inventory_ids:
        flash("No inventories selected for deletion")
        app.logger.error("del_inventory: 'inventory_ids' missing or empty")
        return redirect(url_for('inv.lists'))

    cleaned_ids = set()
    for x in inventory_ids:
        try:
            cleaned = int(bleach.clean(str(x)))
            if cleaned > 0:
                cleaned_ids.add(cleaned)
        except (ValueError, TypeError) as e:
            app.logger.warning("del_inventory: invalid inventory id '%s' (%s)", x, e)

    if not cleaned_ids:
        flash("No valid inventory IDs provided")
        return redirect(url_for('inv.lists'))

    try:
        InventoryService.delete_lists_by_id(inventory_ids=list(cleaned_ids), user_id=current_user.id)
    except Exception as e:
        app.logger.exception("Error deleting inventories: %s", e)
        flash("Error deleting selected inventories")

    return redirect(url_for('inv.lists'))


# IMPROVED
@inv.route(rule='/list/edit', methods=['POST'])
@login_required
def edit_inventory():
    # helpers
    def safe_int(value, default=None):
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    MAX_NAME_LEN = 255
    MAX_DESC_LEN = 2000

    form = request.form

    # required id
    inventory_id_raw = form.get("inventory_id")
    if not inventory_id_raw:
        flash("Issue editing inventory")
        app.logger.error("edit_inventory: missing inventory_id")
        return redirect(url_for('inv.lists'))

    inventory_id = safe_int(bleach.clean(inventory_id_raw))
    if inventory_id is None or inventory_id <= 0:
        flash("Issue editing inventory")
        app.logger.error("edit_inventory: invalid inventory_id '%s'", inventory_id_raw)
        return redirect(url_for('inv.lists'))

    # fetch inventory and check permissions
    inventory_obj, user_inventory = InventoryService.find_inventory_by_id(inventory_id=inventory_id, user_id=current_user.id)
    if inventory_obj is None:
        flash("No such inventory")
        app.logger.warning("edit_inventory: inventory not found: %s", inventory_id)
        return redirect(url_for('inv.lists'))
    # ensure current user can edit; user_inventory may indicate access level
    if not (inventory_obj.owner_id == current_user.id or (user_inventory and user_inventory.can_edit())):
        flash("You do not have permission to edit this inventory")
        app.logger.warning("edit_inventory: permission denied for user %s on inventory %s", current_user.id, inventory_id)
        return redirect(url_for('inv.lists'))

    # name and description
    inventory_name = form.get("inventory_name")
    if not inventory_name:
        flash("Issue editing inventory, inventory name cannot be blank")
        app.logger.error("edit_inventory: blank inventory_name for inventory %s", inventory_id)
        return redirect(url_for('inv.lists'))
    inventory_name = bleach.clean(inventory_name).strip()[:MAX_NAME_LEN]

    inventory_description = form.get("inventory_description", "")
    inventory_description = bleach.clean(inventory_description).strip()[:MAX_DESC_LEN]

    # inventory type
    inventory_type_raw = form.get("inventory_type", str(__INVENTORY__))
    inventory_type = safe_int(bleach.clean(inventory_type_raw))
    allowed_types = {__INVENTORY__, __LIST__, __URL_LIST__}
    if inventory_type not in allowed_types:
        flash("Issue editing inventory, inventory type must be valid")
        app.logger.error("edit_inventory: invalid inventory_type '%s' for inventory %s", inventory_type_raw, inventory_id)
        return redirect(url_for('inv.lists'))

    # access level (limit to expected values)
    access_level_ = __PRIVATE__ if "inventory_public" not in form else __PUBLIC__
    if access_level_ not in (int(__PRIVATE__), int(__PUBLIC__)):
        access_level_ = __PRIVATE__

    # boolean flags as 0/1
    show_default_fields = 0 if "edit_form_hide_default_fields" in form else 1
    show_item_images = 1 if "show_item_images" in form else 0
    show_item_type = 1 if "show_item_type" in form else 0
    show_item_location = 1 if "show_item_location" in form else 0
    show_item_tags = 1 if "show_item_tags" in form else 0
    show_item_url = 1 if "show_item_url" in form else 0

    try:
        result = InventoryService.edit_inventory_data(
            user_id=current_user.id,
            inventory_id=inventory_id,
            name=inventory_name,
            description=inventory_description,
            inventory_type=inventory_type,
            show_default_fields=int(show_default_fields),
            show_item_images=int(show_item_images),
            show_item_type=int(show_item_type),
            show_item_location=int(show_item_location),
            show_item_tags=int(show_item_tags),
            show_item_url=int(show_item_url),
            access_level=int(access_level_)
        )
        # if service returns status or raises, handle accordingly
        if result is False or result is None:
            flash("Failed to update inventory")
            app.logger.error("edit_inventory: InventoryService.edit_inventory_data returned failure for %s", inventory_id)
    except Exception as exc:
        app.logger.exception("edit_inventory: exception updating inventory %s: %s", inventory_id, exc)
        flash("Error updating inventory")

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

    result, msg = InventoryService.delete_user_to_inventory(inventory_id=inventory_id, user_to_delete_id=user_id)

    inventory_, user_inventory_ = InventoryService.find_inventory_by_id(inventory_id=inventory_id, user_id=current_user.id)

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
    status, msg = InventoryService.regenerate_inventory_token(user_id=current_user.id,
                                        inventory_id=inventory_id,
                                        new_token=new_token)

    if status:
        return json.dumps({'success': True, "new-token": new_token}), __OK__, \
               {'ContentType': 'application/json'}
    else:
        app.logger.error(msg)
        return json.dumps({'success': False, "new-token": ""}), __BAD_REQUEST__, \
               {'ContentType': 'application/json'}


@inv.route('/list/access', methods=['POST'])
@login_required
def register_for_inventory_access():

    access_token = bleach.clean(request.form.get("access_token"))

    inventory_ = InventoryService.get_inventory_by_access_token(access_token=access_token)
    if inventory_ is not None:
        result = InventoryService.add_user_to_inventory_from_token(inventory_id=inventory_.id, user_to_add=current_user,
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

    result, message = InventoryService.add_user_to_inventory(inventory_id=list_id, current_user_id=current_user.id,
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
    inventory_, user_inventory_ = InventoryService.find_inventory_by_slug(inventory_slug=inventory_slug,
                                                         inventory_owner_id=current_user.id)
    InventoryService.delete_item_from_inventory(user=current_user, inventory_id=int(inventory_.id), item_id=int(item_id))
    return redirect(url_for(endpoint='inv.inventory_by_slug', username=username, inventory_slug=inventory_.slug))


@inv.route('/list/additem', methods=['POST'])
@login_required
def add_to_list_endpoint():
    item_name = bleach.clean(request.form.get("name", "")).strip()
    if not item_name:
        flash("Item name cannot be empty")
        return redirect(url_for('inv.lists'))

    item_description_raw = request.form.get("description", "")
    item_description = bleach.clean(item_description_raw).strip()
    if item_description == "":
        item_description = None

    # Read raw values with string defaults to avoid type errors
    inventory_id_raw = request.form.get("inventory_id", "-1")
    item_quantity_raw = request.form.get("quantity", "1")
    item_location_raw = request.form.get("location_id", "-1")

    try:
        if inventory_id_raw == "":
            inventory_id = InventoryService.get_user_default_inventory_id(user_id=current_user.id)
        else:
            inventory_id = int(bleach.clean(str(inventory_id_raw)))
        item_quantity = int(bleach.clean(str(item_quantity_raw)))
        item_location = int(bleach.clean(str(item_location_raw)))
    except (ValueError, TypeError):
        flash("Issue adding item to inventory")
        return redirect(url_for('inv.lists'))

    item_url = bleach.clean(request.form.get("url", "")).strip()

    username = bleach.clean(request.form.get("username", "")).lower().strip()
    inventory_slug = bleach.clean(request.form.get("inventory_slug", "")).lower().strip()

    item_type_raw = bleach.clean(request.form.get("type", "")).strip().lower()
    item_type = item_type_raw if item_type_raw != "" else None

    item_specific_location = bleach.clean(request.form.get("specific_location", "")).lower().strip()

    tags_raw = bleach.clean(request.form.get("tags", "")).lower()
    item_tags = [re.sub(CLEANR, '', t).strip() for t in tags_raw.split(",") if t.strip()]

    to_remove = {'username', 'name', 'id', 'description', 'inventory_id', 'location_id',
                 'inventory_slug', 'specific_location', 'csrf_token', 'tags', 'type', 'quantity', 'url'}
    item_custom_fields = {k: v for k, v in request.form.items() if k not in to_remove}

    InventoryService.add_item_to_inventory(
        item_name=item_name,
        item_desc=item_description,
        item_type_name_or_id=item_type,
        item_tags=item_tags,
        item_quantity=item_quantity,
        item_url=item_url,
        item_location_id=item_location,
        item_specific_location=item_specific_location,
        inventory_id=inventory_id,
        user_id=current_user.id,
        custom_fields=item_custom_fields
    )

    if inventory_id <= 0 or not inventory_slug:
        return redirect(url_for(endpoint='items.items_with_username', list_username=username))
    else:
        return redirect(url_for(endpoint='items.items_with_username_and_inventory',
                                list_username=username, inventory_slug=inventory_slug))


