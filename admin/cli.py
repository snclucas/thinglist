#!/usr/bin/env python3
"""Admin CLI for ThingList

Subcommands:
  add-user       Add a user (username, email, password) interactively or via flags
  list-users     List users in the database
  reset-password Reset a user's password by username or email
  delete-user    Delete a user by id or username
  activate-user  Activate a user by id or username
  promote        Promote a user to admin by id or username

This CLI runs commands inside the Flask app context so services and DB calls work.
"""

import os
import sys
import argparse
import getpass
from typing import Optional
import logging
import json

# Ensure project root is on sys.path so `import app` works when running this script directly
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from app import app as flask_app
from app import flask_bcrypt
from services.user_service import UserService
from models import User
from app import db


MIN_PASSWORD_LENGTH = 8


def run_in_app_context(fn):
    def wrapper(*args, **kwargs):
        with flask_app.app_context():
            # If using in-memory sqlite for quick test runs, ensure tables exist
            try:
                uri = flask_app.config.get('SQLALCHEMY_DATABASE_URI', '') or ''
                # If sqlite file path used, ensure parent directory exists so DB can be created
                if uri.startswith('sqlite'):
                    # handle in-memory
                    if ':memory:' in uri:
                        is_sqlite_file = False
                    else:
                        # for sqlite file URIs like sqlite:///C:/path/to/db.db or sqlite:///relative.db
                        is_sqlite_file = True
                        # extract path after sqlite:///
                        parts = uri.split('///', 1)
                        if len(parts) == 2:
                            db_path = parts[1]
                        else:
                            # fallback: strip the sqlite:// prefix
                            db_path = uri.replace('sqlite://', '')
                        # Normalize and get parent dir
                        db_path = os.path.abspath(db_path)
                        parent = os.path.dirname(db_path)
                        if parent and not os.path.exists(parent):
                            try:
                                os.makedirs(parent, exist_ok=True)
                            except Exception:
                                pass
                if uri.startswith('sqlite') and (':memory:' in uri or uri.endswith('.db')):
                    # create tables if not present (safe for test/dev only)
                    from sqlalchemy import inspect
                    inspector = inspect(db.engine)
                    # if no tables, create_all
                    if not inspector.get_table_names():
                        db.create_all()
            except Exception:
                # If inspection fails, ignore and proceed (don't block admin actions)
                pass
            return fn(*args, **kwargs)
    return wrapper


@run_in_app_context
def add_user_cmd(username: Optional[str], email: Optional[str], password: Optional[str], interactive: bool = False, json_output: bool = False):
    if interactive:
        if not username:
            username = input('Username: ').strip()
        if not email:
            email = input('Email: ').strip()
        if not password:
            password = getpass.getpass('Password: ')
    else:
        missing = []
        if not username:
            missing.append('--username')
        if not email:
            missing.append('--email')
        if not password:
            missing.append('--password')
        if missing:
            print('Missing required arguments: ' + ', '.join(missing) + '. Or use --interactive', file=sys.stderr)
            return 2

    if not password or len(password) < MIN_PASSWORD_LENGTH:
        print(f'Password must be at least {MIN_PASSWORD_LENGTH} characters', file=sys.stderr)
        return 3

    user = UserService.add_user_by_details(username=username, email=email, password=password)
    if user is None:
        msg = {'success': False, 'error': 'Failed to create user (see logs)'}
        if json_output:
            print(json.dumps(msg))
        else:
            print('Failed to create user (see logs for details)', file=sys.stderr)
        return 1
    result = {'success': True, 'id': user.id, 'username': user.username, 'email': user.email}
    if json_output:
        print(json.dumps(result))
    else:
        print(f'Created user: id={user.id} username={user.username} email={user.email}')
    return 0


@run_in_app_context
def list_users_cmd(json_output: bool = False):
    users = db.session.query(User).order_by(User.id).all()
    if not users:
        if json_output:
            print(json.dumps([]))
        else:
            print('No users found')
        return 0
    if json_output:
        out = []
        for u in users:
            out.append({'id': u.id, 'username': u.username, 'email': u.email, 'activated': bool(u.activated), 'admin': bool(u.is_admin)})
        print(json.dumps(out))
    else:
        print(f"{'id':>4}  {'username':20}  {'email':30}  {'activated':9}  {'admin':5}")
        print('-' * 80)
        for u in users:
            print(f"{u.id:>4}  {u.username:20}  {u.email:30}  {str(bool(u.activated)):9}  {str(bool(u.is_admin)):5}")
    return 0


