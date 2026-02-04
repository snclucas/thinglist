from sqlalchemy.exc import SQLAlchemyError

from app import db, app
from models import Notification, User
from services.user_service import UserService


class NotificationService:

    @staticmethod
    def delete_notification_by_id(notification_id: int, user: User):
        with app.app_context():
            notification_ = Notification.query.filter_by(id=notification_id).one_or_none()

            if notification_ is not None:
                db.session.delete(notification_)
                # user.notifications.remove(notification_)
                try:
                    db.session.commit()
                    return {
                        "success": True,
                        "message": f"Removed notification with ID {notification_.id} from user @{user.username}"
                    }
                except SQLAlchemyError as error:
                    app.logger.error(
                        f"Error removing notification with ID {notification_id} from user @{user.username}: {str(error)}")
                    return {
                        "success": False,
                        "message": f"Error removing notification with ID {notification_id} from user @{user.username}: {str(error)}"
                    }

            return {
                "success": False,
                "message": f"No notification with ID {notification_id} for user @{user.username}"
            }

    @staticmethod
    def get_all_user_notifications(user_id: int):
        with app.app_context():
            _user = UserService.get_user_by_id(user_id=user_id)
            return _user.notifications

    @staticmethod
    def get_number_of_user_notifications(user_id: int) -> int:
        with app.app_context():
            return len(NotificationService.get_all_user_notifications(user_id=user_id))

    @staticmethod
    def _create_notification(from_user_username: str, message: str) -> Notification:
        return Notification(text=message, from_user_username=from_user_username)

    @staticmethod
    def add_user_notification(to_user_id: int, from_user_id: int, message: str, _ctx=None) -> (bool, str):

        if to_user_id is None or from_user_id is None:
            return None, "To and from user IDs cannot be None"
        if message is None:
            return None, "Message cannot be None"

        if _ctx is None:
            _ctx = app.app_context()
        with _ctx:
            user_ = db.session.query(User).filter(User.id == to_user_id).one()

            if user_ is not None:
                from_user_ = db.session.query(User).filter(User.id == from_user_id).one()
                if from_user_ is not None:
                    notification_ = Notification(text=message, from_user_username=from_user_.username)
                    try:
                        db.session.add(notification_)
                        user_.notifications.append(notification_)
                        db.session.commit()
                        db.session.flush()
                        return notification_.id, "Notification added successfully"
                    except SQLAlchemyError as error:
                        app.logger.error(f"Could not add notification to user {user_.username} due to: {str(error)}")
                        return None, f"Could not add notification to user {user_.username}"
