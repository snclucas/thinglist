import re
import uuid

from flask import current_app, Blueprint, render_template, request, flash, redirect, url_for

from app import login_manager, flask_bcrypt, app
from flask_login import (login_required, login_user, logout_user, confirm_login)

from database_functions import find_user, save_new_user, find_user_by_token, activate_user_in_db, find_user_by_username, \
    find_user_by_email
from email_utils import send_email
from models import User

auth_flask_login = Blueprint('auth_flask_login', __name__, template_folder='templates')


# @auth_flask_login.route('/reset_password/<token>', methods=['GET', 'POST'])
# def reset_password(token):
#     if current_user.is_authenticated:
#         return redirect(url_for('index'))
#     user = User.verify_reset_password_token(token)
#     if not user:
#         return redirect(url_for('index'))
#     form = ResetPasswordForm()
#     if form.validate_on_submit():
#         user.set_password(form.password.data)
#         db.session.commit()
#         flash('Your password has been reset.')
#         return redirect(url_for('login'))
#     return render_template('reset_password.html', form=form)


def sanitize(input_string):
    """
    Sanitizes the given input string by encoding and decoding it using unicode_escape.

    Args:
        input_string (str): The input string to be sanitized.

    Returns:
        str: The sanitized input string.
    """
    # Perform input sanitization
    return input_string.encode('unicode_escape').decode()


@auth_flask_login.route("/login", methods=["GET", "POST"])
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

        username = sanitize(request.form.get("username"))
        password = sanitize(request.form.get("password"))

        user = find_user(username_or_email=username)
        if user and flask_bcrypt.check_password_hash(user.password, password) and user.is_active:
            remember = request.form.get("remember", "no") == "yes"

            if user.activated == 0:
                flash("Account not activated")
                return render_template("auth/login.html")

            if login_user(user, remember=remember):
                return redirect(url_for('main.profile', username=user.username).replace('%40', '@'))
            else:
                flash("Unable to log you in")
        else:
            flash("Unable to log you in")

    allow_registrations = (int(app.config['ALLOW_REGISTRATIONS']) == 1)
    return render_template("auth/login.html", allow_registrations=allow_registrations)


@auth_flask_login.route("/activate-user/<token>", methods=["GET"])
def activate_user(token):
    """
    Activate a user based on the given token.

    :param token: The activation token provided in the URL.
    :type token: str
    :return: The rendered template after user activation.
    :rtype: str
    """
    user_ = find_user_by_token(token=token)
    template = "auth/login.html"

    if user_ is not None and not user_.activated and user_.token == token:
        activate_user_in_db(user_id=user_.id)
        flash("You are now an activated Thing!")

    return render_template(template)


@auth_flask_login.route("/passwd", methods=["GET", "POST"])
@login_required
def change_password():
    current_app.logger.info(request.form)

    if request.method == 'POST':

        username = request.form['username']

        try:
            user_ = find_user(username_or_email=username)
            if user_ is not None:
                confirmation_token = uuid.uuid4().hex

                text_body = render_template('email/reset_password.txt', user=username, token=confirmation_token)
                html_body = render_template('email/reset_password.html', user=username, token=confirmation_token)
                send_email("Password change", sender=app.config['ADMINS'][0], recipients=[user_.email],
                           text_body=text_body, html_body=html_body)

        except Exception as err:
            current_app.logger.error("Error on registration - possible duplicate emails")








        flash("If this account exists, an email will be sent with instructions to reset the password")
        return render_template("auth/reset_password.html")


    else:
        return render_template("auth/reset_password.html")


def password_check(password):
    """
    Check if a password meets the specified criteria.

    Parameters:
    password (str): The password to be checked.

    Returns:
    dict: A dictionary containing the result of the password check.
        - 'password_ok' (bool): True if the password meets the criteria, False otherwise.
        - 'length_error' (bool): True if the password length is less than 8 characters, False otherwise.
        - 'digit_error' (bool): True if the password does not contain any digits, False otherwise.
        - 'uppercase_error' (bool): True if the password does not contain any uppercase letters, False otherwise.
        - 'lowercase_error' (bool): True if the password does not contain any lowercase letters, False otherwise.
        - 'symbol_error' (bool): True if the password does not contain any symbols, False otherwise.
    """
    # calculating the length
    length_error = len(password) < 8
    # searching for digits
    digit_error = re.search(r"\d", password) is None
    # searching for uppercase
    uppercase_error = re.search(r"[A-Z]", password) is None
    # searching for lowercase
    lowercase_error = re.search(r"[a-z]", password) is None
    # searching for symbols
    symbol_error = re.search(r"\W", password) is None
    # overall result
    password_ok = not (length_error or digit_error or uppercase_error or lowercase_error or symbol_error)

    return {
        'password_ok': password_ok,
        'length_error': length_error,
        'digit_error': digit_error,
        'uppercase_error': uppercase_error,
        'lowercase_error': lowercase_error,
        'symbol_error': symbol_error,
    }


@auth_flask_login.route("/register", methods=["GET", "POST"])
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

        existing_user = find_user_by_username(username) or find_user_by_email(email)
        if existing_user:
            flash("User with that email or username already exists")
            return render_template(template_name_or_list="auth/register.html", allow_registrations=allow_registrations)

        # generate password hash
        password_hash = flask_bcrypt.generate_password_hash(supplied_password)

        confirmation_token = uuid.uuid4().hex

        # prepare User
        new_user = User(username=username, email=email, password=password_hash, token=confirmation_token)

        try:
            user_added, msg, user = save_new_user(new_user)
            if user_added:
                text_body = render_template(template_name_or_list='email/user_registration.txt', user=username, token=confirmation_token)
                html_body = render_template(template_name_or_list='email/user_registration.html', user=username, token=confirmation_token)
                send_email(subject="New user registration", sender=app.config['ADMINS'][0], recipients=[email],
                           text_body=text_body, html_body=html_body)
                flash("Check your email for an activation link!")
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
    flash("Logged out.")
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
    if id is None:
        redirect('/login')

    user = User.query.filter_by(id=id).first()
    if user is not None:
        if user.is_active:
            return user
        else:
            return None
