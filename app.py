import logging
import os
from logging.handlers import RotatingFileHandler

from flask_qrcode import QRcode
from flask_sqlalchemy import SQLAlchemy
from flask import Flask, render_template, request
import flask_resize
from flask_login import LoginManager
from flask_bcrypt import Bcrypt
from flask_wtf.csrf import CSRFProtect
from flask_mail import Mail

#from flask_msearch import Search

#from pycharm_flask_debug_patch import restart_with_reloader_patch


from dotenv import load_dotenv

if not load_dotenv('.env'):
    if not load_dotenv('../.env'):
        raise Exception("Could not read environment file")



# Create and name Flask app
app = Flask(import_name="ThingList", static_url_path="", static_folder="static")




app.config['RESIZE_URL'] = os.environ.get('RESIZE_URL', '')
app.config['RESIZE_ROOT'] = os.environ.get('RESIZE_ROOT', '/tmp')

resize = flask_resize.Resize(app)

ELASTICSEARCH_URL = os.environ.get('ELASTICSEARCH_URL')

app.config['LOG_DIRECTORY'] = os.environ.get('LOG_DIRECTORY', '')
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', '')
app.config['IMAGE_SECRET_KEY'] = os.environ.get('IMAGE_SECRET_KEY', '')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# database connection
app.config['MYSQL_HOST'] = os.environ.get('MYSQL_HOST', '')
app.config['MYSQL_USER'] = os.environ.get('MYSQL_USER', '')
app.config['MYSQL_PASSWORD'] = os.environ.get('MYSQL_PASSWORD', '')
app.config['MYSQL_DB'] = os.environ.get('MYSQL_DB', '')

app.config['UPLOAD_FOLDER'] = os.environ.get('UPLOAD_FOLDER', '')

app.config['FILE_UPLOADS'] = os.environ.get('FILE_UPLOADS', '')

app.config['POSTS_PER_PAGE'] = os.environ.get('POSTS_PER_PAGE', 10)

app.debug = os.environ.get('DEBUG', bool(os.environ.get('DEBUG', '')))


app.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER')
app.config['MAIL_PORT'] = int(os.environ.get('MAIL_PORT') or 25)
app.config['MAIL_USE_TLS'] = os.environ.get('MAIL_USE_TLS') is not None
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')
app.config['MAIL_DEBUG'] = os.environ.get('MAIL_DEBUG')
app.config['ADMINS'] = os.environ.get('ADMINS')

app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('MAIL_DEFAULT_SENDER')

app.config['ALLOW_REGISTRATIONS'] = os.environ.get('ALLOW_REGISTRATIONS', 0)
app.config['TOKEN_EXPIRATION_MINUTES'] = os.environ.get('TOKEN_EXPIRATION_MINUTES', 15)
app.config['ITEM_DESCRIPTION_CHAR_LIMIT'] = os.environ.get('ITEM_DESCRIPTION_CHAR_LIMIT', 20000)
app.config['USER_IMAGES_BASE_URL'] = os.environ.get('USER_IMAGES_BASE_URL', '')
app.config['USER_IMAGES_BASE_PATH'] = os.environ.get('USER_IMAGES_BASE_PATH', '')
app.config['ITEM_MASONARY_IMAGE_SIZE'] = os.environ.get('ITEM_MASONARY_IMAGE_SIZE', 200)



# Configure Flask logging
if not os.path.exists(app.config['LOG_DIRECTORY']):
    os.mkdir(app.config['LOG_DIRECTORY'])

error_log_file_handler = RotatingFileHandler(filename=os.path.join(app.config['LOG_DIRECTORY'], 'thinglist_error.txt'), maxBytes=10240,
                                             backupCount=10)
error_log_file_handler.setFormatter(logging.Formatter(
    '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'))
error_log_file_handler.setLevel(logging.INFO)
app.logger.addHandler(error_log_file_handler)

app.logger.setLevel(logging.INFO)
app.logger.info('ThingList startup')



csrf = CSRFProtect(app)

QRcode(app)

app.jinja_env.trim_blocks = True
app.jinja_env.lstrip_blocks = True

SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL', 'mysql://{0}:{1}@{2}/{3}?charset=utf8mb4'.format(app.config['MYSQL_USER'],
                                                                                     app.config['MYSQL_PASSWORD'],
                                                                                     app.config['MYSQL_HOST'],
                                                                                     app.config['MYSQL_DB']))

app.config['ELASTICSEARCH_URL'] = ELASTICSEARCH_URL

app.config['SQLALCHEMY_DATABASE_URI'] = SQLALCHEMY_DATABASE_URI

db = SQLAlchemy(app, session_options={"expire_on_commit": "False"})

#search = Search(db=db)
#search.init_app(app)

# Flask BCrypt will be used to salt the user password
flask_bcrypt = Bcrypt(app)

# Associate Flask-Login manager with current app
login_manager = LoginManager()
login_manager.init_app(app)

mail = Mail(app)


@app.context_processor
def inject_template_scope():
    injections = dict()

    def cookies_check():
        value = request.cookies.get('cookie_consent')
        return value == 'true'

    injections.update(cookies_check=cookies_check)

    return injections


@app.errorhandler(404)
def page_not_found(error):
    return render_template('404.html', title='404', error=error), 404


@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return render_template('500.html'), 500
