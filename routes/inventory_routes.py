import json
import uuid

import bleach
from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_required, current_user

from database_functions import get_user_inventories, delete_item_from_inventory, \
    add_item_to_inventory, \
    get_items_for_inventory, find_inventory, get_all_item_types, find_inventory_by_slug, \
    find_user_by_username, edit_inventory_data, get_all_user_locations, \
    delete_inventory_by_id, add_user_to_inventory, delete_user_to_inventory, find_inventory_by_id, add_user_inventory, \
    send_inventory_invite, regenerate_inventory_token, find_inventory_by_access_token, add_user_to_inventory_from_token
from email_utils import send_email

inv = Blueprint('inv', __name__)


__OWNER = 0
__COLLABORATOR = 1
__VIEWER = 2
__PRIVATE = 0
__PUBLIC = 1
__READ_ONLY = 2


@inv.context_processor
def my_utility_processor():
    def item_tag_to_string(item_tag_list):
        tag_arr = []
        for tag in item_tag_list:
            tag_arr.append(tag.tag.replace("@#$", " "))
        return ",".join(tag_arr)
    return dict(item_tag_to_string=item_tag_to_string)


@inv.route('/inventories', methods=['GET'])
@login_required
def inventories():
    """
    Flask route to retrieve the inventories.

    Returns:
        The rendered HTML template with the following variables:
            - username (str): The current user's username.
            - inventories (list): The inventories for the current user.
            - user_is_authenticated (bool): Indicates if the user is authenticated.
            - number_inventories (int): The number of inventories minus one (excluding the 'hidden' default inventory).
    """
    user_is_authenticated = current_user.is_authenticated
    user_invs = get_user_inventories(current_user_id=current_user.id,
                                     requesting_user_id=current_user.id, access_level=-1)

    number_inventories = len(user_invs) - 1  # -1 to count for the 'hidden' default inventory

    return render_template(template_name_or_list='inventory/inventories.html', username=current_user.username, inventories=user_invs,
                           user_is_authenticated=user_is_authenticated, number_inventories=number_inventories)


@inv.route('/@<string:username>/inventories')
def inventories_for_username(username):
    current_user_id = None
    requesting_user_id = None
    if current_user is not None:
        user_is_authenticated = current_user.is_authenticated
    else:
        user_is_authenticated = False

    if user_is_authenticated:
        current_user_id = current_user.id
        if username != current_user.username:
            user_ = find_user_by_username(username=username)
            if user_ is not None:
                requesting_user_id = user_.id
                username = user_.username
            else:
                return render_template(template_name_or_list='404.html', message="No such inventory"), 404
        else:
            requesting_user_id = current_user.id
            username = current_user.username

    user_invs = get_user_inventories(current_user_id=current_user_id,
                                     requesting_user_id=requesting_user_id,
                                     access_level=-1)

    if len(user_invs) == 0:
        return render_template(template_name_or_list='404.html', message="No inventories"), 404

    number_inventories = len(user_invs) - 1  # -1 to count for the 'hidden' default inventory

    return render_template(template_name_or_list='inventory/inventories.html',
                           inventories=user_invs, username=username,
                           user_is_authenticated=user_is_authenticated,
                           number_inventories=number_inventories)


@inv.route('/inventory/<int:inventory_id>')
@login_required
def inventory(inventory_id: int):
    inventory_ = find_inventory(inventory_id=inventory_id)
    if inventory_ is not None:
        if inventory_.owner_id == current_user.id:
            return redirect(url_for(endpoint='items.items_with_username_and_inventory',
                                    username=current_user.username, inventory_slug=inventory_.slug))

    return render_template(template_name_or_list='404.html', message="No such inventory"), 404


@inv.route(rule='/inventory/add', methods=['POST'])
@login_required
def add_inventory():
    inventory_name_ = request.form.get("inventory_name")
    inventory_description_ = request.form.get("inventory_description")
    if inventory_name_ is None or inventory_name_ == "":
        return redirect(url_for('inv.inventories'))
    if inventory_description_ is None:
        inventory_description_ = ""

    inventory_type_ = request.form.get("inventory_type")
    inventory_type_ = int(bleach.clean(str(inventory_type_)))

    inventory_name_ = bleach.clean(inventory_name_)
    inventory_description_ = bleach.clean(inventory_description_)

    access_level_ = __PRIVATE
    if "inventory_public" in request.form:
        access_level_ = __PUBLIC

    new_inventory_data, msg = add_user_inventory(name=inventory_name_, description=inventory_description_,
                                                 inventory_type=inventory_type_,
                                                 access_level=access_level_, user_id=current_user.id)

    if new_inventory_data is None:
        return redirect(url_for('inv.inventories'))

    return redirect(url_for(endpoint='items.items_with_username_and_inventory', username=current_user.username,
                            inventory_slug=new_inventory_data["slug"]))


@inv.route(rule='/inventory/delete', methods=['POST'])
@login_required
def del_inventory():
    if request.method == 'POST':
        json_data = request.json
        inventory_ids = json_data['inventory_ids']
        delete_inventory_by_id(inventory_ids=inventory_ids, user_id=current_user.id)

        return redirect(url_for('inv.inventories'))