@run_in_app_context
def reset_password_cmd(identifier: str, new_password: Optional[str], interactive: bool = False, json_output: bool = False):
    # identifier may be username or email
    if interactive:
        if not new_password:
            new_password = getpass.getpass('New password: ')
    else:
        if not new_password:
            print('Missing --password (or use --interactive)', file=sys.stderr)
            return 2

    if not new_password or len(new_password) < MIN_PASSWORD_LENGTH:
        print(f'Password must be at least {MIN_PASSWORD_LENGTH} characters', file=sys.stderr)
        return 3

    # locate user
    user = UserService.get_user_by_username(identifier) or UserService.get_user_by_email(identifier)
    if not user:
        print(f'User not found for identifier: {identifier}', file=sys.stderr)
        return 4

    password_hash = flask_bcrypt.generate_password_hash(new_password)
    if hasattr(password_hash, 'decode'):
        password_hash = password_hash.decode('utf-8')

    success, err = UserService.update_user_password_by_user_id(user_id=user.id, password_hash=password_hash)
    if not success:
        if json_output:
            print(json.dumps({'success': False, 'error': str(err)}))
        else:
            print(f'Failed to update password: {err}', file=sys.stderr)
        return 1
    if json_output:
        print(json.dumps({'success': True, 'id': user.id, 'username': user.username}))
    else:
        print(f'Password updated for user id={user.id} username={user.username}')
    return 0


@run_in_app_context
def delete_user_cmd(identifier: str, json_output: bool = False):
    # identifier may be numeric id or username
    user = None
    try:
        uid = int(identifier)
        user = UserService.get_user_by_id(uid)
    except Exception:
        user = UserService.get_user_by_username(identifier)

    if not user:
        print(f'User not found: {identifier}', file=sys.stderr)
        return 4

    # Confirmation prompt (interactive safeguard)
    # Check env var set by main when --yes used
    skip_confirm = bool(os.environ.get('CLI_SKIP_CONFIRM', ''))
    if not skip_confirm:
        prompt = f"Are you sure you want to DELETE user id={user.id} username={user.username}? This action is permanent. [y/N]: "
        ans = input(prompt).strip().lower()
        if ans not in ('y', 'yes'):
            print('Aborted.')
            return 0

    ok, msg = UserService.delete_user_by_id(user.id)
    if not ok:
        if json_output:
            print(json.dumps({'success': False, 'error': msg}))
        else:
            print(f'Failed to delete user: {msg}', file=sys.stderr)
        return 1
    if json_output:
        print(json.dumps({'success': True, 'id': user.id, 'username': user.username}))
    else:
        print(f'Deleted user id={user.id} username={user.username}')
    return 0


@run_in_app_context
def activate_user_cmd(identifier: str, json_output: bool = False):
    # accept id (int) or username
    user = None
    try:
        uid = int(identifier)
        user = UserService.get_user_by_id(uid)
    except Exception:
        user = UserService.get_user_by_username(identifier)

    if not user:
        print(f'User not found: {identifier}', file=sys.stderr)
        return 4

    ok = UserService.activate(user.id)
    if not ok:
        if json_output:
            print(json.dumps({'success': False, 'error': 'activation failed'}))
        else:
            print('Failed to activate user (see logs)', file=sys.stderr)
        return 1
    if json_output:
        print(json.dumps({'success': True, 'id': user.id, 'username': user.username}))
    else:
        print(f'Activated user id={user.id} username={user.username}')
    return 0


@run_in_app_context
def promote_user_cmd(identifier: str, json_output: bool = False):
    # accept id or username; set is_admin True
    user = None
    try:
        uid = int(identifier)
        user = UserService.get_user_by_id(uid)
    except Exception:
        user = UserService.get_user_by_username(identifier)

    if not user:
        if json_output:
            print(json.dumps({'success': False, 'error': 'user not found'}))
        else:
            print(f'User not found: {identifier}', file=sys.stderr)
        return 4

    # Confirmation prompt
    skip_confirm = bool(os.environ.get('CLI_SKIP_CONFIRM', ''))
    if not skip_confirm:
        prompt = f"Promote user id={user.id} username={user.username} to admin? [y/N]: "
        ans = input(prompt).strip().lower()
        if ans not in ('y', 'yes'):
            print('Aborted.')
            return 0

    try:
        user.is_admin = True
        db.session.merge(user)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        if json_output:
            print(json.dumps({'success': False, 'error': str(e)}))
        else:
            print(f'Failed to promote user: {e}', file=sys.stderr)
        return 1

    if json_output:
        print(json.dumps({'success': True, 'id': user.id, 'username': user.username, 'is_admin': True}))
    else:
        print(f'Promoted user id={user.id} username={user.username} to admin')
    return 0


