from threading import Thread
import traceback

from flask import render_template
from flask_mail import Message
from app import app, mail


def threading(f):
    def wrapper(*args, **kwargs):
        thr = Thread(target=f, args=args, kwargs=kwargs)
        thr.daemon = True
        thr.start()
        return thr
    return wrapper


def _choose_sender(explicit_sender=None):
    """Choose a safe sender email address.

    Order of preference:
    1. explicit_sender argument
    2. app.config['MAIL_DEFAULT_SENDER']
    3. first entry in app.config['ADMINS'] if present
    Returns None if no sender is available.
    """
    if explicit_sender:
        return explicit_sender
    default = app.config.get('MAIL_DEFAULT_SENDER')
    if default:
        return default
    admins = app.config.get('ADMINS') or []
    if isinstance(admins, (list, tuple)) and len(admins) > 0:
        return admins[0]
    return None


@threading
def send_email(subject, sender=None, recipients=None, text_body=None, html_body=None):
    # Determine sender safely
    sender_addr = _choose_sender(explicit_sender=sender)
    if sender_addr is None:
        app.logger.error('No valid email sender configured; skipping send_email')
        return

    with app.app_context():
        try:
            msg = Message(subject, sender=sender_addr, recipients=(recipients or []))
            msg.body = text_body
            msg.html = html_body
            mail.send(msg)
        except Exception:
            # Ensure exceptions inside the thread get logged
            app.logger.exception('Error sending email')
            app.logger.debug(traceback.format_exc())


def inventory_invite_email(user, token: str):
    text_body = render_template('email/inventory_invite.txt', user=user.username, token=token)
    html_body = render_template('email/inventory_invite.html', user=user.username, token=token)

    send_email("New user registration",
               sender=None,
               recipients=[user.email],
               text_body=text_body,
               html_body=html_body)



def new_registration_email(user, token: str):
    text_body = render_template('email/user_registration.txt', user=user.username, token=token)
    html_body = render_template('email/user_registration.html', user=user.username, token=token)

    send_email("New user registration",
               sender=None,
               recipients=[user.email],
               text_body=text_body,
               html_body=html_body)


def send_password_reset_email(user):
    # This assumes `user` has a method `get_reset_password_token` if present.
    token = None
    if hasattr(user, 'get_reset_password_token'):
        token = user.get_reset_password_token()
    send_email('[ThingList] Reset Your Password',
               sender=None,
               recipients=[user.email],
               text_body=render_template('email/reset_password.txt',
                                         user=user, token=token),
               html_body=render_template('email/reset_password.html',
                                         user=user, token=token))
