from threading import Thread

from flask import render_template
from flask_mail import Message
from app import app, mail


def threading(f):
    def wrapper(*args, **kwargs):
        thr = Thread(target=f, args=args, kwargs=kwargs)
        thr.start()
    return wrapper


@threading
def send_email(subject, sender=None, recipients=None, text_body=None, html_body=None):
    if sender is None:
        sender = app.config['ADMINS'][0]

    with app.app_context():
        msg = Message(subject, sender=sender, recipients=recipients)
        msg.body = text_body
        msg.html = html_body
        mail.send(msg)


def inventory_invite_email(user, token: str):
    text_body = render_template('email/inventory_invite.txt', user=user.username, token=token)
    html_body = render_template('email/inventory_invite.html', user=user.username, token=token)

    send_email("New user registration",
               sender=app.config['ADMINS'][0],
               recipients=[user.email],
               text_body=text_body,
               html_body=html_body)



def new_registration_email(user, token: str):
    text_body = render_template('email/user_registration.txt', user=user.username, token=token)
    html_body = render_template('email/user_registration.html', user=user.username, token=token)

    send_email("New user registration",
               sender=app.config['ADMINS'][0],
               recipients=[user.email],
               text_body=text_body,
               html_body=html_body)


def send_password_reset_email(user):
    token = user.get_reset_password_token()
    send_email('[Microblog] Reset Your Password',
               sender=app.config['ADMINS'][0],
               recipients=[user.email],
               text_body=render_template('email/reset_password.txt',
                                         user=user, token=token),
               html_body=render_template('email/reset_password.html',
                                         user=user, token=token))
