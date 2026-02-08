import os
from datetime import datetime
from typing import Tuple, Optional

from sqlalchemy.exc import SQLAlchemyError

from app import db, app, flask_bcrypt
from email_utils import send_email
from models import User


from site_globals import __DEFAULT__

def post_user_add_hook(new_user: User):
    """

    The post_user_add_hook method is used to execute certain actions after a new user is added to the system.

    Parameters:
    - new_user (User): The newly created user object.

    Returns:
    - None

    Example usage:
    post_user_add_hook(new_user)

    """
    with app.app_context():
        from services.inventory_service import InventoryService
        _ret = InventoryService.add_user_list(name=f"{__DEFAULT__}_{new_user.username}",
                                              description=f"Default inventory",
                                              access_level=0,
                                              inventory_type=1,
                                              is_default=True,
                                              user_id=new_user.id)
        from services.location_service import LocationService
        LocationService.get_or_add_new_location(location_name=f"{__DEFAULT__}_{new_user.username}",
                                                location_description=f"Default location",
                                                to_user_id=new_user.id)
        # add_new_user_itemtype(name=_NONE_, user_id=new_user.id)

        # create folder for user uploads
        user_upload_folder = os.path.join(app.config['USER_IMAGES_BASE_PATH'], str(new_user.id))
        if not os.path.exists(user_upload_folder):
            os.makedirs(user_upload_folder)

    # add default locations, types


