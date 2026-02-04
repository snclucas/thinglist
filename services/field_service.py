
from slugify import slugify
from sqlalchemy import select, or_
from sqlalchemy.exc import SQLAlchemyError
from app import db, app
from database.database_functions import get_or_create, _commit

from models import User, Field, ItemField


class FieldService:

    @staticmethod
    def delete_all_user_fields(user_id: int) -> int:
        """
        Deletes all fields associated with a user.

        Args:
            user_id (int): The ID of the user whose fields are to be deleted.

        Returns:
            int: The number of fields deleted.
        """
        if user_id is None:
            return 0

        with app.app_context():
            fields_to_delete = Field.query.filter_by(user_id=user_id).all()
            number_fields_deleted = 0

            for field_ in fields_to_delete:
                db.session.delete(field_)
                number_fields_deleted += 1

            status, msg = _commit()
            if not status:
                app.logger.error(f"Could not delete user fields: {msg}")
                return 0

            return number_fields_deleted

    @staticmethod
    def get_all_user_and_system_fields(user_id: int):
        with app.app_context():
            q_ = db.session.query(Field).filter(or_(Field.user_id == user_id, Field.user_id.is_(None)))
            res_ = db.session.execute(q_).all()
            return res_

    @staticmethod
    def get_all_system_fields():
        with app.app_context():
            q_ = db.session.query(Field).filter(Field.user_id is None)
            res_ = db.session.execute(q_).all()
            return res_

    @staticmethod
    def get_all_user_fields(user_id: int):
        with app.app_context():
            q_ = db.session.query(Field).filter(Field.user_id == user_id)
            res_ = db.session.execute(q_).all()
            return [r[0] for r in res_]

    @staticmethod
    def set_field_status(item_id, field_ids, is_visible=True):
        with app.app_context():

            all_fields = FieldService.get_all_fields()

            for field_name, field in dict(all_fields).items():
                show = (field.id in field_ids)

                instance_ = ItemField.query.filter_by(item_id=int(item_id), field_id=int(field.id)).first()
                if instance_:
                    if show:
                        instance_.show = show
                    else:
                        db.session.delete(instance_)
                    db.session.commit()
                else:
                    if show:
                        instance_ = ItemField(item_id=int(item_id), field_id=int(field.id), show=show)
                        db.session.add(instance_)

                db.session.commit()

    @staticmethod
    def get_all_fields():
        """
        Returns a list of all Field ORM instances from the database.
        """
        with app.app_context():
            try:
                return db.session.query(Field).all()
            except SQLAlchemyError as ex:
                app.logger.error(f"Error fetching all fields: {ex}")
                db.session.rollback()
                return []

    @staticmethod
    def get_by_slug(slug: str):
        if not slug:
            return None
        return Field.query.filter_by(slug=slug).first()

    @staticmethod
    def add_field(field_name: str, field_type: str, user_id: int):
        with app.app_context():
            slug = slugify(field_name)
            return get_or_create(model=Field, field=field_name, type=field_type,
                                 user_id=user_id, slug=slug)

    @staticmethod
    def edit_user_field_by_id(field_id: int, field_name: str, field_type: str, user_id: int) -> bool:

        if field_id is None:
            return False
        if field_name is None:
            return False

        with app.app_context():
            field_ = Field.query.filter_by(id=field_id, user_id=user_id).one_or_none()
            if field_ is not None:
                field_.field = field_name
                field_.type = field_type
                db.session.commit()
                return True

            return False

    @staticmethod
    def delete_fields_from_db(user_id: str, field_ids) -> bool:
        with app.app_context():
            if not isinstance(field_ids, list):
                field_ids = [field_ids]

            stmt = select(Field).join(User) \
                .where(Field.user_id == user_id) \
                .where(Field.id.in_(field_ids))
            fields_ = db.session.execute(stmt).all()

            try:
                for field_ in fields_:
                    db.session.delete(field_[0])
                    db.session.commit()
                return True
            except SQLAlchemyError as err:
                app.logger.error(f"Failed to delete fields from database: {str(err)}")
                return False

    @staticmethod
    def find_field_by_name(field_name: str) -> Field:
        with app.app_context():
            field_slug = slugify(field_name)
            field_ = Field.query.filter(Field.slug == field_slug).one_or_none()
            # return {"id": field_.id, "name": field_.name, "slug": field_.slug}
            return field_

    @staticmethod
    def find_field_by_slug(field_slug: str):
        with app.app_context():
            field_ = Field.query.filter(Field.slug == field_slug).one_or_none()
            return field_

    @staticmethod
    def find_field_by_id(field_id: int):
        with app.app_context():
            field_ = Field.query.filter(Field.id == field_id).one_or_none()
            return field_
