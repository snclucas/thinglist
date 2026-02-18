from app import app

# Import and register blueprints here so that importing `routes` ensures routes are active.
# This mirrors what run_server.py does but keeps registration available when importing `app` directly.
try:
    from .auth_routes import auth_flask_login
    app.register_blueprint(auth_flask_login)
except Exception:
    app.logger.debug('auth_routes lazy registration failed', exc_info=True)

try:
    from .index_routes import main
    app.register_blueprint(main)
except Exception:
    app.logger.debug('index_routes lazy registration failed', exc_info=True)

try:
    from .list_routes import inv
    app.register_blueprint(inv)
except Exception:
    app.logger.debug('list_routes lazy registration failed', exc_info=True)

try:
    from .location_routes import location
    app.register_blueprint(location)
except Exception:
    app.logger.debug('location_routes lazy registration failed', exc_info=True)

try:
    from .field_template_routes import field_template
    app.register_blueprint(field_template)
except Exception:
    app.logger.debug('field_template_routes lazy registration failed', exc_info=True)

try:
    from .item_types_routes import types
    app.register_blueprint(types)
except Exception:
    app.logger.debug('item_types_routes lazy registration failed', exc_info=True)

try:
    from .item_routes import item_routes
    app.register_blueprint(item_routes)
except Exception:
    app.logger.debug('item_routes lazy registration failed', exc_info=True)

try:
    from .items_routes import items_routes
    app.register_blueprint(items_routes)
except Exception:
    app.logger.debug('items_routes lazy registration failed', exc_info=True)

try:
    from .api_routes import api_routes
    app.register_blueprint(api_routes)
except Exception:
    app.logger.debug('api_routes lazy registration failed', exc_info=True)

try:
    from .search_routes import search_routes
    app.register_blueprint(search_routes)
except Exception:
    app.logger.debug('search_routes lazy registration failed', exc_info=True)

try:
    from .field_routes import field_routes
    app.register_blueprint(field_routes)
except Exception:
    app.logger.debug('field_routes lazy registration failed', exc_info=True)

try:
    from .user_admin_routes import user_admin_routes
    app.register_blueprint(user_admin_routes)
except Exception:
    app.logger.debug('user_admin_routes lazy registration failed', exc_info=True)