class UserService:

    @staticmethod
    def send_inventory_invite(recipient_username: str, text_body: str, html_body: str):
        recipient_user_ = UserService.get_user_by_username(username=recipient_username)
        if recipient_user_ is not None:
            send_email("New user registration", recipients=[recipient_user_.email], text_body=text_body,
                       html_body=html_body)


    @staticmethod
    def update_user_password_by_token(token: str, password_hash: str) -> Tuple[bool, Optional[Exception]]:
        with app.app_context():
            with app.app_context():
                user_ = UserService.get_user_by_token(token=token)
                if user_ is not None and user_.activated:
                    user_.password = password_hash
                    user_.token = ""
                    try:
                        db.session.merge(user_)
                        db.session.commit()
                        return True, None
                    except Exception as e:
                        db.session.rollback()
                        return False, e
            return False, None

    @staticmethod
    def update_user_password_by_user_id(user_id: int, password_hash: str) -> Tuple[bool, Optional[Exception]]:
        with app.app_context():
            user_ = UserService.get_user_by_id(user_id=user_id)
            if user_ is not None and user_.activated:
                user_.password = password_hash
                user_.token = ""
                try:
                    db.session.merge(user_)
                    db.session.commit()
                    return True, None
                except Exception as e:
                    db.session.rollback()
                    return False, e
        return False, None

    @staticmethod
    def save_new_user(user_: User, fail_on_duplicate: bool = True) -> Tuple[bool, str, Optional[User]]:
        """
        Saves a new user to the database.

        Parameters:
        - user_ (User): The user object to be saved.

        Return:
        - Tuple[bool, str, Optional[User]]: A tuple containing the following values:
          - success (bool): True if the user was successfully saved, False otherwise.
          - message (str): A message indicating the result of the save operation.
          - user_ (Optional[User]): The saved user object, if the save operation was successful.
            Otherwise, None is returned.
        """
        with app.app_context():
            potential_user_ = UserService.get_user_by_username(username=user_.username)
            if potential_user_ is not None and not fail_on_duplicate:
                return True, "duplicate", potential_user_

            if potential_user_ is not None:
                return False, "Username taken", None

            potential_user_ = UserService.get_user_by_email(email=user_.email)
            if potential_user_ is not None:
                return False, "Email taken", None

            db.session.add(user_)

            try:
                db.session.commit()
            except SQLAlchemyError as err:
                app.logger.error(f"Error saving new user: {str(err)}")

            post_user_add_hook(new_user=user_)

            return True, "success", user_

    @staticmethod
    def add_user_by_details(username: str, email: str, password: str, fail_on_duplicate: bool = True) -> Optional[User]:
        """
        Create and persist a new user from basic details.

        Performs basic validation, hashes the password, delegates persistence to
        `save_new_user`, and returns the persisted User on success or `None` on failure.
        """
        if not username or not isinstance(username, str):
            app.logger.error("add_user_by_details: invalid username")
            return None
        if not email or not isinstance(email, str):
            app.logger.error("add_user_by_details: invalid email")
            return None
        if not password or not isinstance(password, str) or len(password) < 6:
            app.logger.error("add_user_by_details: invalid password (min length 6)")
            return None

        with app.app_context():
            try:
                password_hash = flask_bcrypt.generate_password_hash(password)
                # Flask\-Bcrypt may return bytes; convert to string when needed
                if hasattr(password_hash, "decode"):
                    password_hash = password_hash.decode("utf-8")

                user = User(username=username, email=email, password=password_hash, activated=True)

                status, message, saved_user = UserService.save_new_user(user_=user, fail_on_duplicate=fail_on_duplicate)

                if status:
                    return saved_user
                else:
                    app.logger.error(f"Error adding user by details: {message}")
                    return None

            except Exception as exc:
                app.logger.exception(f"Unexpected error in add_user_by_details: {str(exc)}")
                return None

    @staticmethod
    def update_user_token_by_email(email: str, user_token: str, token_expires: datetime):
        with app.app_context():
            user_ = UserService.get_user_by_email(email=email)
            if user_ is not None and user_.activated:
                user_.token = user_token
                user_.token_expires = token_expires
                db.session.merge(user_)
                db.session.commit()
            return

    @staticmethod
    def get_user_by_username(username: str) -> Optional[User]:
        if not username:
            return None
        try:
            return db.session.query(User).filter_by(username=username).one_or_none()
        except SQLAlchemyError as ex:
            app.logger.error(f"Error fetching user by username: {ex}")
            db.session.rollback()
            return None

    @staticmethod
    def get_user_by_email(email: str) -> Optional[User]:
        if not email:
            return None
        try:
            return db.session.query(User).filter_by(email=email).one_or_none()
        except SQLAlchemyError as ex:
            app.logger.error(f"Error fetching user by email: {ex}")
            db.session.rollback()
            return None

    @staticmethod
    def get_user_by_token(token: str) -> Optional[User]:
        if not token:
            return None
        try:
            return db.session.query(User).filter_by(token=token).one_or_none()
        except SQLAlchemyError as ex:
            app.logger.error(f"Error fetching user by token: {ex}")
            db.session.rollback()
            return None

    @staticmethod
    def get_user_by_id(user_id: int) -> Optional[User]:
        if not user_id:
            return None
        try:
            return db.session.query(User).filter_by(id=user_id).one_or_none()
        except SQLAlchemyError as ex:
            app.logger.error(f"Error fetching user by token: {ex}")
            db.session.rollback()
            return None

    @staticmethod
    def delete_user_by_id(user_id: int) -> Tuple[bool, str]:
        """Delete a user by ID. Returns (success, message)."""
        if user_id is None:
            return False, "User ID cannot be None"

        try:
            user_ = db.session.get(User, user_id)
            if user_ is None:
                return False, f"User with ID {user_id} not found"
            db.session.delete(user_)
            db.session.commit()
            return True, f"User with ID {user_id} removed successfully"
        except SQLAlchemyError as e:
            app.logger.exception(f"Error removing user by ID {user_id}: {e}")
            db.session.rollback()
            return False, str(e)
        except Exception as e:
            app.logger.exception(f"Unexpected error removing user by ID {user_id}: {e}")
            db.session.rollback()
            return False, str(e)

    @staticmethod
    def activate(user_id: int) -> bool:
        if user_id is None:
            app.logger.error("activate_user called with user_id=None")
            return False

        with app.app_context():
            try:
                user_ = db.session.query(User).filter(User.id == user_id).one_or_none()
                if user_ is None:
                    app.logger.warning(f"User not found: {user_id}")
                    return False

                if user_.activated:
                    return True

                user_.activated = True
                db.session.commit()
                return True
            except SQLAlchemyError as ex:
                app.logger.error(f"Could not activate user {user_id}: {str(ex)}")
                db.session.rollback()
                return False
            except Exception as ex:
                app.logger.error(f"Unexpected error activating user {user_id}: {str(ex)}")
                db.session.rollback()
                return False

