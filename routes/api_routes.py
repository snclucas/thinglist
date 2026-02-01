import bleach
from flask import Blueprint, jsonify
from flask_login import login_required, current_user
from flask import request
from database.database_functions import get_all_user_tags, \
    find_items_new, find_all_my_items, count_all_item_ids_in_inventory, count_all_user_items, \
    get_all_user_and_system_item_types
from routes.items_routes import _get_inventory, _process_url_query
from site_globals import __DEFAULT__
from services.thinglist_api import UserService, LocationService, ItemTypeService

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
    user_itemtypes_ = ItemTypeService.get_all_user_item_types(user_id=current_user.id)
    return user_itemtypes_


@api_routes.route('/api/user-items', methods=['GET', 'POST'])
@login_required
def user_items():
    user_items_ = find_all_my_items(logged_in_user_id=current_user.id)
    ret_items = []
    for item_ in user_items_:
        ret_items.append(f"{item_.slug}")

    return ret_items



@api_routes.route('/api/items/@<string:username>/<inventory_slug>', methods=['GET', 'POST'])
#@login_required
def items(username=None, inventory_slug=None):
    user_is_authenticated = current_user.is_authenticated

    inventory_slug = bleach.clean(inventory_slug.strip())
    inventory_owner_username = bleach.clean(username)
    inventory_owner = None
    requested_user = username
    inventory_owner_id = None


    logged_in_user = None
    logged_in_user_id = None

    if user_is_authenticated:
        logged_in_user = current_user

        if current_user.username == inventory_owner_username:
            inventory_owner = current_user
            inventory_owner_id = inventory_owner.id

    if logged_in_user is not None:
        logged_in_user_id = logged_in_user.id

    if inventory_owner is None:
        inventory_owner = UserService.get_user_by_username(username=inventory_owner_username)
        if inventory_owner is not None:
            inventory_owner_id = inventory_owner.id

    requested_user = UserService.get_user_by_username(username=username)
    #if requested_user is None:
    #    requested_user = current_user

    if inventory_slug != 'all':
        inventory_id, inventory_, inventory_field_template = _get_inventory(inventory_slug=inventory_slug,
                                                                            inventory_owner_id=inventory_owner_id,
                                                                            logged_in_user_id=logged_in_user_id)
    else:
        inventory_id, inventory_ = None, None

    request_params = _process_url_query(req_=request, inventory_user=requested_user)

    search_query = request.args.get("search[value]", None)
    if search_query is not None:
        if len(search_query) < 3:
            search_query = None

    query_params = {
        'item_location': request_params.get("requested_item_location_id", None),
        'item_specific_location': request_params.get("item_specific_location", None),
        'item_tags': request_params.get("requested_tag_strings", None),
        'item_type': request_params.get("requested_item_type_id", None),
        'start': request.args.get("start", 0),
        'length': request.args.get("length", 50),
        'order_0': request.args.get("order[0][column]", None),
        'dir_0': request.args.get("order[0][dir]", None),
        'search': search_query,
    }

    #test_ = find_items_by_field_value(user_id=username, field_name="manufacturer", field_value="IBM")

    items_ = find_items_new(inventory_id=inventory_id,
                            query_params=query_params,
                            #requested_username=current_user.username,
                            requested_username=username,
                            logged_in_user=logged_in_user)

    if inventory_slug != 'all':
        num_items_in_inventory = count_all_item_ids_in_inventory(user_id=requested_user.id, inventory_id=inventory_id)
    else:
        num_items_in_inventory = count_all_user_items(user_id=requested_user.id)

    _already_found_list = []
    ret_items = []
    for row in items_:
        item_ = row[0]
        tag_arr = []
        is_link = row[4]
        for tag in item_.tags:
            tag_arr.append(tag.tag.replace("@#$", " "))

        location = {}
        if row[2] is not None:
            location["location"] = row[2]
            if item_.specific_location is not None:
                location["specific_location"] = item_.specific_location

        # process item list names
        _list_inventories = []
        for _inv in item_.inventories:
            _list_inventories.append("Default" if __DEFAULT__ in _inv.name else _inv.name)

        # used to remove duplicates resulting from item links
        if item_.slug not in _already_found_list:
            ret_items.append({
                "name": {"name": item_.name, "slug": item_.slug, "id": item_.id, "description": item_.description,
                         "is_link": is_link},
                "description": {"description": item_.description, "url": item_.url},
                "inventories": ", ".join(_list_inventories),
                "tags": tag_arr,
                "location": location,
                "type": row[1],
                "id": item_.id
            })
            _already_found_list.append(item_.slug)

    return jsonify({
        "data": ret_items,
        "recordsTotal": num_items_in_inventory,
        "recordsFiltered": num_items_in_inventory #len(ret_items)
    }, 200, 'application/json').json[0]


@api_routes.route('/api/locations', methods=['GET'])
@login_required
def locations():
    new_ret = []
    locations_ = LocationService.get_all_user_locations(user_id=current_user.id)
    loc_array = []
    for loc_ in locations_:
        loc_array.append(f"location: {loc_.name.lower()}")
        new_ret.append({"location": loc_.name.lower()})

    tags_ = get_all_user_tags(user_id=current_user.id)
    for tag_ in tags_:
        loc_array.append(f"tag: {tag_.tag.lower()}")
        new_ret.append({"tag": tag_.tag.lower()})

    item_types_ = get_all_user_and_system_item_types(user_id=current_user.id)
    for item_type_ in item_types_:
        loc_array.append(f"type: {item_type_.name.lower()}")
        new_ret.append({"type": item_type_.name.lower()})

    return jsonify(new_ret)
    #return loc_array
