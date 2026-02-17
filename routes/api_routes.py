import bleach
from flask import Blueprint, jsonify, current_app, request
from flask_login import login_required, current_user

from routes.items_routes import _process_url_query
from services.inventory_service import InventoryService
from services.item_service import ItemService
from services.item_type_service import ItemTypeService
from services.location_service import LocationService
from services.tag_service import TagService
from services.user_service import UserService
from services.search_service import SearchService
from site_globals import __DEFAULT__
from app import app

api_routes = Blueprint('api', __name__)


@api_routes.context_processor
def my_utility_processor():
    def item_tag_to_string(item_tag_list):
        tag_arr = []
        for tag in item_tag_list:
            tag_arr.append(tag.tag.replace("@#$", " "))
        return ",".join(tag_arr)

    return dict(item_tag_to_string=item_tag_to_string)


@api_routes.route('/api/item-types', methods=['GET'])
@login_required
def user_item_types():
    user_itemtypes_ = ItemTypeService.get_all_user_item_types(user_id=current_user.id)
    return user_itemtypes_


@api_routes.route('/api/user-items', methods=['GET', 'POST'])
@login_required
def user_items():
    user_items_ = ItemService.find_all_my_items(logged_in_user_id=current_user.id)
    ret_items = []
    for item_ in user_items_:
        ret_items.append(f"{item_.slug}")

    return ret_items


@api_routes.route('/api/items/@<string:username>/<inventory_slug>', methods=['GET', 'POST'])
# @login_required
def items(username=None, inventory_slug=None):
    """Optimized and more robust version of the items endpoint.

    Changes made:
    - Harden inputs (handle None, strip safely) and reduce repeated calls to services.
    - Fail fast with 404 when requested user or inventory doesn't exist.
    - Parse numeric query args once and convert to ints.
    - Use set for duplicate detection (faster membership tests).
    - Use list comprehensions where appropriate to reduce Python loop overhead.
    - Return proper Flask response (jsonify(...), status_code) instead of accessing .json[0].
    - Catch unexpected exceptions, log them, and return a 500 response.
    """
    try:
        user_is_authenticated = current_user.is_authenticated

        # sanitize inputs safely
        inventory_slug = (inventory_slug or '').strip()
        inventory_slug = bleach.clean(inventory_slug) if inventory_slug else 'all'
        inventory_owner_username = bleach.clean(username or '')

        inventory_owner = None
        inventory_owner_id = None

        logged_in_user = current_user if user_is_authenticated else None
        logged_in_user_id = getattr(logged_in_user, 'id', None)

        # if the logged in user matches the inventory owner username, prefer that user object
        if logged_in_user and getattr(logged_in_user, 'username', None) == inventory_owner_username:
            inventory_owner = logged_in_user
            inventory_owner_id = inventory_owner.id

        # fetch inventory owner only if needed
        if inventory_owner is None and inventory_owner_username:
            inventory_owner = UserService.get_user_by_username(username=inventory_owner_username)
            if inventory_owner is not None:
                inventory_owner_id = inventory_owner.id

        # requested_user is required for counts and permissions; fail if missing
        requested_user = UserService.get_user_by_username(username=username)
        if requested_user is None:
            return jsonify({"error": "requested user not found"}), 404

        # resolve inventory if specific inventory requested
        inventory_id = None
        inventory_ = None
        if inventory_slug != 'all':
            inventory_, user_inventory_ = InventoryService.find_inventory_by_slug(
                inventory_slug=inventory_slug,
                inventory_owner_id=inventory_owner_id,
                viewing_user_id=logged_in_user_id
            )
            if inventory_ is None:
                return jsonify({"error": "inventory not found"}), 404
            inventory_id = inventory_.id

        # build params from request
        request_params = _process_url_query(req_=request, inventory_user=requested_user)

        search_query = request.args.get("search[value]", None)
        if search_query is not None and len(search_query) < 3:
            search_query = None

        # parse numeric pagination arguments with safe fallbacks
        def _safe_int(val, default):
            try:
                return int(val)
            except (TypeError, ValueError):
                return default

        start = _safe_int(request.args.get("start", 0), 0)
        length = _safe_int(request.args.get("length", 50), 50)

        query_params = {
            'item_location': request_params.get("requested_item_location_id", None),
            'item_specific_location': request_params.get("item_specific_location", None),
            'item_tags': request_params.get("requested_tag_strings", None),
            'item_type': request_params.get("requested_item_type_id", None),
            'start': start,
            'length': length,
            'order_0': request.args.get("order[0][column]", None),
            'dir_0': request.args.get("order[0][dir]", None),
            'search': search_query,
        }

        # fetch items - let the service layer do heavy DB work
        items_ = ItemService.find_items_new(
            inventory_id=inventory_id,
            query_params=query_params,
            requested_username=username,
            logged_in_user=logged_in_user
        )

        # counts
        if inventory_slug != 'all':
            num_items_in_inventory = InventoryService.count_all_item_ids_in_inventory(user_id=requested_user.id, inventory_id=inventory_id)
        else:
            num_items_in_inventory = ItemService.count_all_user_items(user_id=requested_user.id)

        # assemble results efficiently
        _already_found_set = set()
        ret_items = []

        for row in items_:
            # row expected to be a tuple: (item, item_type, location_name, ..., is_link)
            item_ = row[0]
            item_type = row[1] if len(row) > 1 else None
            location_name = row[2] if len(row) > 2 else None
            is_link = row[4] if len(row) > 4 else False

            # deduplicate by slug quickly
            if item_.slug in _already_found_set:
                continue
            _already_found_set.add(item_.slug)

            # tags and inventories via comprehensions
            tag_arr = [t.tag.replace("@#$", " ") for t in item_.tags]
            _list_inventories = ["Default" if __DEFAULT__ in inv.name else inv.name for inv in item_.inventories]

            location = {}
            if location_name is not None:
                location["location"] = location_name
                if getattr(item_, 'specific_location', None):
                    location["specific_location"] = item_.specific_location

            ret_items.append({
                "name": {"name": item_.name, "slug": item_.slug, "id": item_.id, "description": item_.description, "is_link": is_link},
                "description": {"description": item_.description, "url": item_.url},
                "inventories": ", ".join(_list_inventories),
                "tags": tag_arr,
                "location": location,
                "type": item_type,
                "id": item_.id
            })

        return jsonify({
            "data": ret_items,
            "recordsTotal": num_items_in_inventory,
            "recordsFiltered": num_items_in_inventory
        }), 200

    except Exception as exc:
        # log and return generic error (avoid exposing internals in production)
        current_app.logger.exception("Error in api.items endpoint")
        return jsonify({"error": "internal server error"}), 500


