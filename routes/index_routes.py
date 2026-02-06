from urllib.parse import quote

import bleach
from flask import Blueprint, render_template, request, redirect, url_for, abort
from flask_login import login_required, current_user

from app import app
from services.field_service import FieldService
from services.field_template_service import FieldTemplateService
from services.inventory_service import InventoryService
from services.item_service import ItemService
from services.item_type_service import ItemTypeService
from services.location_service import LocationService
from services.notification_service import NotificationService
from services.user_service import UserService

from site_globals import __BAD_REQUEST__

main = Blueprint('main', __name__)


@main.route('/')
def index():
    """
    Redirects the user to their profile if they are logged in, otherwise renders the index.html template.

    :return: A redirect response to the profile page if the user is logged in, otherwise the rendered index.html template.
    :rtype: werkzeug.wrappers.response.Response or flask.templating.render_template.rendered_template
    """
    # Ensure that 'current_user' is instantiated correctly, usually done through LoginManager
    if current_user and current_user.is_authenticated:
        return redirect(url_for(endpoint='main.profile', username=current_user.username))
    else:
        return render_template('index.html')


@app.context_processor
def utility_processor():
    def get_image_url(user_id, image_id):
        user_id = bleach.clean(str(user_id))
        image_id = bleach.clean(str(image_id))
        base_url = app.config['USER_IMAGES_BASE_URL']
        image = f"{base_url}/{user_id}/{image_id}"
        return image
    return dict(get_image_url=get_image_url)


@main.route('/testimages/<string:image_id>')
def testimages(image_id):
    return render_template(template_name_or_list='testimages.html', image_id=image_id)

@main.route('/images/<int:user_id>/<string:image_id>')
def images(user_id: int, image_id: str):
    """
    Redirect to the external user image URL.

    - Ensures `USER_IMAGES_BASE_URL` is configured.
    - Sanitizes inputs with `bleach`.
    - URL\-encodes path segments to avoid invalid URLs.
    - Returns a 302 redirect to the composed image URL.
    """
    base_url = app.config.get('USER_IMAGES_BASE_URL')
    if not base_url:
        abort(500, description='USER_IMAGES_BASE_URL is not configured')

    # Sanitize inputs
    user_id_clean = bleach.clean(str(user_id))
    image_id_clean = bleach.clean(str(image_id))

    # URL\-encode path components (no safe characters so everything is encoded appropriately)
    user_enc = quote(user_id_clean, safe='')
    image_enc = quote(image_id_clean, safe='')

    # Normalize base URL (avoid double slashes)
    base_url = base_url.rstrip('/')

    image_url = f"{base_url}/{user_enc}/{image_enc}"
    return redirect(image_url, code=302)

@main.route('/about')
def about():
    return render_template('about.html')

@main.route('/privacy-policy')
def privacy():
    return render_template('privacy_policy.html')


@main.route(rule='/delete-notification', methods=['POST'])
@login_required
def del_notification():
    """
    Deletes a notification by its ID.

    :return: None
    """
    json_data = request.json
    username = json_data['username']
    notification_id = json_data.get('notification_id')
    if notification_id is None:
        return "Missing 'notification_id'", __BAD_REQUEST__
    NotificationService.delete_notification_by_id(notification_id=notification_id, user=current_user)

    return redirect(url_for(endpoint='main.profile', username=username))


@main.route(rule='/@<username>', methods=['GET'])
@login_required
def profile(username):
    """
    :param username: The username of the profile being accessed.
    :return: The rendered profile page template with the user's information.
    """
    username = bleach.clean(username)
    user_is_authenticated = current_user.is_authenticated
    current_user_id = None
    requesting_user_id = None

    if username == current_user.username:

        # -1 for the default None item type
        num_item_types = len(ItemTypeService.get_all_user_item_types(user_id=current_user.id, string_list=False))
        num_items = ItemService.get_user_item_count(user_id=current_user.id)
        num_field_templates = len(FieldTemplateService.get_user_templates(user_id=current_user.id))
        num_user_locations = LocationService.get_number_user_locations(user_id=current_user.id)
        num_user_fields = len(FieldService.get_all_user_fields(user_id=current_user.id))

        if user_is_authenticated:
            current_user_id = current_user.id
            if username != current_user.username:
                user_ = UserService.get_user_by_username(username=username)
                if user_ is not None:
                    requesting_user_id = user_.id
            else:
                requesting_user_id = current_user.id

        user_inventories, status, msg = (
            InventoryService.get_user_inventories(current_user_id=current_user_id, requesting_user_id=requesting_user_id,
                                                access_level=-1))

        user_notifications = current_user.notifications
        # -1 to remove the default inventory
        return render_template(template_name_or_list='profile.html', name=current_user.username, num_items=num_items,
                               num_item_types=num_item_types, list_username=username, user_inventories=user_inventories,
                               num_field_templates=num_field_templates, num_user_locations=num_user_locations,
                               user_notifications=user_notifications, user_is_authenticated=user_is_authenticated,
                               num_inventories=len(list(user_inventories))-1, num_user_fields=num_user_fields)

    else:
        user_ = UserService.get_user_by_username(username=username)
        if user_ is not None:
            _user_preferences = user_.preferences
            if _user_preferences.public_profile:
                _users_public_lists = InventoryService.get_user_public_lists(for_user_id=user_.id)
                return render_template(template_name_or_list='users_public_profile.html')
            else:
                return redirect(url_for(endpoint='main.index'))
