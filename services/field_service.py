from slugify import slugify
from sqlalchemy import select, or_
from sqlalchemy.exc import SQLAlchemyError
from app import db, app
from database.database_functions import get_or_create, _commit
from models import User, Field, ItemField


class FieldService:

    @staticmethod
    def delete_all_user_fields(user_id: int) -> int:
        if not user_id:
            return 0

        with app.app_context():
            fields = Field.query.filter_by(user_id=user_id).all()
            for field in fields:
                db.session.delete(field)

            status, msg = _commit()
            if not status:
                app.logger.error(f"Could not delete user fields: {msg}")
                return 0

            return len(fields)

    @staticmethod
    def get_all_user_and_system_fields(user_id: int):
        with app.app_context():
            query = Field.query.filter(or_(Field.user_id == user_id, Field.user_id.is_(None)))
            return db.session.execute(query).all()

    @staticmethod
    def get_all_system_fields():
        with app.app_context():
            query = Field.query.filter(Field.user_id.is_(None))
            return db.session.execute(query).all()

    @staticmethod
    def get_all_user_fields(user_id: int):
        with app.app_context():
            query = Field.query.filter(Field.user_id == user_id)
            return [row[0] for row in db.session.execute(query).all()]

    @staticmethod
    def set_field_status(item_id, field_ids, is_visible=True) -> bool:
        try:
            item_id = int(item_id)
            field_ids = {int(fid) for fid in (field_ids or [])} if isinstance(field_ids, (list, set, tuple)) else {int(field_ids)}
        except (TypeError, ValueError):
            return False

        with app.app_context():
            try:
                existing = {row.field_id: row for row in ItemField.query.filter_by(item_id=item_id).all()}
                for fid in field_ids:
                    if fid in existing:
                        existing[fid].show = True
                        existing.pop(fid)
                    else:
                        db.session.add(ItemField(item_id=item_id, field_id=fid, show=True))
                for row in existing.values():
                    db.session.delete(row)
                db.session.commit()
                return True
            except SQLAlchemyError as ex:
                app.logger.error(f"set_field_status failed: {ex}")
                db.session.rollback()
                return False

    @staticmethod
    def get_all_fields():
        with app.app_context():
            try:
                return Field.query.all()
            except SQLAlchemyError as ex:
                app.logger.error(f"Error fetching all fields: {ex}")
                db.session.rollback()
                return []

    @staticmethod
    def get_field_by_slug(slug: str):
        return Field.query.filter_by(slug=slug).first() if slug else None

    @staticmethod
    def add_field(field_name: str, field_type: str, user_id: int):
        with app.app_context():
            slug = slugify(field_name)
            return get_or_create(Field, field=field_name, type=field_type, user_id=user_id, slug=slug)

    @staticmethod
    def edit_user_field_by_id(field_id: int, field_name: str, field_type: str, user_id: int) -> bool:
        if not field_id or not field_name:
            return False

        with app.app_context():
            field = Field.query.filter_by(id=field_id, user_id=user_id).one_or_none()
            if field:
                field.field = field_name
                field.type = field_type
                db.session.commit()
                return True
            return False

    @staticmethod
    def delete_fields_from_db(user_id: str, field_ids) -> bool:
        field_ids = [field_ids] if not isinstance(field_ids, list) else field_ids

        with app.app_context():
            try:
                fields = db.session.execute(
                    select(Field).join(User).where(Field.user_id == user_id, Field.id.in_(field_ids))
                ).all()
                for field in fields:
                    db.session.delete(field[0])
                db.session.commit()
                return True
            except SQLAlchemyError as err:
                app.logger.error(f"Failed to delete fields: {err}")
                return False

    @staticmethod
    def find_field_by_name(field_name: str):
        with app.app_context():
            return Field.query.filter_by(slug=slugify(field_name)).one_or_none()

    @staticmethod
    def find_field_by_slug(field_slug: str):
        with app.app_context():
            return Field.query.filter_by(slug=field_slug).one_or_none()

    @staticmethod
    def find_field_by_id(field_id: int):
        with app.app_context():
            return Field.query.filter_by(id=field_id).one_or_none()
