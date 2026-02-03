
import bleach

from flask import Blueprint, request, render_template
from flask_login import login_required, current_user

from routes.index_routes import profile
from services.thinglist_services import InventoryService, ItemService, LocationService, FieldService, \
    FieldTemplateService, ItemTypeService

user_admin_routes = Blueprint('user_admin', __name__)


@user_admin_routes.route('/user-admin', methods=['POST'])
@login_required
def admin():
    return render_template(template_name_or_list='admin/admin.html')


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
        ItemService.delete_all_user_items(user_id=current_user.id)
        InventoryService.delete_all_user_lists(user_id=current_user.id)
        LocationService.delete_user_locations(user_id=current_user.id)
        FieldService.delete_all_user_fields(user_id=current_user.id)
        ItemTypeService.delete_all_user_item_types(user_id=current_user.id)
        FieldTemplateService.delete_all_user_field_templates(user_id=current_user.id)
    else:
        if wipe_items:
            ItemService.delete_all_user_items(user_id=current_user.id)

        if wipe_lists:
            InventoryService.delete_all_user_lists(user_id=current_user.id)

    return profile(username=username)
