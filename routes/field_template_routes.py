import collections
import json

import bleach
from flask import Blueprint, render_template, redirect, url_for, request, abort, Response
from flask_login import login_required, current_user

from services.field_service import FieldService
from services.field_template_service import FieldTemplateService

from site_globals import __BAD_REQUEST__, __NOT_FOUND__

field_template = Blueprint('field_template', __name__)


@field_template.route('/field-templates')
@login_required
def templates():
    return templates_with_username(username=current_user.username)


@field_template.route('/field-templates/<int:template_id>/sort', methods=['GET', 'POST'])
@login_required
def sort_template(template_id):
    if request.method == 'GET':
        all_fields = FieldService.get_all_fields()

        user_template_ = FieldTemplateService.get_user_template_by_id(template_id=template_id, user_id=current_user.id)

        selected_field_ids = []
        if user_template_ is not None:
            for field_ in user_template_[0].fields:
                selected_field_ids.append(field_.id)

        sdds = FieldTemplateService.get_template_fields_by_id(template_id=template_id)

        selected_field_ids = {}
        for entry in sdds:
            template_field_, field_ = entry

            selected_field_ids[template_field_.order] = {"name": field_.field, "id": field_.id}

        od = collections.OrderedDict(sorted(selected_field_ids.items()))

        return render_template(template_name_or_list='field_template/partials/_sort_template_fields.html',
                               field_template_name=user_template_[0].name,
                               username=current_user.username, all_fields=all_fields, user_template=user_template_,
                               selected_field_ids=selected_field_ids, template_id=template_id, fields=od)

    else:
        json_data = request.json
        row_order = json_data["row_order"]
        FieldTemplateService.set_template_fields_orders(field_data=row_order, template_id=template_id,
                                                        user_id=current_user.id)

        return json.dumps({'success': True}), 200, {'ContentType': 'application/json'}


@field_template.route('/field-templates/<int:template_id>')
@login_required
def template(template_id):
    """
    :param template_id: The ID of the field template to retrieve.
    :return: The rendered template or a 404 error message if the template does not exist or the user does not have access.
    """
    all_fields = list(FieldService.get_all_user_and_system_fields(user_id=current_user.id))

    user_template_ = FieldTemplateService.get_user_template_by_id(template_id=template_id, user_id=current_user.id)

    if user_template_ is None:
        return render_template(template_name_or_list='404.html',
                               message="No such template or you do not have access to this item"), __NOT_FOUND__

    selected_field_ids = [field_.id for field_ in user_template_[0].fields]

    return render_template(template_name_or_list='field_template/field_template.html',
                           field_template_name=user_template_[0].name,
                           username=current_user.username, all_fields=all_fields, user_template=user_template_,
                           selected_field_ids=selected_field_ids, template_id=template_id)


@field_template.route('/@<string:username>/field-templates')
@login_required
def templates_with_username(username):
    all_fields = FieldService.get_all_fields()
    user_templates = FieldTemplateService.get_user_templates(user_id=current_user.id)
    return render_template(template_name_or_list='field_template/field_templates.html',
                           name=current_user.username, templates=user_templates, all_fields=all_fields)


@field_template.route('/set-template-fields', methods=['POST'])
@login_required
def set_template_fields():
    request_xhr_key = request.headers.get('X-Requested-With')
    if request_xhr_key and request_xhr_key == 'XMLHttpRequest':
        json_data = request.json
        template_name = json_data['template_name']
        # sanitise template name
        template_name = bleach.clean(template_name)

        field_ids = json_data['field_ids']
        if len(field_ids) == 0:
            abort(Response("At least 1 field is required for the template", __BAD_REQUEST__))

        field_ids = [int(x) for x in field_ids]  # was str(x)

        status, msg, template_id = FieldTemplateService.save_template_fields(template_name=template_name,
                                                                             fields=field_ids, user_id=current_user.id)

    return redirect(url_for('field_template.templates'))


@field_template.route('/field-templates/delete', methods=['POST'])
@login_required
def delete_template():
    json_data = request.json
    template_ids = json_data['template_ids']
    FieldTemplateService.delete_templates_from_db(user_id=current_user.id, template_ids=template_ids)
    return redirect(url_for('field_template.templates'))


@field_template.route('/field-templates/add', methods=['POST'])
@login_required
def add_template():
    from flask import current_app
    template_id_raw = request.form.get("template_id")
    template_name = request.form.get("template_name", "")
    template_fields_raw = request.form.get("template_fields", "")

    # sanitize name
    template_name = bleach.clean(template_name or "").strip()
    if not template_name:
        abort(Response("Template name is required", __BAD_REQUEST__))

    # parse template_fields: accept JSON array/obj or comma-separated list
    field_ids = []
    try:
        if template_fields_raw:
            s = template_fields_raw.strip()
            if s.startswith(("[", "{")):
                parsed = json.loads(s)
                if isinstance(parsed, dict):
                    # common payload shape: { "fields": [...] }
                    parsed = parsed.get("fields", [])
                if not isinstance(parsed, (list, tuple)):
                    raise ValueError("Invalid JSON shape for template_fields")
                field_ids = [int(x) for x in parsed]
            else:
                # comma separated string like "1,2,3"
                field_ids = [int(x) for x in s.split(",") if x.strip()]
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        current_app.logger.warning("Invalid template_fields: %s", exc)
        abort(Response("Invalid template fields format", __BAD_REQUEST__))

    # require at least one valid positive integer field id
    field_ids = [fid for fid in field_ids if isinstance(fid, int) and fid > 0]
    if not field_ids:
        abort(Response("At least 1 valid field id is required", __BAD_REQUEST__))

    # normalize template_id (optional)
    template_id = None
    if template_id_raw:
        try:
            template_id = int(template_id_raw)
            if template_id <= 0:
                template_id = None
        except (ValueError, TypeError):
            current_app.logger.info("Ignoring invalid template_id: %r", template_id_raw)
            template_id = None

    try:
        if template_id is None:
            # create new template
            FieldTemplateService.add_new_template(name=template_name, fields=field_ids, to_user=current_user)
        else:
            # update existing template: ensure it exists and belongs to the current user
            potential_template = FieldTemplateService.find_template_by_id(template_id=template_id)
            if potential_template is None:
                abort(Response("Template not found", __BAD_REQUEST__))
            owner_id = getattr(potential_template, "user_id", None)
            if owner_id is not None and owner_id != current_user.id:
                abort(Response("Forbidden", 403))
            new_template_data = {"id": template_id, "name": template_name, "fields": field_ids}
            FieldTemplateService.update_template_by_id(template_data=new_template_data, user=current_user)

    except Exception as exc:  # log and return generic server error
        current_app.logger.error("Failed to save template: %s", exc, exc_info=True)
        abort(Response("Failed to save template", 500))

    return redirect(url_for('field_template.templates'))
