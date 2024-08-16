from flask import Blueprint, render_template, request
from flask_login import login_required, current_user

from database_functions import search_items

search_routes = Blueprint('search', __name__)


@search_routes.route('/search', methods=['GET', 'POST'])
@login_required
def search():
    query_string = request.args.get('q')
    if query_string is not None:
        items = search_items(query=query_string, user_id=current_user.id)
        return render_template('search/search.html', items=items, q=query_string, username=current_user.username)
    return render_template('search/search.html')
