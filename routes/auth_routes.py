import datetime
import re
import secrets

# bleach imported but not used here; leave available for views that sanitize HTML if needed
#from flask import current_app, Blueprint, render_template, request, flash, redirect, url_for, session
from flask import current_app, Blueprint, render_template, request, flash, redirect, url_for, session
from app import login_manager, flask_bcrypt, app
from flask_login import (login_required, login_user, logout_user, confirm_login, current_user)

from email_utils import send_email
from models import User
from routes.index_routes import profile
from services.user_service import UserService, post_user_add_hook
from utils import sanitize, password_check
try:
    from app import limiter
except Exception:
    limiter = None

auth_flask_login = Blueprint('auth_flask_login', __name__, template_folder='templates')


@auth_flask_login.route("/login", methods=["GET", "POST"])
@limiter.limit("10 per minute") if limiter is not None else (lambda f: f)
def login():
    """
    Method: login

    This method is used to authenticate a user and log them into the system.

    URL: /login
    Methods: GET, POST

    Parameters:
        - None

    Returns:
        - None
    """

    if request.method == "POST" and "username" in request.form:

        username = sanitize(request.form.get("username", None))
        password = sanitize(request.form.get("password", None))
        if username is None or password is None:
            flash("Username or password cannot be empty")
            return render_template("auth/login.html")

        user = UserService.get_user_by_username(username=username)
        if user and flask_bcrypt.check_password_hash(user.password, password) and user.is_active:
            remember = request.form.get("remember", "no") == "yes"

            if user.activated == 0:
                flash("Thing Master not activated")
                return render_template("auth/login.html")

            # Prevent session fixation: clear existing session data before login
            session.clear()
            # Perform login; on success, regenerate the session using app helper
            if login_user(user, remember=remember):
                try:
                    # regenerate_session clears and sets a nonce so a new cookie will be issued
                    from app import regenerate_session
                    regenerate_session()
                except Exception:
                    current_app.logger.warning('Failed to regenerate session after login')
                return redirect(url_for('main.profile', username=user.username).replace('%40', '@'))
            else:
                flash("Unable to log you in")
                allow_registrations = (int(app.config['ALLOW_REGISTRATIONS']) == 1)
                return render_template(template_name_or_list="auth/login.html", allow_registrations=allow_registrations)
        else:
            flash("Unable to log you in")
            allow_registrations = (int(app.config['ALLOW_REGISTRATIONS']) == 1)
            return render_template(template_name_or_list="auth/login.html", allow_registrations=allow_registrations)

    else:

        allow_registrations = (int(app.config['ALLOW_REGISTRATIONS']) == 1)
        return render_template(template_name_or_list="auth/login.html", allow_registrations=allow_registrations)


@auth_flask_login.route(rule="/activate-user/<token>", methods=["GET"])
def activate_user(token):
    """
    Activate a user based on the given token.

    :param token: The activation token provided in the URL.
    :type token: str
    :return: The rendered template after user activation.
    :rtype: str
    """
    user_ = UserService.get_user_by_token(token=token)
    template = "auth/login.html"

    if user_ is not None and not user_.activated and user_.token == token:
        token_expiry = user_.token_expires
        # Normalize timezone: treat naive datetimes as UTC
        if token_expiry is None:
            flash("Expired registration request")
            return render_template(template)
        if token_expiry.tzinfo is None:
            token_expiry = token_expiry.replace(tzinfo=datetime.timezone.utc)
        if datetime.datetime.now(datetime.timezone.utc) > token_expiry:
            flash("Expired registration request")
            return render_template(template)

        # Activate and clear token
        success = UserService.activate(user_id=user_.id)
        try:
            user_.token = None
            user_.token_expires = None
            from app import db
            db.session.merge(user_)
            db.session.commit()
        except Exception:
            current_app.logger.exception('Failed to clear activation token after activation')

        flash("You are now an activated Thing Master!")

    return render_template(template)


