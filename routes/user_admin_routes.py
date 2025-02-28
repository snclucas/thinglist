

import bleach

from flask import Blueprint, request
from flask_login import login_required, current_user

from database.database_functions import delete_all_user_items, delete_all_user_lists
from routes.index_routes import profile

user_admin_routes = Blueprint('user_admin', __name__)



@user_admin_routes.route('/user-admin/wipe', methods=['POST'])
@login_required
def wipe():
    username = current_user.username

    d = request.form

    wipe_items = bleach.clean(str(request.form.get("wipe_items")))
    wipe_items = True if wipe_items == "on" else False

    wipe_lists = bleach.clean(str(request.form.get("wipe_lists")))
    wipe_lists = True if wipe_lists == "on" else False

    wipe_locations = bleach.clean(str(request.form.get("wipe_locations")))
    wipe_locations = True if wipe_locations == "on" else False

    wipe_templates = bleach.clean(str(request.form.get("wipe_templates")))
    wipe_templates = True if wipe_templates == "on" else False

    if wipe_items and wipe_lists and wipe_locations and wipe_templates:
        # delete everything
        delete_all_user_items(user_id=current_user.id)
        delete_all_user_lists(user_id=current_user.id)

    else:
        if wipe_items:
            delete_all_user_items(user_id=current_user.id)

        if wipe_lists:
            delete_all_user_lists(user_id=current_user.id)


    return profile(username=username)