@api_routes.route('/api/locations', methods=['GET'])
def get_search_dropdown_entries():
    # optional query to filter suggestions
    q = request.args.get('query', '').strip().lower()
    if not current_user or not getattr(current_user, 'is_authenticated', False):
        return jsonify({'error': 'authentication required'}), 401
    try:
        limit = int(request.args.get('limit', 10))
    except Exception:
        limit = 10

    suggestions = []

    # helper to add suggestions without exceeding limit
    def add_suggestions(arr):
        for obj in arr:
            if len(suggestions) >= limit:
                break
            suggestions.append(obj)
        return len(suggestions) >= limit

    # tags (prioritized first)
    tags_ = TagService.get_all_user_tags(user_id=current_user.id)
    tag_sugg = []
    for tag_ in tags_:
        tname = (tag_.tag or '').replace("@#$", " ").strip()
        if not tname:
            continue
        lt = tname.lower()
        if q and q not in lt:
            continue
        tag_sugg.append({"category": "tag", "value": tname})
    if add_suggestions(tag_sugg):
        return jsonify(suggestions)

    # types (second)
    item_types_ = ItemTypeService.get_all_user_and_system_item_types(user_id=current_user.id)
    type_sugg = []
    for item_type_ in item_types_:
        t = (item_type_ or '').strip()
        if not t:
            continue
        lt = t.lower()
        if q and q not in lt:
            continue
        type_sugg.append({"category": "type", "value": t})
    if add_suggestions(type_sugg):
        return jsonify(suggestions)

    # locations (third)
    locations_ = LocationService.get_all_user_locations(user_id=current_user.id)
    loc_sugg = []
    for loc_ in locations_:
        name = (loc_.name or '').strip()
        if not name:
            continue
        lname = name.lower()
        if q and q not in lname:
            continue
        loc_sugg.append({"category": "location", "value": name})
    if add_suggestions(loc_sugg):
        return jsonify(suggestions)

    # fields (last)
    try:
        from services.field_service import FieldService
        fields_ = FieldService.get_all_user_and_system_fields(user_id=current_user.id)
        fields_list = [row[0] if isinstance(row, (list, tuple)) else row for row in fields_]
        field_sugg = []
        for f in fields_list:
            fname = (f.field or '').strip()
            if not fname:
                continue
            lf = fname.lower()
            if q and q not in lf:
                continue
            field_sugg.append({"category": "field", "value": fname})
        add_suggestions(field_sugg)
    except Exception:
        pass

    return jsonify(suggestions)
    # return loc_array


