import collections
import json

import bleach
from flask import Blueprint, render_template, redirect, url_for, request, abort, Response, flash
from flask_login import login_required, current_user

from database_functions import find_template, add_new_template, update_template_by_id, get_user_templates, \
    get_all_fields, save_template_fields, get_user_template_by_id, delete_templates_from_db, \
    set_template_fields_orders, \
    get_template_fields_by_id, get_all_fields_include_users, get_all_user_fields, delete_fields_from_db, add_field
from models import FieldTemplate

field_routes = Blueprint('field', __name__)


@field_routes.route('/fields')
@login_required
def fields():
    return fields_with_username(username=current_user.username)

@field_routes.route('/@<username>/fields')
@login_required
def fields_with_username(username):
    user_fields = list(get_all_user_fields(user_id=current_user.id))
    return render_template(template_name_or_list='fields/fields.html',
                           name=current_user.username, fields=user_fields)

@field_routes.route('/fields/delete', methods=['POST'])
@login_required
def delete_field():
    if request.method == 'POST':
        json_data = request.json
        field_ids = json_data['field_ids']
        delete_fields_from_db(user_id=current_user.id, field_ids=field_ids)
        return redirect(url_for('field_routes.fields'))


@field_routes.route('/fields/add', methods=['POST'])
@login_required
def add_new_field():
    if request.method == 'POST':
        field_name = request.form.get("field_name")
        field_name = bleach.clean(field_name)
        field, success = add_field(field_name=field_name, user_id=current_user.id)
        if not success:
            flash("Failed to add new field")
        return redirect(url_for('field.fields'))