@inv.route(rule='/inventory/edit', methods=['POST'])
@login_required
def edit_inventory():
    if request.method == 'POST':
        inventory_id = bleach.clean(request.form.get("inventory_id"))
        inventory_name = bleach.clean(request.form.get("inventory_name"))
        inventory_description = bleach.clean(request.form.get("inventory_description"))
        inventory_type = int(bleach.clean(request.form.get("inventory_type")))

        access_level_ = __PRIVATE
        if "inventory_public" in request.form:
            access_level_ = __PUBLIC

        edit_inventory_data(user_id=current_user.id, inventory_id=int(inventory_id), name=inventory_name,
                            description=inventory_description, inventory_type=inventory_type,
                            access_level=int(access_level_))

        return redirect(url_for('inv.inventories'))


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
    except Exception:
        return redirect(url_for('inv.inventories'))

    result = delete_user_to_inventory(inventory_id=inventory_id, user_to_delete_id=user_id)

    inventory_ = find_inventory_by_id(inventory_id=inventory_id, user_id=current_user.id)

    if result:
        return redirect(url_for('items.items_with_username_and_inventory',
                                inventory_slug=inventory_.slug, username=current_user.username).replace('%40', '@'))
    else:
        return redirect(url_for('items.items_with_username_and_inventory',
                                inventory_slug=inventory_.slug, username=current_user.username).replace('%40', '@'))


@inv.route("/regenerate-token>", methods=["POST"])
@login_required
def regenerate_token():
    if request.method == 'POST':
        json_data = request.json
        inventory_id = json_data['inventory_id']
        new_token = uuid.uuid4().hex
        token_ = regenerate_inventory_token(user_id=current_user.id,
                                            inventory_id=inventory_id,
                                            new_token=new_token)

        if token_ is not None:
            return json.dumps({'success': True, "new-token": token_}), 200, \
                   {'ContentType': 'application/json'}
        else:
            return json.dumps({'success': False, "new-token": ""}), 400, \
                   {'ContentType': 'application/json'}


@inv.route('/inventory/access', methods=['POST'])
@login_required
def register_for_inventory_access():
    if request.method == 'POST':
        access_token = bleach.clean(request.form.get("access_token"))

        inventory_ = find_inventory_by_access_token(access_token=access_token)
        if inventory_ is not None:
            result = add_user_to_inventory_from_token(inventory_id=inventory_.id, user_to_add=current_user,
                                                      added_user_access_level=__READ_ONLY)
            flash(f"Inventory {inventory_.name} added...")
        else:
            flash("Invalid inventory access token")

    return redirect(url_for('inv.inventories'))




@inv.route('/inventory/adduser', methods=['POST'])
@login_required
def add_user_to_inv():
    if request.method == 'POST':
        inventory_id = bleach.clean(request.form.get("inventory_id"))
        access_level = bleach.clean(request.form.get("access_level"))
        user_to_add = bleach.clean(request.form.get("user_to_add"))

        if '@' in user_to_add:
            user_to_add = user_to_add.replace('@', '')

        try:
            inventory_id = int(inventory_id)
            access_level = int(access_level)
        except Exception:
            return redirect(url_for('inv.inventories'))

        result = add_user_to_inventory(inventory_id=inventory_id, current_user_id=current_user.id,
                                       user_to_add_username=user_to_add,
                                       added_user_access_level=access_level)

        if result:
            return redirect(url_for('inv.inventories'))
        else:
            return redirect(url_for('inv.inventories'))


@inv.route('/inventory/@<username>/<inventory_slug>/delete/<item_id>', methods=['POST'])
@login_required
def delete_from_inventory(username: str, inventory_slug, item_id):
    inventory_, user_inventory_ = find_inventory_by_slug(inventory_slug=inventory_slug,
                                                         inventory_owner_id=current_user.id)
    delete_item_from_inventory(user=current_user, inventory_id=int(inventory_.id), item_id=int(item_id))
    return redirect(url_for('inv.inventory_by_slug', username=username, inventory_slug=inventory_.slug))


@inv.route('/inventory/additem', methods=['POST'])
@login_required
def add_to_inventory():

    if request.method == 'POST':
        item_name = bleach.clean(request.form.get("name"))
        item_description = bleach.clean(request.form.get("description"))
        inventory_id = request.form.get("inventory_id")
        item_quantity = request.form.get("quantity")

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
                              item_tags=item_tags, item_quantity=item_quantity,
                              item_location_id=int(item_location), item_specific_location=item_specific_location,
                              inventory_id=inventory_id, user_id=current_user.id,
                              custom_fields=item_custom_fields)

        if inventory_id == '' or inventory_slug == '' or inventory_id is None or inventory_slug is None:
            return redirect(url_for('items.items_with_username',
                                    username=username))
        else:
            return redirect(url_for('items.items_with_username_and_inventory',
                                    username=username, inventory_slug=inventory_slug))
