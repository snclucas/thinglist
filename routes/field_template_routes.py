import collections
import json

import bleach
from flask import Blueprint, render_template, redirect, url_for, request, abort, Response
from flask_login import login_required, current_user

from database_functions import find_template, add_new_template, update_template_by_id, get_user_templates, \
    get_all_fields, save_template_fields, get_user_template_by_id, delete_templates_from_db, \
    set_template_fields_orders, \
    get_template_fields_by_id
from models import FieldTemplate

field_template = Blueprint('field_template', __name__)


@field_template.route('/field-templates')
@login_required
def templates():
    return templates_with_username(username=current_user.username)


@field_template.route('/field-templates/<template_id>/sort', methods=['GET', 'POST'])
@login_required
def sort_template(template_id):
    if request.method == 'GET':
        all_fields = dict(get_all_fields())

        user_template_ = get_user_template_by_id(template_id=template_id, user_id=current_user.id)

        selected_field_ids = []
        if user_template_ is not None:
            for field_ in user_template_[0].fields:
                selected_field_ids.append(field_.id)

        sdds = get_template_fields_by_id(template_id=template_id)

        selected_field_ids = {}
        for entry in sdds:
            template_field_, field_ = entry

            selected_field_ids[template_field_.order] = {"name": field_.field, "id": field_.id}

        od = collections.OrderedDict(sorted(selected_field_ids.items()))

        return render_template('field_template/_sort_template_fields.html', field_template_name=user_template_[0].name,
                               username=current_user.username, all_fields=all_fields, user_template=user_template_,
                               selected_field_ids=selected_field_ids, template_id=template_id, fields=od)

    else:
        json_data = request.json
        row_order = json_data["row_order"]
        set_template_fields_orders(field_data=row_order, template_id=template_id, user_id=current_user.id)

        return json.dumps({'success': True}), 200, {'ContentType': 'application/json'}


@field_template.route('/field-templates/<int:template_id>')
@login_required
def template(template_id):
    """
    :param template_id: The ID of the field template to retrieve.
    :return: The rendered template or a 404 error message if the template does not exist or the user does not have access.
    """
    all_fields = dict(get_all_fields())

    user_template_ = get_user_template_by_id(template_id=template_id, user_id=current_user.id)

    if user_template_ is None:
        return render_template(template_name_or_list='404.html', message="No such template or you do not have access to this item"), 404

    selected_field_ids = [field_.id for field_ in user_template_[0].fields]

    return render_template(template_name_or_list='field_template/field_template.html', field_template_name=user_template_[0].name,
                           username=current_user.username, all_fields=all_fields, user_template=user_template_,
                           selected_field_ids=selected_field_ids, template_id=template_id)


@field_template.route('/@<username>/field-templates')
@login_required
def templates_with_username(username):
    all_fields = dict(get_all_fields())
    user_templates = get_user_templates(user=current_user)
    return render_template('field_template/field_templates.html',
                           name=current_user.username, templates=user_templates, all_fields=all_fields)


@field_template.route('/set-template-fields', methods=['POST'])
@login_required
def set_template_fields():
    if request.method == 'POST':
        request_xhr_key = request.headers.get('X-Requested-With')
        if request_xhr_key and request_xhr_key == 'XMLHttpRequest':
            json_data = request.json
            template_name = json_data['template_name']

            # sanitise template name
            template_name = bleach.clean(template_name)

            field_ids = json_data['field_ids']
            if len(field_ids) == 0:
                abort(Response("At least 1 field is required for the template", 400))

            field_ids = [str(x) for x in field_ids]

            save_template_fields(template_name=template_name, fields=field_ids, user=current_user)

    return redirect(url_for('field_template.templates'))


@field_template.route('/field-templates/delete', methods=['POST'])
@login_required
def delete_template():
    if request.method == 'POST':
        json_data = request.json
        template_ids = json_data['template_ids']
        delete_templates_from_db(user_id=current_user.id, template_ids=template_ids)
        return redirect(url_for('field_template.templates'))


@field_template.route('/field-templates/add', methods=['POST'])
@login_required
def add_template():
    if request.method == 'POST':
        template_id = request.form.get("template_id")
        template_name = request.form.get("template_name")
        template_fields = request.form.get("template_fields")

        new_template_data = {
            "id": template_id,
            "name": template_name,
            "fields": template_fields,
        }

        potential_template = find_template(template_id=int(template_id))

        if potential_template is None:
            template_ = FieldTemplate(name=new_template_data['name'], fields=new_template_data['fields'])
            add_new_template(name=template_name,
                             fields=template_fields, to_user=current_user)
        else:
            update_template_by_id(template_data=new_template_data, user=current_user)

        return redirect(url_for('field_template.templates'))
