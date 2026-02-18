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
try:
    from flask_limiter import Limiter
    from flask_limiter.util import get_remote_address
except Exception:
    Limiter = None
    get_remote_address = None

from site_globals import (__INVENTORY__, __LIST__, __URL_LIST__, __PUBLIC__, __PRIVATE__,
                          __VIEWER__, __LIST_ALL__, __COLLABORATOR__, __DEFAULT__, __OWNER__)


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

app.config['PRESERVE_CONTEXT_ON_EXCEPTION'] = False

app.config['LOG_DIRECTORY'] = os.environ.get('LOG_DIRECTORY', '')
# SECRET_KEY must be set in production. Default to a non-empty value in dev if provided, but fail-fast
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

def _parse_bool_env(val, default=False):
    if isinstance(val, bool):
        return val
    if val is None:
        return default
    return str(val).lower() in ("1", "true", "yes", "on")

# Parse DEBUG explicitly from env
app.debug = _parse_bool_env(os.environ.get('DEBUG', ''), False)

# Secure cookie and session settings. Respect explicit env overrides; otherwise default to secure values in non-debug.
_env_session_secure = os.environ.get('SESSION_COOKIE_SECURE')
if _env_session_secure is not None and _env_session_secure != '':
    app.config['SESSION_COOKIE_SECURE'] = _parse_bool_env(_env_session_secure)
else:
    app.config['SESSION_COOKIE_SECURE'] = False if app.debug else True

_env_session_httponly = os.environ.get('SESSION_COOKIE_HTTPONLY')
if _env_session_httponly is not None and _env_session_httponly != '':
    app.config['SESSION_COOKIE_HTTPONLY'] = _parse_bool_env(_env_session_httponly)
else:
    app.config['SESSION_COOKIE_HTTPONLY'] = True

_env_session_samesite = os.environ.get('SESSION_COOKIE_SAMESITE')
if _env_session_samesite is not None and _env_session_samesite != '':
    app.config['SESSION_COOKIE_SAMESITE'] = _env_session_samesite
else:
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

app.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER')
app.config['MAIL_PORT'] = int(os.environ.get('MAIL_PORT') or 25)
app.config['MAIL_USE_TLS'] = os.environ.get('MAIL_USE_TLS') is not None
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')
app.config['MAIL_DEBUG'] = os.environ.get('MAIL_DEBUG')
raw_admins = os.environ.get('ADMINS', '')
if raw_admins:
    # Support comma-separated list in the environment; normalize to a list
    app.config['ADMINS'] = [a.strip() for a in raw_admins.split(',') if a.strip()]
else:
    app.config['ADMINS'] = []

app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('MAIL_DEFAULT_SENDER')

app.config['ALLOW_REGISTRATIONS'] = os.environ.get('ALLOW_REGISTRATIONS', 0)
app.config['TOKEN_EXPIRATION_MINUTES'] = os.environ.get('TOKEN_EXPIRATION_MINUTES', 15)
app.config['ITEM_DESCRIPTION_CHAR_LIMIT'] = os.environ.get('ITEM_DESCRIPTION_CHAR_LIMIT', 20000)


app.config['USER_IMAGES_BASE_URL'] = os.environ.get('USER_IMAGES_BASE_URL', '')
app.config['USER_IMAGES_BASE_PATH'] = os.environ.get('USER_IMAGES_BASE_PATH', '')
app.config['ITEM_MASONARY_IMAGE_SIZE'] = os.environ.get('ITEM_MASONARY_IMAGE_SIZE', 200)
app.config['PROCESS_IMAGE_WIDTH'] = os.environ.get('PROCESS_IMAGE_WIDTH', 600)
app.config['PROCESS_IMAGE_HEIGHT'] = os.environ.get('PROCESS_IMAGE_HEIGHT', 800)
app.config['PROCESS_IMAGE_FORMAT'] = os.environ.get('PROCESS_IMAGE_FORMAT', "JPEG")


