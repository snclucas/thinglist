from flask import Blueprint, render_template, request
from flask_login import login_required, current_user
from app import app

from services.search_service import SearchService

search_routes = Blueprint('search', __name__)


@search_routes.route('/search', methods=['GET', 'POST'])
@login_required
def search():
    query_string = request.args.get('q')
    # default paging values
    try:
        page = int(request.args.get('page', 1))
    except Exception:
        page = 1
    try:
        per_page = int(request.args.get('per_page', app.config.get('POSTS_PER_PAGE', 20)))
    except Exception:
        per_page = int(app.config.get('POSTS_PER_PAGE', 20))

    # Clamp/validate ranges
    try:
        max_per_page = int(app.config.get('SEARCH_MAX_PER_PAGE', 100))
    except Exception:
        max_per_page = 100
    if page < 1:
        page = 1
    if per_page < 1:
        per_page = 1
    if per_page > max_per_page:
        per_page = max_per_page

    # default template context
    context = {
        'items': [],
        'q': query_string or '',
        'username': current_user.username,
        'total': 0,
        'page': page,
        'per_page': per_page,
    }

    if query_string:
        result = SearchService.search_items(query=query_string, user_id=current_user.id, page=page, per_page=per_page)
        context['items'] = result.get('items', [])
        context['total'] = result.get('total', 0)
        context['page'] = result.get('page', page)
        context['per_page'] = result.get('per_page', per_page)

    try:
        from site_globals import build_meta
        meta = build_meta(title=f"Search — {query_string or ''}", description=f"Search results for {query_string or ''}")
    except Exception:
        meta = None

    return render_template('search/search.html', **context, meta=meta)
