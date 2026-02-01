from app import app, db

from sqlalchemy.exc import SQLAlchemyError

from models import ItemType


def verify_database_setup() -> bool:
    """
    Verify essential DB objects exist. Currently checks for a ItemType with name 'None'.
    Returns True when checks pass, False otherwise.
    """
    with app.app_context():
        try:
            field_none = db.session.query(ItemType).filter(ItemType.name == "None").one_or_none()
            if field_none is None:
                app.logger.error("Database verification failed: missing ItemType with name 'None'")
                return False
            app.logger.debug("Database verification passed: ItemType 'None' exists")
            return True
        except SQLAlchemyError as ex:
            app.logger.exception(f"Database verification error: {ex}")
            try:
                db.session.rollback()
            except Exception:
                pass
            return False