@auth_flask_login.route("/reset-password/<token>", methods=["GET", "POST"])
@limiter.limit("5 per minute") if limiter is not None else (lambda f: f)
def reset_password_token(token):
    template = "auth/reset_password.html"

    if request.method == 'GET':
        user_ = UserService.get_user_by_token(token=token)
        if user_ is not None and user_.activated:
            return render_template(template, token=token)
        return None
    else:
        user_ = UserService.get_user_by_token(token=token)

        token_expiry = user_.token_expires if user_ is not None else None
        if token_expiry is None:
            flash("Expired or invalid password reset request")
            return reset_password_token(token)
        if token_expiry.tzinfo is None:
            token_expiry = token_expiry.replace(tzinfo=datetime.timezone.utc)
        if datetime.datetime.now(datetime.timezone.utc) > token_expiry:
            flash("Expired or invalid password reset request")
            return reset_password_token(token)

        if user_ is not None and user_.activated:
            password1 = sanitize(request.form.get("password1"))
            password2 = sanitize(request.form.get("password2"))

            if password1 == password2:
                password_check_results = password_check(password1)
                if not password_check_results['password_ok']:
                    flash("Password does not meet the criteria")
                    return reset_password_token(token)

                password_hash = flask_bcrypt.generate_password_hash(password1)
                UserService.update_user_password_by_token(token=token, password_hash=password_hash)
                # Clear token on successful reset
                try:
                    user_.token = None
                    user_.token_expires = None
                    from app import db
                    db.session.merge(user_)
                    db.session.commit()
                except Exception:
                    current_app.logger.exception('Failed to clear reset token after password update')
                return login()
            else:
                flash("Both passwords must match")
                return reset_password_token(token)
        else:
            flash("There was a problem updating your password")
            return reset_password_token(token)



@auth_flask_login.route(rule="/reset-password", methods=["GET", "POST"])
@limiter.limit("5 per minute") if limiter is not None else (lambda f: f)
def reset_password_request():

    token_epiration_minutes = int(app.config['TOKEN_EXPIRATION_MINUTES'])

    template = "auth/reset_password_request.html"

    if request.method == 'POST':
        email = sanitize(request.form.get("email"))
        user_ = UserService.get_user_by_email(email=email)

        if user_ is not None and user_.activated:
            # Use a secure token generator
            confirmation_token = secrets.token_urlsafe(32)
            token_expires = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=token_epiration_minutes)
            UserService.update_user_token_by_email(email=email, user_token=confirmation_token, token_expires=token_expires)

            text_body = render_template(template_name_or_list='email/reset_password.txt', user=user_, token=confirmation_token)
            html_body = render_template(template_name_or_list='email/reset_password.html', user=user_, token=confirmation_token)
            send_email(subject="Password change", sender=None, recipients=[user_.email],
                       text_body=text_body, html_body=html_body)

        flash("Check your email")
        return render_template(template)

    else:
        return render_template(template)


@auth_flask_login.route(rule="/change-password", methods=["POST"])
@login_required
def change_password():

    if request.method == 'POST':

        old_password = sanitize(request.form.get("old_password"))
        new_password1 = sanitize(request.form.get("new_password1"))
        new_password2 = sanitize(request.form.get("new_password2"))

        if flask_bcrypt.check_password_hash(current_user.password, old_password):

            if new_password1 == new_password2:
                password_check_results = password_check(new_password1)
                if password_check_results['password_ok']:
                    success, possible_error = UserService.update_user_password_by_user_id(user_id=current_user.id,
                                                    password_hash=flask_bcrypt.generate_password_hash(new_password1))
                    if not success:
                        current_app.logger.error(f"Error changing password [{possible_error}]")
                        flash("Unable to update password")
                        return render_template("profile.html")
                    else:
                        flash("Password updated")
                        return render_template("profile.html")
                else:
                    flash("Password does not meet the criteria")
                    return profile(current_user.username)

        else:
            flash("Old password is incorrect")
            return render_template("profile.html")