@api_routes.route('/api/search', methods=['GET'])
def api_search():
    q = request.args.get('q', '').strip()
    if not current_user or not getattr(current_user, 'is_authenticated', False):
        return jsonify({'error': 'authentication required'}), 401
    try:
        page = int(request.args.get('page', 1))
    except Exception:
        page = 1
    try:
        per_page = int(request.args.get('per_page', app.config.get('POSTS_PER_PAGE', 20)))
    except Exception:
        per_page = int(app.config.get('POSTS_PER_PAGE', 20))

    # clamp values
    if page < 1:
        page = 1
    try:
        max_per_page = int(app.config.get('SEARCH_MAX_PER_PAGE', 100))
    except Exception:
        max_per_page = 100
    if per_page < 1:
        per_page = 1
    if per_page > max_per_page:
        per_page = max_per_page

    current_app.logger.debug(f"api_search called q={q!r} user_id={current_user.id if current_user else 'anon'} page={page} per_page={per_page}")

    if not q:
        current_app.logger.debug("api_search: empty q -> returning empty result")
        return jsonify({'items': [], 'total': 0, 'page': page, 'per_page': per_page})

    result = SearchService.search_items(query=q, user_id=current_user.id, page=page, per_page=per_page)
    current_app.logger.debug(f"api_search: returning total={result.get('total',0)} items for q={q!r}")
    return jsonify(result)


@api_routes.route('/api/debug_search_inspect', methods=['GET'])
def debug_search_inspect():
    q = request.args.get('q', '').strip()
    if not current_user or not getattr(current_user, 'is_authenticated', False):
        return jsonify({'error': 'authentication required'}), 401
    if not q:
        return jsonify({'error': 'query required'}), 400
    info = SearchService.inspect_query(q, user_id=current_user.id)
    return jsonify(info), 200


@api_routes.route('/api/search_debug', methods=['GET'])
def api_search_debug():
    # combined debug endpoint: returns search result + inspect info
    if not current_user or not getattr(current_user, 'is_authenticated', False):
        return jsonify({'error': 'authentication required'}), 401
    q = request.args.get('q', '').strip()
    try:
        page = int(request.args.get('page', 1))
    except Exception:
        page = 1
    try:
        per_page = int(request.args.get('per_page', app.config.get('POSTS_PER_PAGE', 20)))
    except Exception:
        per_page = int(app.config.get('POSTS_PER_PAGE', 20))

    # clamp
    if page < 1:
        page = 1
    try:
        max_per_page = int(app.config.get('SEARCH_MAX_PER_PAGE', 100))
    except Exception:
        max_per_page = 100
    if per_page < 1:
        per_page = 1
    if per_page > max_per_page:
        per_page = max_per_page

    if not q:
        return jsonify({'items': [], 'total': 0, 'page': page, 'per_page': per_page, 'debug': {}})

    result = SearchService.search_items(query=q, user_id=current_user.id, page=page, per_page=per_page)
    info = SearchService.inspect_query(q, user_id=current_user.id)
    return jsonify({'result': result, 'inspect': info}), 200