@run_in_app_context
def user_get_cmd(identifier: str, json_output: bool = False):
    # accept id or username or email
    user = None
    try:
        uid = int(identifier)
        user = UserService.get_user_by_id(uid)
    except Exception:
        user = UserService.get_user_by_username(identifier) or UserService.get_user_by_email(identifier)

    if not user:
        if json_output:
            print(json.dumps({'success': False, 'error': 'user not found'}))
        else:
            print(f'User not found: {identifier}', file=sys.stderr)
        return 4

    info = {
        'id': user.id,
        'username': user.username,
        'email': user.email,
        'activated': bool(user.activated),
        'is_admin': bool(user.is_admin),
        'created': str(user.user_created) if hasattr(user, 'user_created') else None,
        'profile_text': getattr(user, 'profile_text', None)
    }
    if json_output:
        print(json.dumps({'success': True, 'user': info}, default=str))
    else:
        print('User details:')
        for k, v in info.items():
            print(f'  {k}: {v}')
    return 0


def build_parser():
    # Create a parent parser for common/global options so they can appear before or after subcommand
    parent = argparse.ArgumentParser(add_help=False)
    parent.add_argument('--json', action='store_true', help='Output JSON from commands')
    parent.add_argument('-v', '--verbose', action='count', default=0, help='Increase verbosity (repeat for more)')
    parent.add_argument('-y', '--yes', action='store_true', help='Assume yes to confirmation prompts')

    parser = argparse.ArgumentParser(description='ThingList admin CLI', parents=[parent])
    sub = parser.add_subparsers(dest='cmd')

    # add-user
    p_add = sub.add_parser('add-user', parents=[parent], help='Add a new user')
    p_add.add_argument('-u', '--username')
    p_add.add_argument('-e', '--email')
    p_add.add_argument('-p', '--password')
    p_add.add_argument('-i', '--interactive', action='store_true')

    # list-users
    sub.add_parser('list-users', parents=[parent], help='List users')

    # reset-password
    p_reset = sub.add_parser('reset-password', parents=[parent], help='Reset a user password')
    p_reset.add_argument('identifier', help='username or email (or numeric id)')
    p_reset.add_argument('-p', '--password')
    p_reset.add_argument('-i', '--interactive', action='store_true')

    # delete-user
    p_del = sub.add_parser('delete-user', parents=[parent], help='Delete a user by id or username')
    p_del.add_argument('identifier', help='id or username')

    # activate-user
    p_act = sub.add_parser('activate-user', parents=[parent], help='Activate a user by id or username')
    p_act.add_argument('identifier', help='id or username')

    # promote (make admin)
    p_prom = sub.add_parser('promote', parents=[parent], help='Promote a user to admin')
    p_prom.add_argument('identifier', help='id or username')

    # user-get
    p_get = sub.add_parser('user-get', parents=[parent], help='Get user details by id, username, or email')
    p_get.add_argument('identifier', help='id, username, or email')

    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)

    # configure logging
    log_level = logging.WARNING
    if args.verbose >= 2:
        log_level = logging.DEBUG
    elif args.verbose == 1:
        log_level = logging.INFO
    logging.basicConfig(level=log_level, format='%(levelname)s:%(name)s:%(message)s')

    json_output = bool(getattr(args, 'json', False))
    # If user passed --yes, set an env var so confirmation prompts inside commands skip interaction
    if getattr(args, 'yes', False):
        os.environ['CLI_SKIP_CONFIRM'] = '1'
    else:
        # Ensure it's unset when not requested
        os.environ.pop('CLI_SKIP_CONFIRM', None)

    if args.cmd == 'add-user':
        return_code = add_user_cmd(username=args.username, email=args.email, password=args.password, interactive=args.interactive, json_output=json_output)
    elif args.cmd == 'list-users':
        return_code = list_users_cmd(json_output=json_output)
    elif args.cmd == 'reset-password':
        return_code = reset_password_cmd(identifier=args.identifier, new_password=args.password, interactive=args.interactive, json_output=json_output)
    elif args.cmd == 'delete-user':
        return_code = delete_user_cmd(identifier=args.identifier, json_output=json_output)
    elif args.cmd == 'activate-user':
        return_code = activate_user_cmd(identifier=args.identifier, json_output=json_output)
    elif args.cmd == 'promote':
        return_code = promote_user_cmd(identifier=args.identifier, json_output=json_output)
    elif args.cmd == 'user-get':
        return_code = user_get_cmd(identifier=args.identifier, json_output=json_output)
    else:
        parser.print_help()
        return_code = 0

    if return_code:
        sys.exit(return_code)


if __name__ == '__main__':
    main()