@auth_flask_login.route("/register", methods=["GET", "POST"])
@limiter.limit("5 per minute") if limiter is not None else (lambda f: f)
def register():
    """
    Registers a new user in the application.

    Route: `/register`
    Methods: `GET`, `POST`

    __Args__:
        - None

    __Returns__:
        - If registrations are not allowed, renders the `auth/register.html` template with `allow_registrations` set to `False`.
        - If a `POST` request is made:
            - If the `username` field is empty, flashes an error message and renders the `auth/register.html` template.
            - If the `email` field is empty, flashes an error message and renders the `auth/register.html` template.
            - If the `email` field is not a valid email address (using a simple regex validation), flashes an error message and renders the `auth/register.html` template.
            - If the supplied password does not meet the criteria, flashes an error message and renders the `auth/register.html` template.
            - If a user with the same email or username already exists, flashes an error message and renders the `auth/register.html` template.
            - Otherwise, generates a password hash, generates a confirmation token, creates a new `User` with the provided details, and attempts to save the new user.
                - If the user is successfully added, constructs the text and HTML bodies for the registration email, sends the email to the user's email address, flashes a success message
    *, and renders the `auth/login.html` template.
                - If there is an error adding the user, flashes an error message.
        - If a `GET` request is made or an exception occurs, renders the `auth/register.html` template with `allow_registrations` set to the value of `ALLOW_REGISTRATIONS` from the application
    *'s config.

    __Raises__:
        - Any exception that occurs during the registration process.

    """
    allow_registrations = (int(app.config['ALLOW_REGISTRATIONS']) == 1)
    token_epiration_minutes = int(app.config['TOKEN_EXPIRATION_MINUTES'])

    if not allow_registrations:
        return render_template(template_name_or_list="auth/register.html", allow_registrations=allow_registrations)

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        supplied_password = request.form.get('password', '').strip()

        if not username:
            flash("Username cannot be empty.")
            return render_template(template_name_or_list="auth/register.html", allow_registrations=allow_registrations)

        if not email:
            flash("Email cannot be empty.")
            return render_template(template_name_or_list="auth/register.html", allow_registrations=allow_registrations)

        # Simple email validation, you might want to use a more robust method in production
        if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
            flash("Invalid email address.")
            return render_template(template_name_or_list="auth/register.html", allow_registrations=allow_registrations)

        password_check_results = password_check(supplied_password)
        if not password_check_results['password_ok']:
            flash("Password does not meet the criteria")
            return render_template(template_name_or_list="auth/register.html", allow_registrations=allow_registrations)

        existing_user = UserService.get_user_by_username(username) or UserService.get_user_by_email(email)
        if existing_user:
            # Avoid account enumeration: return a generic response to the client
            flash("If registration was successful, you will receive an email with activation instructions.")
            return render_template(template_name_or_list="auth/register.html", allow_registrations=allow_registrations)

        password_hash = flask_bcrypt.generate_password_hash(supplied_password)

        confirmation_token = secrets.token_urlsafe(32)
        token_expires = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=token_epiration_minutes)

        # prepare User
        new_user = User(username=username, email=email,
                        password=password_hash, token=confirmation_token, token_expires=token_expires)

        try:
            user_added, msg, user = UserService.save_new_user(new_user)
            if user_added:
                post_user_add_hook(new_user=user)
                text_body = render_template(template_name_or_list='email/user_registration.txt', user=username,
                                            token=confirmation_token, token_expires=token_expires.isoformat())
                html_body = render_template(template_name_or_list='email/user_registration.html', user=username,
                                            token=confirmation_token, token_expires=token_expires.isoformat())
                send_email(subject="New user registration", sender=None, recipients=[email],
                           text_body=text_body, html_body=html_body)
                flash("If registration was successful, you will receive an email with activation instructions.")
                return render_template("auth/login.html")
            else:
                flash("Unable to register you at this time")
        except Exception as err:
            current_app.logger.error(f"Exception occurred: {str(err)}", exc_info=True)
            flash("Unable to register with that email address")
            current_app.logger.error("Error on registration - possible duplicate emails")

    return render_template(template_name_or_list="auth/register.html", allow_registrations=allow_registrations)


@auth_flask_login.route("/reauth", methods=["GET", "POST"])
@login_required
def reauth():
    if request.method == "POST":
        confirm_login()
        flash(u"Reauthenticated.")
        return redirect(request.args.get("next") or '/admin')

    template_data = {}
    return render_template(template_name_or_list="auth/reauth.html", **template_data)


@auth_flask_login.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect('/login')


@login_manager.unauthorized_handler
def unauthorized_callback():
    return redirect('/login')


@login_manager.user_loader
def load_user(id):
    """
    Load User

    Loads the user associated with the given ID.

    Parameters:
    - id (int): The ID of the user to load.

    Returns:
    - User: The user with the specified ID, if found and active. If the ID is None or the user is not found or inactive, returns None.

    Note:
    - This method is decorated with the `@login_manager.user_loader` decorator to register it as the user loader function for the current login manager. It is automatically called when loading
    * a user based on the ID.
    """
    # The user loader must return a user object or None. Do not perform redirects here.
    if id is None:
        return None

    # The incoming id may be a string (from the session). Coerce to int when possible.
    try:
        uid = int(id)
    except Exception:
        # Invalid id format
        return None

    user = User.query.filter_by(id=uid).first()
    if user and user.is_active:
        return user
    return None
