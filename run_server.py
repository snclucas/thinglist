import os
from datetime import datetime
import mimetypes

from admin.verify_database import verify_database_setup
# Import the main Flask app
from app import app

# Get Blueprint Apps
from routes.auth_routes import auth_flask_login

from routes.index_routes import main
from routes.list_routes import inv
from routes.location_routes import location
from routes.field_template_routes import field_template
from routes.item_types_routes import types
from routes.item_routes import item_routes
from routes.items_routes import items_routes
from routes.api_routes import api_routes
from routes.search_routes import search_routes
from routes.field_routes import field_routes
from routes.user_admin_routes import user_admin_routes


# Register Blueprints
# app.register_blueprint(auth_flask_login)
# app.register_blueprint(main)
# app.register_blueprint(inv)
# app.register_blueprint(location)
# app.register_blueprint(field_template)
# app.register_blueprint(types)
# app.register_blueprint(item_routes)
# app.register_blueprint(items_routes)
# app.register_blueprint(api_routes)
# app.register_blueprint(search_routes)
# app.register_blueprint(field_routes)
# app.register_blueprint(user_admin_routes)


mimetypes.add_type('application/javascript', '.js')
mimetypes.add_type('text/css', '.css')




@app.after_request
def add_headers(response):
    """
    Inject headers
    :param response:
    :return:
    """
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    #response.headers['Content-Security-Policy'] = "default-src 'self'; style-src-elem 'self' http://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; unsafe-inline"
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    response.headers['Last-Modified'] = datetime.now()
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '-1'

    return response



# start the server
if __name__ == "__main__":
    if not verify_database_setup():
        app.logger.error("One or more database checks failed on startup")

    port = int(os.environ.get('THINGLIST_PORT', 5000))
    app.run(host=os.environ.get('THINGLIST_HOST', '0.0.0.0'), port=port, debug=True)
