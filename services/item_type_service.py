from typing import Optional, Union, Tuple, Dict

from slugify import slugify
from sqlalchemy import or_, select
from sqlalchemy.exc import SQLAlchemyError

from app import app, db
from database_utils import _to_dict, _commit
from models import ItemType, Item

from site_globals import __NONE__, __none__


def _get_itemtype_id(item_data: dict, user_id: str) -> Optional[int]:
    """

    Method: _get_itemtype_id

    Parameters:
    - item_data (dict): A dictionary containing data about the item.
    - user_id (str): An instance of the User ID representing the user.

    Description:
    This method is used to get the ID of an item type based on the provided item data and user.

    Returns:
    - int: The ID of the item type. If the item type does not exist, it creates a new one and returns its ID.

    """
    with app.app_context():
        if 'item_type' not in item_data:
            return None

        if item_data['item_type'] is None:
            return None

        if item_data['item_type'] == "":
            return None

        if user_id is None:
            return None

        if not isinstance(item_data, dict):
            return None
        # this is broken
        select_itemtype = select(ItemType).where(ItemType.name == item_data['item_type']).where(
            ItemType.user_id == user_id)
        itemtype_result = db.session.execute(select_itemtype).first()
        if itemtype_result is None:
            new_itemtype_ = ItemType(name=item_data['item_type'], user_id=user_id)
            db.session.add(new_itemtype_)
            db.session.commit()
            db.session.flush()
            return new_itemtype_.id
        return itemtype_result[0].id




