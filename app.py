import os

from flask_qrcode import QRcode
from flask_sqlalchemy import SQLAlchemy
from flask import Flask, render_template, request
import flask_resize
from flask_login import LoginManager
from flask_bcrypt import Bcrypt
from flask_wtf.csrf import CSRFProtect
from flask_mail import Mail

#from pycharm_flask_debug_patch import restart_with_reloader_patch


from dotenv import load_dotenv

if not load_dotenv('.env'):
    if not load_dotenv('../.env'):
        raise Exception("Could not read environment file")

__PUBLIC__ = 2
__PRIVATE__ = 0
__OWNER__ = 0
__COLLABORATOR__ = 1
__VIEWER__ = 2

# Create and name Flask app
app = Flask("ThingList", static_url_path="", static_folder="static")

app.config['RESIZE_URL'] = os.environ.get('RESIZE_URL', '')
app.config['RESIZE_ROOT'] = os.environ.get('RESIZE_ROOT', '/tmp')

resize = flask_resize.Resize(app)

ELASTICSEARCH_URL = os.environ.get('ELASTICSEARCH_URL')


app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', '')
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

csrf = CSRFProtect(app)

QRcode(app)

app.jinja_env.trim_blocks = True
app.jinja_env.lstrip_blocks = True

SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL', 'mysql://{0}:{1}@{2}/{3}'.format(app.config['MYSQL_USER'],
                                                                                     app.config['MYSQL_PASSWORD'],
                                                                                     app.config['MYSQL_HOST'],
                                                                                     app.config['MYSQL_DB']))

app.config['ELASTICSEARCH_URL'] = ELASTICSEARCH_URL

app.config['SQLALCHEMY_DATABASE_URI'] = SQLALCHEMY_DATABASE_URI

db = SQLAlchemy(app, session_options={"expire_on_commit": "False"})

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
