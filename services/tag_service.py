
from typing import Optional, List

from sqlalchemy.exc import SQLAlchemyError
from app import db, app
from models import  Tag

class TagService:

    @staticmethod
    def get_all_user_tags(user_id: int) -> List[Tag]:
        """
        Retrieves all tags associated with a specific user.

        Args:
            user_id (int): The ID of the user whose tags are to be fetched.

        Returns:
            list[Tag]: A list of Tag objects associated with the given user ID.

        Notes:
            - This function assumes that the `user_id` is valid and exists in the database.
            - The function executes within the Flask application context to ensure proper database session handling.
        """
        with app.app_context():
            try:
                tags = db.session.query(Tag).filter(Tag.user_id == user_id).all()
            except SQLAlchemyError as ex:
                app.logger.error(f"Error fetching tags for user {user_id}: {ex}")
                db.session.rollback()
                return []
        return tags

    @staticmethod
    def get_tag_by_id(tag_id: int) -> Optional[Tag]:
        """
       Fetches a tag object from the database based on the provided tag ID.

       Args:
           tag_id (int): The ID of the tag to search for.

       Returns:
           Optional[Tag]: The Tag object if found, or None if the input is None.

       Raises:
           ValueError: If the tag is not found in the database.
           SQLAlchemyError: If a database error occurs during the query.

       Notes:
           - Logs an error message and rolls back the session in case of a database error.
           - Ensures that a `ValueError` is raised if the tag does not exist.
       """
        if tag_id is None:
            return None
        try:
            tag = db.session.get(Tag, tag_id)
        except SQLAlchemyError as ex:
            app.logger.error(f"Error fetching tag {tag_id}: {ex}")
            db.session.rollback()
            raise
        if tag is None:
            raise ValueError("tag not found")
        return tag

    @staticmethod
    def get_tag_by_str(tag_str: str) -> Optional[Tag]:
        """
        Fetches a tag object from the database based on the provided tag string.

        Args:
            tag_str (str): The string representation of the tag to search for.

        Returns:
            Optional[Tag]: The Tag object if found, or None if the input is None.

        Raises:
            ValueError: If the tag is not found in the database.
            SQLAlchemyError: If a database error occurs during the query.

        Notes:
            - Logs an error message and rolls back the session in case of a database error.
            - Ensures that a `ValueError` is raised if the tag does not exist.
        """
        if tag_str is None:
            return None
        try:
            tag = db.session.query(Tag).filter_by(tag=tag_str).one_or_none()
        except SQLAlchemyError as ex:
            app.logger.error(f"Error fetching tag {tag_str}: {ex}")
            db.session.rollback()
            raise
        if tag is None:
            raise ValueError("tag not found")
        return tag