# Configure Flask logging
# Ensure log directory exists if configured. If empty or not set, fall back to a safe temp directory.
if not app.config['LOG_DIRECTORY']:
    # Choose a fallback logs directory inside the project tmp
    app.config['LOG_DIRECTORY'] = os.path.join(os.path.dirname(__file__), 'logs')

try:
    os.makedirs(app.config['LOG_DIRECTORY'], exist_ok=True)
except Exception:
    # If we cannot create the directory, log to current directory as a last resort
    app.config['LOG_DIRECTORY'] = os.path.join(os.path.dirname(__file__), '.')

error_log_file_handler = RotatingFileHandler(filename=os.path.join(app.config['LOG_DIRECTORY'], 'thinglist_error.txt'), maxBytes=1024*1024,
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

# Detect whether the connected DB supports window functions (ROW_NUMBER) and cache the result.
from sqlalchemy import text
try:
    # A small query using ROW_NUMBER to test support. Different DBs may accept this;
    # if it raises, we'll assume window functions are not supported and fall back to Python selection.
    with app.app_context():
        db.session.execute(text("SELECT 1 FROM (SELECT row_number() OVER (ORDER BY (SELECT 1)) AS rn) AS t LIMIT 1"))
        app.config['DB_SUPPORTS_WINDOW_FUNCTIONS'] = True
except Exception as e:
    app.logger.warning(f"DB does not appear to support window functions (row_number); falling back to Python selection: {e}")
    app.config['DB_SUPPORTS_WINDOW_FUNCTIONS'] = False

app.logger.info(f"DB_SUPPORTS_WINDOW_FUNCTIONS={app.config['DB_SUPPORTS_WINDOW_FUNCTIONS']}")

#search = Search(db=db)
#search.init_app(app)

# Flask BCrypt will be used to salt the user password
flask_bcrypt = Bcrypt(app)

# Associate Flask-Login manager with current app
login_manager = LoginManager()
login_manager.init_app(app)
# Strengthen session protection
try:
    login_manager.session_protection = 'strong'
except Exception:
    # Older versions may not support this attribute; ignore if unavailable
    pass

# Initialize Flask-Limiter if available
if Limiter is not None:
    # Different flask-limiter versions accept app in different positions; to be compatible,
    # construct without app and call init_app.
    limiter = Limiter(key_func=get_remote_address, default_limits=["200 per day", "50 per hour"])
    try:
        limiter.init_app(app)
    except TypeError:
        # Fallback: older versions accept app as first arg
        limiter = Limiter(app, key_func=get_remote_address, default_limits=["200 per day", "50 per hour"])
else:
    limiter = None

# Environment validation for critical settings (fail-fast in production)
def _validate_env():
    # Ensure DB URL is configured
    db_url = app.config.get('SQLALCHEMY_DATABASE_URI')
    if not app.debug:
        if not db_url:
            raise RuntimeError("DATABASE_URL (SQLALCHEMY_DATABASE_URI) must be set in environment for non-debug mode. Example: DATABASE_URL='mysql://user:pass@host/dbname?charset=utf8mb4'")
        # Basic sanity checks
        if '//' not in db_url:
            raise RuntimeError(f"DATABASE_URL looks invalid: {db_url}")

    # Mail settings: warn if incomplete
    mail_server = app.config.get('MAIL_SERVER')
    if mail_server:
        if not app.config.get('MAIL_USERNAME') or not app.config.get('MAIL_PASSWORD'):
            app.logger.warning('MAIL_SERVER is set but MAIL_USERNAME or MAIL_PASSWORD is missing; email sending may fail.')
    else:
        app.logger.info('MAIL_SERVER is not set; transactional emails will be disabled.')


_validate_env()


@app.context_processor
def inject_globals():
    return dict(
        __DEFAULT__=__DEFAULT__,
        __PUBLIC__=__PUBLIC__,
        __PRIVATE__=__PRIVATE__,
        __COLLABORATOR__=__COLLABORATOR__,
        __INVENTORY__=__INVENTORY__,
        __LIST__=__LIST__,
        __LIST_ALL__=__LIST_ALL__,
        __URL_LIST__=__URL_LIST__,
        __VIEWER__=__VIEWER__,
        __OWNER__=__OWNER__
    )


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

# Validate required production settings early (fail-fast if missing when not in debug)
if not app.debug:
    if not app.config.get('SECRET_KEY'):
        raise RuntimeError("SECRET_KEY must be set in environment for non-debug mode")

mail = Mail(app)

# Optional server-side session support: Flask-Session with Redis
_session_backend_available = False
try:
    from flask_session import Session as FlaskSession
    _session_backend_available = True
except Exception:
    FlaskSession = None

# Initialize server-side session if configured via env
if _session_backend_available:
    # Prefer explicit SESSION_TYPE or REDIS_URL
    session_type = os.environ.get('SESSION_TYPE', '')
    redis_url = os.environ.get('REDIS_URL', '')
    if session_type.lower() == 'redis' or redis_url:
        app.config.setdefault('SESSION_TYPE', 'redis')
        if redis_url:
            app.config.setdefault('SESSION_REDIS', redis_url)
        try:
            FlaskSession(app)
            app.logger.info('Server-side sessions enabled via Flask-Session')
        except Exception:
            app.logger.exception('Failed to initialize Flask-Session; falling back to client-side sessions')


# Helper to explicitly rotate/regenerate session data
def regenerate_session():
    """Regenerate the session to mitigate session fixation.

    Approach: preserve non-sensitive session data if needed, clear the session, then set a nonce
    to ensure the resulting session cookie differs from the prior one. This works with client-side
    signed cookies and with server-side session backends (Flask-Session), forcing a new session
    payload/cookie to be issued.
    """
    try:
        from flask import session, request, current_app
        import secrets as _secrets

        sess_interface = current_app.session_interface

        # Determine existing session id if available (many server-side backends expose it on session.sid)
        old_sid = None
        try:
            old_sid = getattr(session, 'sid', None)
        except Exception:
            old_sid = None

        if not old_sid:
            # Fallback to cookie value
            old_sid = request.cookies.get(current_app.session_cookie_name)

        # Attempt to generate a new session id using the session interface if supported
        new_sid = None
        try:
            if hasattr(sess_interface, 'generate_sid'):
                new_sid = sess_interface.generate_sid()
        except Exception:
            new_sid = None

        if not new_sid:
            # Last-resort SID generator
            new_sid = _secrets.token_urlsafe(24)

        # If backend supports direct deletion (commonly Redis), attempt to remove old session data
        try:
            # Redis-backed interface often exposes a `redis` attribute and `key_prefix`
            redis_client = getattr(sess_interface, 'redis', None)
            key_prefix = getattr(sess_interface, 'key_prefix', '') or ''
            if redis_client and old_sid:
                try:
                    redis_client.delete(key_prefix + old_sid)
                except Exception:
                    # ignore deletion errors
                    pass
            # Some interfaces use `cache` attribute (memcached etc.)
            cache_client = getattr(sess_interface, 'cache', None)
            if cache_client and old_sid:
                try:
                    cache_client.delete(key_prefix + old_sid)
                except Exception:
                    pass
        except Exception:
            # Not critical; continue
            pass

        # Clear current session contents and set new sid/nonce
        try:
            # preserve no keys; clear everything
            for k in list(session.keys()):
                try:
                    session.pop(k)
                except Exception:
                    pass
        except RuntimeError:
            current_app.logger.warning('regenerate_session called outside request context; skipping clear')
            return

        # Set new identifiers which many server-side session backends will respect
        try:
            setattr(session, 'sid', new_sid)
        except Exception:
            # Some session objects are dict-like only; set a fallback key
            session['_id'] = new_sid

        # Add a nonce and mark modified so the session will be saved under the new id
        session['session_nonce'] = _secrets.token_urlsafe(16)
        session.modified = True

    except RuntimeError:
        # Not in a request context — cannot rotate session
        app.logger.warning('regenerate_session called outside request context; skipping')
    except Exception:
        app.logger.exception('Error rotating session')
