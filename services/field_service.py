
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
    def set_field_status(item_id, field_ids, is_visible=True) -> bool:
        """
        Efficiently set which fields are shown for an item.

        - Normalizes inputs.
        - Loads existing ItemField rows for the item once.
        - Adds/updates/deletes rows as needed.
        - Commits once; rolls back on error.
        Returns True on success, False on failure.
        """
        from sqlalchemy.exc import SQLAlchemyError

        with app.app_context():
            try:
                # normalize item_id
                item_id = int(item_id)
            except (TypeError, ValueError):
                return False

            # normalize field_ids to a set of ints (empty set -> no fields shown)
            desired_ids = set()
            if field_ids is None:
                desired_ids = set()
            elif isinstance(field_ids, (list, tuple, set)):
                try:
                    desired_ids = {int(fid) for fid in field_ids}
                except (TypeError, ValueError):
                    return False
            else:
                # single id provided
                try:
                    desired_ids = {int(field_ids)}
                except (TypeError, ValueError):
                    return False

            try:
                # load existing ItemField rows for this item in one query
                existing = ItemField.query.filter_by(item_id=item_id).all()
                existing_map = {row.field_id: row for row in existing}

                # create or update rows for desired_ids
                for fid in desired_ids:
                    row = existing_map.pop(fid, None)
                    if row:
                        # ensure show is True (preserve other attributes)
                        if not row.show:
                            row.show = True
                    else:
                        # create new visible mapping
                        db.session.add(ItemField(item_id=item_id, field_id=fid, show=True))

                # any remaining rows in existing_map are not desired -> delete them
                for row in existing_map.values():
                    db.session.delete(row)

                db.session.commit()
                return True

            except SQLAlchemyError as ex:
                app.logger.error(f"set_field_status failed: {ex}")
                db.session.rollback()
                return False

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
    def get_field_by_slug(slug: str):
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
