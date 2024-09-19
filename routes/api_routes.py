import bleach
from flask import Blueprint
from flask_login import login_required, current_user
from flask import request
from database_functions import get_all_itemtypes_for_user, get_all_user_locations, get_all_user_tags, \
    get_all_item_types, find_items_new, find_all_my_items, find_user_by_username
from routes.items_routes import _get_inventory, _process_url_query

api_routes = Blueprint('api', __name__)


@api_routes.context_processor
def my_utility_processor():
    def item_tag_to_string(item_tag_list):
        tag_arr = []
        for tag in item_tag_list:
            tag_arr.append(tag.tag.replace("@#$", " "))
        return ",".join(tag_arr)

    return dict(item_tag_to_string=item_tag_to_string)


@api_routes.route('/api/item-types', methods=['GET'])
@login_required
def user_item_types():
    user_itemtypes_ = get_all_itemtypes_for_user(user_id=current_user.id)
    return user_itemtypes_


@api_routes.route('/api/user-items', methods=['GET', 'POST'])
@login_required
def user_items():
    user_items_ = find_all_my_items(logged_in_user=current_user)
    ret_items = []
    for item_ in user_items_:
        ret_items.append(f"{item_.slug}")

    return ret_items



@api_routes.route('/api/items/@<string:username>/<inventory_slug>', methods=['GET', 'POST'])
@login_required
def items(username=None, inventory_slug=None):
    inventory_slug = bleach.clean(inventory_slug.strip())
    inventory_owner_username = bleach.clean(username)
    inventory_owner = None
    requested_user = None
    inventory_owner_id = None

    user_is_authenticated = current_user.is_authenticated
    logged_in_user = None
    logged_in_user_id = None

    if user_is_authenticated:
        logged_in_user = current_user

        if current_user == inventory_owner_username:
            inventory_owner = current_user
            inventory_owner_id = inventory_owner.id

    if logged_in_user is not None:
        logged_in_user_id = logged_in_user.id

    if inventory_owner is None:
        inventory_owner = find_user_by_username(username=inventory_owner_username)
        if inventory_owner is not None:
            inventory_owner_id = inventory_owner.id

    if requested_user is None:
        requested_user = current_user

    inventory_id, inventory_, inventory_field_template = _get_inventory(inventory_slug=inventory_slug,
                                                                        inventory_owner_id=inventory_owner_id,
                                                                        logged_in_user_id=logged_in_user_id)

    request_params = _process_url_query(req_=request, inventory_user=requested_user)
    query_params = {
        'item_location': request_params.get("requested_item_location_id", None),
        'item_specific_location': request_params.get("item_specific_location", None),
        'item_tags': request_params.get("requested_tag_strings", None),
        'item_type': request_params.get("requested_item_type_id", None),
        'start': request.args.get("start", 0),
        'length': request.args.get("length", 50),
        'order_0': request.args.get("order[0][column]", None),
        'dir_0': request.args.get("order[0][dir]", None),
    }

    items_ = find_items_new(inventory_id=inventory_id,
                            query_params=query_params,
                            requested_username=current_user.username,
                            logged_in_user=current_user)

    ret_items = []
    for row in items_:
        item_ = row[0]
        tag_arr = []
        for tag in item_.tags:
            tag_arr.append(tag.tag.replace("@#$", " "))

        location = {}
        if row[2] is not None:
            location["location"] = row[2]
            if item_.specific_location is not None:
                location["specific_location"] = item_.specific_location

        ret_items.append({
            "name": {"name": item_.name, "slug": item_.slug},
            "slug": item_.slug,
            "description": item_.description,
            "tags": tag_arr,
            "location": location,
            "type": row[1],
            "id": item_.id
        })

    return {"data": ret_items}


@api_routes.route('/api/locations', methods=['GET'])
@login_required
def locations():
    locations_ = get_all_user_locations(user_id=current_user.id)
    loc_array = []
    for loc_ in locations_:
        loc_array.append(f"location:{loc_.name.lower()}")

    tags_ = get_all_user_tags(user_id=current_user.id)
    for tag_ in tags_:
        loc_array.append(f"tags:{tag_.tag.lower()}")

    item_types_ = get_all_item_types()
    for item_type_ in item_types_:
        loc_array.append(f"type:{item_type_.name.lower()}")

    return loc_array
