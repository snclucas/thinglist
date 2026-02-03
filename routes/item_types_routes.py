import csv
import os
from io import StringIO

import bleach
from flask import Blueprint, render_template, redirect, url_for, request, make_response
from flask_login import login_required, current_user

from app import app

from services.thinglist_services import ItemTypeService

types = Blueprint('types', __name__)


@types.route('/item-types', methods=['GET'])
@login_required
def item_types():
    user_itemtypes = ItemTypeService.get_all_user_item_types(user_id=current_user.id, string_list=False)
    return render_template(template_name_or_list='types/item_types.html',
                           username=current_user.username, user_item_types=user_itemtypes)


@types.route('/item-type/delete', methods=['POST'])
@login_required
def delete_item_type():
    json_data = request.json
    itemtype_ids = json_data['itemtype_ids']
    ItemTypeService.delete_item_types_by_id(itemtype_ids=itemtype_ids, user_id=current_user.id)
    return redirect(url_for('types.item_types'))


@types.route('/item_type/add', methods=['POST'])
@login_required
def add_item_type():
    item_type_name = request.form.get("item_type_name")
    item_type_name = bleach.clean(item_type_name)

    potential_item_type_ = ItemTypeService.find_item_type_by_text(type_text=item_type_name)

    if potential_item_type_ is None:
        ItemTypeService.get_or_add_new_user_item_type(name=item_type_name, user_id=current_user.id)

    return redirect(url_for('types.item_types'))


@types.route('/item-types/save', methods=['POST'])
@login_required
def itemtypes_save():
    username = current_user.username

    filename = f"{username}_itemtypes_export.csv"

    user_itemtypes = ItemTypeService.get_all_user_item_types(user_id=current_user.id, string_list=False)

    csv_list = [["#Type"]]

    for row in user_itemtypes:
        item_type = row.name
        if item_type != "None":
            csv_list.append([item_type])

    si = StringIO()
    cw = csv.writer(si)
    cw.writerows(csv_list)
    output = make_response(si.getvalue())
    output.headers["Content-Disposition"] = f"attachment; filename={filename}"
    output.headers["Content-types"] = "text/csv"
    return output


@types.route('/item-types/load', methods=['POST'])
@login_required
def itemtypes_load():

    if request.files:
        uploaded_file = request.files['file']  # This line uses the same variable and worked fine
        filepath = os.path.join(app.config['FILE_UPLOADS'], uploaded_file.filename)
        uploaded_file.save(filepath)

        with open(filepath) as csvfile:
            line_count = 0
            reader = csv.reader(csvfile, delimiter=',', quotechar='"')
            for row in reader:

                if line_count != 0:
                    item_type = row[0]

                    if item_type != "None":
                        potential_item_type_ = ItemTypeService.find_item_type_by_text(type_text=item_type)
                        if potential_item_type_ is None:
                            ItemTypeService.get_or_add_new_user_item_type(name=item_type, user_id=current_user.id)

                line_count += 1

    return redirect(url_for('types.item_types'))
