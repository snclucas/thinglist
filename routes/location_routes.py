import bleach
from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_required, current_user

from database.database_functions import get_user_locations_by_id, update_location_by_id, get_or_add_new_location, \
    delete_locations

from app import app
from services.thinglist_api import LocationService

location = Blueprint(name='location', import_name=__name__)


def get_form_data(key: str) -> str:
    return request.form.get(key)

@location.route(rule='/locations', methods=['GET'])
@login_required
def locations():
    """

    Retrieves the locations for the logged in user.

    This method handles the GET request for the '/locations' route, requiring the user to be logged in.
    It retrieves the locations specific to the current user and renders the 'location/locations.html' template
    with the user's username and locations displayed.

    """
    _user_locations = get_user_locations_by_id(user_id=current_user.id)
    return render_template(template_name_or_list='location/locations.html',
                           username=current_user.username, locations=_user_locations)


@location.route(rule='/location/delete', methods=['POST'])
@login_required
def del_locations():
    """
    Deletes the specified locations by IDs.

    :return: None
    """
    json_data = request.json
    location_ids = json_data["location_ids"]
    try:
        location_ids = [bleach.clean(x) for x in location_ids]
        location_ids = [int(x) for x in location_ids]
    except ValueError:
        flash("Something went wrong.")
        return redirect(url_for('location.locations'))

    _ret = delete_locations(user_id=current_user.id, location_ids=location_ids)

    if not _ret["success"]:
        flash("Something went wrong.")
    return redirect(url_for('location.locations'))


@location.route(rule='/location/add', methods=['POST'])
@login_required
def add_location():
    """
    Add a location to the system.

    :return: None
    """

    _location_id = get_form_data("location_id")
    if _location_id is None or _location_id == "":
        app.logger.error("Location ID is required to add a location.")
        flash("Something went wrong.")
        return redirect(url_for('location.locations'))

    _location_name =  get_form_data("location_name")
    if _location_name is None or _location_name == "":
        app.logger.error("Location name is required to add a location.")
        flash("Location name is required.")
        return redirect(url_for('location.locations'))

    _location_description = get_form_data("location_description")
    if _location_description is None or _location_description == "":
        _location_description = _location_name

    try:
        _location_id = bleach.clean(_location_id)
        _location_id_int = int(_location_id)
        _location_name = bleach.clean(_location_name)
        _location_description =  bleach.clean(_location_description)
    except ValueError as ve:
        flash("Something went wrong.")
        app.logger.error(ve)
        return redirect(url_for('location.locations'))

    new_location_data = {
        "id": _location_id_int,
        "name": _location_name,
        "description": _location_description,
    }

    potential_location = LocationService.get_location_by_id(location_id=_location_id_int)

    if potential_location is None:
        get_or_add_new_location(location_name=_location_name,
                                location_description=_location_description,
                                to_user_id=current_user.id)
    else:
        update_location_by_id(location_data=new_location_data, user=current_user)

    return redirect(url_for('location.locations'))
