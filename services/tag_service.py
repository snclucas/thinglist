
from typing import Optional

from sqlalchemy.exc import SQLAlchemyError
from app import db, app
from models import  Tag

class TagService:

    @staticmethod
    def get_all_user_tags(user_id: int) -> list[Tag]:
        with app.app_context():
            res_ = db.session.query(Tag).filter(Tag.user_id == user_id).all()
        return res_

    @staticmethod
    def get_tag_by_id(tag_id: int) -> Optional[Tag]:
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
        if tag_str is None:
            return None
        try:
            tag = db.session.query(Tag).filter_by(name=tag_str).one_or_none()
        except SQLAlchemyError as ex:
            app.logger.error(f"Error fetching tag {tag_str}: {ex}")
            db.session.rollback()
            raise
        if tag is None:
            raise ValueError("tag not found")
        return tag