class ItemTypeService:

    @staticmethod
    def get_itemtype_by_slug(slug: str, user_id: int = None) -> Optional[ItemType]:
        with app.app_context():
            item_type_ = ItemType.query.filter_by(slug=slug.lower().strip()) \
                .filter(or_(ItemType.user_id == user_id, ItemType.user_id == None)).one_or_none()

            if item_type_ is not None:
                return item_type_

            return None

    @staticmethod
    def get_user_or_system_item_type(user_id: Optional[int], item_type_name_or_slug: str) -> Optional[ItemType]:
        """
        Return an ItemType matching the given slug/name for the user or the global (system) one.

        - If `item_type_name_or_slug` is falsy returns None.
        - If `user_id` is None only returns system item types (user_id IS NULL).
        - Handles DB errors and performs rollback on failure.
        """
        if not item_type_name_or_slug:
            return None

        try:
            slug = slugify(item_type_name_or_slug)
        except Exception:
            slug = str(item_type_name_or_slug).lower()

        with app.app_context():
            try:
                q = db.session.query(ItemType).filter(ItemType.slug == slug)
                if user_id is None:
                    q = q.filter(ItemType.user_id.is_(None))
                else:
                    q = q.filter(or_(ItemType.user_id == user_id, ItemType.user_id.is_(None)))
                return q.one_or_none()
            except SQLAlchemyError as ex:
                app.logger.error(f"get_user_or_system_item_type error: {ex}")
                db.session.rollback()
                return None

    @staticmethod
    def get_or_add_new_user_item_type(name: str = None, user_id: int = None) -> Tuple[bool, str, Optional[Dict]]:
        with app.app_context():
            if name is None or name == "":
                app.logger.error(f"System tried to add user item with name {name} for user {user_id}")
                return False, f"Item type name cannot be None or blank", None

            if user_id is None:
                app.logger.error(f"System tried to add user item with user_id {user_id} for user {user_id}")
                return False, f"User ID cannot be None", None

            # convert to lower case
            name = name.lower().strip()
            _slug = slugify(name)
            existing_item_type_ = ItemTypeService.get_itemtype_by_slug(slug=_slug, user_id=user_id)

            if existing_item_type_ is None:
                new_item_type_ = ItemType(name=name.lower(), user_id=user_id)
                db.session.add(new_item_type_)

                try:
                    db.session.commit()
                    db.session.flush()
                    db.session.refresh(new_item_type_)
                    new_item_type_ = db.session.merge(new_item_type_)
                    return True, f"Item type {name} added for user {user_id}", _to_dict(new_item_type_)
                except SQLAlchemyError as ex:
                    app.logger.error(f"Could not add new item type {name} for user {user_id}: [{str(ex)}]")
                    return False, f"Could not add new item type {name} for user {user_id}", None

            return True, f"Item type {name} exists for {user_id}", _to_dict(existing_item_type_)

    @staticmethod
    def delete_item_types_by_id(itemtype_ids: Union[int, list[int]], user_id: int) -> Tuple[bool, str]:
        """
        Delete user item types safely.

        - Accepts an int or list of ints for `itemtype_ids`.
        - Ensures a per-user `__NONE__` ItemType exists (creates it if missing).
        - Reassigns any Items referencing the deleted types to the `__NONE__` type.
        - Performs bulk update and bulk delete within a single transaction.
        - Logs exceptions and rolls back on error.
        """
        if not isinstance(user_id, int):
            app.logger.error("delete_item_types_by_id: user_id must be an integer")
            return False, "Invalid user_id"

        # normalize itemtype_ids to unique list of ints
        if itemtype_ids is None:
            return False, "itemtype_ids cannot be None"
        if not isinstance(itemtype_ids, list):
            itemtype_ids = [itemtype_ids]

        try:
            itemtype_ids = list({int(i) for i in itemtype_ids})
        except (TypeError, ValueError):
            app.logger.error("delete_item_types_by_id: itemtype_ids must be int or list of ints")
            return False, "Invalid itemtype_ids"

        if len(itemtype_ids) == 0:
            return False, "No item type ids provided"

        with app.app_context():
            try:
                none_type = ItemTypeService.get_itemtype_by_slug(slug=__none__)

                # Fetch item types to delete (only those belonging to this user)
                stmt = select(ItemType).where(ItemType.user_id == user_id, ItemType.id.in_(itemtype_ids))
                to_delete = db.session.execute(stmt).scalars().all()

                if not to_delete:
                    return False, "No matching item types found for deletion"

                # Exclude the __NONE__ type from deletion if it was included
                ids_to_delete = [it.id for it in to_delete if it.id != none_type.id]
                if not ids_to_delete:
                    return False, "Requested item types include only the reserved None type; nothing deleted"

                # Reassign items referencing the types to delete to the None type (bulk update)
                updated = db.session.query(Item).filter(
                    Item.user_id == user_id,
                    Item.item_type.in_(ids_to_delete)
                ).update({Item.item_type: none_type.id}, synchronize_session=False)

                # Delete the ItemType rows (bulk delete)
                deleted = db.session.query(ItemType).filter(
                    ItemType.user_id == user_id,
                    ItemType.id.in_(ids_to_delete)
                ).delete(synchronize_session=False)

                db.session.commit()
                return True, f"Deleted {deleted} item type(s), reassigned {updated} item(s) to '{__NONE__}'"
            except SQLAlchemyError as ex:
                app.logger.exception(f"Error deleting item types for user_id={user_id}: {ex}")
                try:
                    db.session.rollback()
                except Exception:
                    pass
                return False, "Database error deleting item types"

    @staticmethod
    def get_all_user_item_types(user_id: int, string_list: bool = True) -> list:
        """
        Return either a list of item type names (strings) or ItemType objects for a user.

        - Validates `user_id`.
        - Uses SQLAlchemy `select(...).scalars()` for a flat result when requesting names.
        - Logs exceptions, rolls back on error, and returns an empty list on failure.
        """
        if not isinstance(user_id, int):
            app.logger.error("get_all_user_item_types: user_id must be an integer")
            return []

        with app.app_context():
            try:
                if string_list:
                    stmt = select(ItemType.name).where(ItemType.user_id == user_id)
                    names = db.session.execute(stmt).scalars().all()
                    return [n for n in names if n is not None]
                else:
                    stmt = select(ItemType).where(ItemType.user_id == user_id)
                    types = db.session.execute(stmt).scalars().all()
                    return types
            except SQLAlchemyError as e:
                app.logger.exception(f"Error fetching item types for user_id={user_id}: {e}")
                try:
                    db.session.rollback()
                except Exception:
                    pass
                return []

    @staticmethod
    def get_user_item_type_count(user_id: int) -> int:
        with app.app_context():
            item_type_count_ = db.session.query(ItemType).filter(ItemType.user_id == user_id).count()
            return item_type_count_

    @staticmethod
    def find_user_item_type_by_name(item_type_name: str, user_id: int) -> ItemType:
        with app.app_context():
            item_type_ = ItemType.query.filter_by(name=item_type_name).filter_by(user_id=user_id).first()
            return item_type_

    @staticmethod
    def delete_all_user_item_types(user_id: int) -> int:
        """
        Deletes all item types associated with a user.

        Args:
            user_id (int): The ID of the user whose item types are to be deleted.

        Returns:
            int: The number of item types deleted.
        """
        if user_id is None:
            return 0

        with app.app_context():
            item_types_to_delete = ItemType.query.filter_by(user_id=user_id).all()
            number_item_types_deleted = 0

            for item_type in item_types_to_delete:
                db.session.delete(item_type)
                number_item_types_deleted += 1

            status, msg = _commit()
            if not status:
                app.logger.error(f"Could not delete user item types: {msg}")
                return 0

            return number_item_types_deleted

    @staticmethod
    def find_item_type_by_text(type_text: str, user_id: int = None) -> Optional[dict]:
        with app.app_context():

            if user_id is None:
                item_type_ = ItemType.query.filter_by(name=type_text.lower().strip()).one_or_none()
            else:
                item_type_ = ItemType.query.filter_by(name=type_text.lower().strip()) \
                    .filter_by(user_id=user_id).one_or_none()

            if item_type_ is not None:
                return _to_dict(item_type_)

            return None

    @staticmethod
    def get_all_user_and_system_item_types(user_id: int, string_list=True) -> list:
        with app.app_context():
            query_statement = db.session.query(ItemType.name) if string_list else db.session.query(ItemType)
            query_statement = query_statement.filter(or_(ItemType.user_id == user_id, ItemType.user_id == None))
            query_result = db.session.execute(query_statement).all()
            return [row[0] for row in query_result if query_result is not None]

    @staticmethod
    def get_user_item_type(user_id: int, item_type_name: None) -> ItemType:
        with app.app_context():
            query_statement = db.session.query(ItemType)
            query_statement = query_statement.filter(ItemType.name == item_type_name)
            query_statement = query_statement.filter(ItemType.user_id == user_id)
            query_result = db.session.execute(query_statement).one_or_none()
            return query_result[0]
