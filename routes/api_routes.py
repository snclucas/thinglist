
from flask import Blueprint
from flask_login import login_required, current_user

from database_functions import get_all_itemtypes_for_user, get_all_user_locations, get_all_user_tags, find_items, \
    get_all_item_types, find_items_new, find_all_my_items

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


@api_routes.route('/api/locations', methods=['GET'])
@login_required
def locations():
    locations_ = get_all_user_locations(user=current_user)
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


# @api_routes.route('/api/locations', methods=['GET'])
# @login_required
# def user_locations():
#     user_locations_ = get_all_itemtypes_for_user(user_id=current_user.id)
#     return user_locations_
