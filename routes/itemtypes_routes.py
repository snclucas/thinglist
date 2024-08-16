import csv
import os
from io import StringIO

from flask import Blueprint, render_template, redirect, url_for, request, make_response
from flask_login import login_required, current_user

from app import app

from database_functions import get_all_itemtypes_for_user, find_type_by_text, \
    add_new_user_itemtype, delete_itemtypes_from_db

types = Blueprint('types', __name__)


@types.route('/item-types')
@login_required
def item_types():
    user_itemtypes = get_all_itemtypes_for_user(user_id=current_user.id, string_list=False)
    return render_template('types/item_types.html', username=current_user.username, user_item_types=user_itemtypes)


@types.route('/item-type/delete', methods=['POST'])
@login_required
def delete_item_type():
    if request.method == 'POST':
        json_data = request.json
        itemtype_ids = json_data['itemtype_ids']
        delete_itemtypes_from_db(itemtype_ids=itemtype_ids, user_id=current_user.id)
        return redirect(url_for('types.item_types'))


@types.route('/item_type/add', methods=['POST'])
@login_required
def add_item_type():

    if request.method == 'POST':
        item_type_name = request.form.get("item_type_name")

        potential_item_type_ = find_type_by_text(type_text=item_type_name)

        if potential_item_type_ is None:
            add_new_user_itemtype(name=item_type_name, user_id=current_user.id)

        return redirect(url_for('types.item_types'))


@types.route('/item-types/save', methods=['POST'])
@login_required
def itemtypes_save():
    username = current_user.username

    filename = f"{username}_itemtypes_export.csv"

    user_itemtypes = get_all_itemtypes_for_user(user_id=current_user.id, string_list=False)

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

    if request.method == 'POST':

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
                            potential_item_type_ = find_type_by_text(type_text=item_type)
                            if potential_item_type_ is None:
                                add_new_user_itemtype(name=item_type, user_id=current_user.id)

                    line_count += 1

    return redirect(url_for('types.item_types'))
