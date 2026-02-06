import os
from typing import Dict, Optional, Union, Tuple

from slugify import slugify
from sqlalchemy import select, or_, func, and_
from sqlalchemy.exc import IntegrityError, SQLAlchemyError, NoResultFound, InvalidRequestError
from app import db, app
from database.database_functions import _commit

from models import UserInventory, Relateditems, Inventory, User, Item, Location, ItemType, \
    TemplateField, Field, Tag, InventoryItem, ItemField
from services.field_service import FieldService
from services.inventory_service import InventoryService
from services.item_type_service import ItemTypeService, _get_itemtype_id
from services.tag_service import TagService
from services.user_service import UserService


class ItemService:

    @staticmethod
    def count_all_user_items(user_id: int) -> int:
        """Return the number of items belonging to `user_id` using an efficient SQL COUNT."""
        if not isinstance(user_id, int):
            app.logger.error("count_all_user_items: user_id must be an integer")
            return 0

        with app.app_context():
            try:
                stmt = select(func.count()).select_from(Item).where(Item.user_id == user_id)
                count = db.session.execute(stmt).scalar_one()
                return int(count or 0)
            except SQLAlchemyError as e:
                app.logger.exception(f"Error counting user items: {e}")
                try:
                    db.session.rollback()
                except Exception:  # noqa
                    pass
                return 0

    @staticmethod
    def get_related_items(item_id: int):
        if item_id is None:
            app.logger.error("get_related_items: item_id cannot be None")
            return []

        # query returns tuples (Relateditems, Item); return only Relateditems instances
        rows = (db.session.query(Relateditems, Item)
                .join(Item, Item.id == Relateditems.related_item_id)
                .filter(Relateditems.item_id == item_id)
                .all())
        if not rows:
            return []
        return [row[0] for row in rows if row is not None]

    @staticmethod
    def get_all_item_fields(item_id: int):
        with app.app_context():
            stmt = select(Field.field, ItemField).join(Item).join(Field, ItemField.field_id == Field.id) \
                .filter(ItemField.item_id == item_id)
            ddd = db.session.execute(stmt).all()
            return ddd

    @staticmethod
    def get_user_unlisted_items(user_id: int):
        with app.app_context():
            user_default_inventory_ = InventoryService.get_user_default_inventory(user_id=user_id)
            items_ = InventoryItem.query.filter_by(user_id=user_id).filter_by(
                inventory_id=user_default_inventory_.id).all()
            return items_

    @staticmethod
    def get_user_unlisted_item_count(user_id: int) -> Optional[int]:
        with app.app_context():
            user_default_inventory_ = InventoryService.get_user_default_inventory(user_id=user_id)
            if user_default_inventory_ is not None:
                item_count = InventoryItem.query.filter_by(inventory_id=user_default_inventory_.id).count()
                return item_count
            else:
                return None

    @staticmethod
    def get_item_fields(item_id: int):
        with app.app_context():
            # stmt = select(Field.field, ItemField).join(Item).join(Field, ItemField.field_id == Field.id) \
            #     .filter(ItemField.item_id == item_id) \
            #     .filter(ItemField.show == True)
            # ddd = db.session.execute(stmt).all()

            stmt = select(Field, ItemField, TemplateField) \
                .join(Field, ItemField.field_id == Field.id) \
                .join(TemplateField, TemplateField.field_id == Field.id) \
                .filter(ItemField.item_id == item_id) \
                .filter(ItemField.show == True)
            ddd = db.session.execute(stmt).all()

            return ddd

    @staticmethod
    def get_item_custom_field_data(user_id: int, item_list=None) -> tuple[dict, list, dict]:
        with app.app_context():
            try:
                q = db.session.query(Item.id, Field.field, ItemField.value, Field.slug) \
                    .join(ItemField, ItemField.field_id == Field.id) \
                    .join(Item, ItemField.item_id == Item.id) \
                    .filter(Item.user_id == user_id) \
                    .filter(ItemField.show.is_(True))

                # allow a single int or any iterable of ids
                if item_list is not None:
                    if isinstance(item_list, (int, str)):
                        q = q.filter(Item.id == int(item_list))
                    else:
                        try:
                            ids = [int(i) for i in item_list]
                            q = q.filter(Item.id.in_(ids))
                        except (TypeError, ValueError):
                            # invalid item_list; return empty
                            return {}, [], {}

                rows = q.all()

                fields_by_item: dict[int, dict] = {}
                list_by_item: dict[int, list] = {}
                slugs_set: set[str] = set()

                for item_id, field_name, value, slug in rows:
                    fields_by_item.setdefault(item_id, {})[field_name] = value
                    list_by_item.setdefault(item_id, []).append({"name": field_name, "value": value, "slug": slug})
                    if slug:
                        slugs_set.add(slug)

                return fields_by_item, list(slugs_set), list_by_item
            except SQLAlchemyError as e:
                app.logger.exception(f"get_item_custom_field_data DB error: {e}")
                try:
                    db.session.rollback()
                except Exception:
                    pass
                return {}, [], {}

    @staticmethod
    def find_items_new(logged_in_user=None, requested_username=None, inventory_id=None, query_params=None):
        from sqlalchemy import asc, desc

        def _safe_int(val, default):
            try:
                return int(val)
            except (TypeError, ValueError):
                return default

        def _pagination_query(q_params, q):
            start = _safe_int(q_params.get("start", 0), 0)
            length = _safe_int(q_params.get("length", 50), 50)
            # enforce sane bounds
            if length <= 0:
                length = 50
            max_len = 500
            if length > max_len:
                length = max_len

            order_0 = q_params.get("order_0", None)
            dir_0 = q_params.get("dir_0", "asc")
            dir_0 = "asc" if dir_0 not in ("asc", "desc") else dir_0

            # map ordering keys to columns; only apply if those tables are present (joins added elsewhere)
            if order_0 == '0':
                q = q.order_by(Item.name.asc() if dir_0 == "asc" else Item.name.desc())
            elif order_0 == '1':
                q = q.order_by(ItemType.name.asc() if dir_0 == "asc" else ItemType.name.desc())
            elif order_0 == '2':
                q = q.order_by(Location.name.asc() if dir_0 == "asc" else Location.name.desc())

            page = start // length
            q = q.limit(length).offset(page * length)
            return q

        def _find_query_parameters(query_, qp):
            if not qp:
                return query_
            item_type = qp.get('item_type')
            item_location = qp.get('item_location')
            item_specific_location = qp.get('item_specific_location')
            item_tags = qp.get('item_tags')

            if item_type not in (None, ''):
                query_ = query_.filter(Item.item_type == item_type)

            if item_location not in (None, ''):
                # Location is explicitly joined in all paths below
                query_ = query_.filter(Location.id == item_location)

            if item_specific_location not in (None, ''):
                query_ = query_.filter(Item.specific_location == item_specific_location)

            if item_tags not in (None, ''):
                tags = [t.strip() for t in str(item_tags).split(",") if t.strip()]
                for tag_ in tags:
                    t_ = TagService.get_tag_by_str(tag_str=tag_)
                    if t_ is not None:
                        # preserve original semantics; if this is a relationship/JSON column adapt accordingly
                        query_ = query_.filter(Item.tags.contains(t_))

            # search term
            search = qp.get("search")
            if search not in (None, ""):
                query_ = query_.filter(Item.name.contains(search))

            return query_

        def _base_entities(include_userinventory=False):
            ents = [Item, ItemType.name, Location.name, InventoryItem.access_level, InventoryItem.is_link]
            if include_userinventory:
                ents.append(UserInventory)
            return ents

        if query_params is None:
            query_params = {}

        try:
            requested_user = None
            logged_in_user_id = getattr(logged_in_user, "id", None)
            request_user_id = None

            if requested_username:
                if logged_in_user and requested_username == getattr(logged_in_user, "username", None):
                    requested_user = logged_in_user
                else:
                    requested_user = UserService.get_user_by_username(username=requested_username)
                if requested_user:
                    request_user_id = requested_user.id

            # require at least one of logged_in_user or requested_user
            if logged_in_user is None and requested_user is None:
                return []

            # --- helpers for each path ---
            def _find_my_items():
                with app.app_context():
                    try:
                        # explicit select_from and joins to avoid cartesian products
                        query = db.session.query(*_base_entities(include_userinventory=True)).select_from(Item)
                        query = query.join(ItemType, ItemType.id == Item.item_type, isouter=True)
                        query = query.join(Location, Location.id == Item.location_id, isouter=True)
                        query = query.join(InventoryItem, InventoryItem.item_id == Item.id)
                        query = query.join(Inventory, Inventory.id == InventoryItem.inventory_id)
                        # ensure we join UserInventory when we filter it
                        query = query.join(UserInventory, UserInventory.inventory_id == Inventory.id)

                        if inventory_id not in (None, ''):
                            query = query.filter(InventoryItem.inventory_id == inventory_id)
                            query = query.filter(UserInventory.inventory_id == inventory_id)
                            query = query.filter(UserInventory.user_id == logged_in_user.id)

                        query = query.filter(Item.user_id == logged_in_user.id)

                        query = _find_query_parameters(query, query_params)
                        query = _pagination_query(query_params, query)
                        return query.all()
                    except SQLAlchemyError:
                        db.session.rollback()
                        app.logger.exception("Error in _find_my_items")
                        return []

            def _find_someone_elses_items_loggedin():
                with app.app_context():
                    try:
                        query = db.session.query(*_base_entities(include_userinventory=True)).select_from(Item)
                        query = query.join(ItemType, ItemType.id == Item.item_type, isouter=True)
                        query = query.join(Location, Location.id == Item.location_id, isouter=True)
                        query = query.join(InventoryItem, InventoryItem.item_id == Item.id)
                        query = query.join(Inventory, Inventory.id == InventoryItem.inventory_id)
                        query = query.join(UserInventory, UserInventory.inventory_id == Inventory.id)

                        if inventory_id not in (None, ''):
                            query = query.filter(InventoryItem.inventory_id == inventory_id)
                            query = query.filter(and_(
                                UserInventory.user_id == logged_in_user.id,
                                UserInventory.inventory_id == inventory_id))

                        if request_user_id is not None:
                            query = query.filter(Item.user_id == request_user_id)

                        query = _find_query_parameters(query, query_params)
                        query = _pagination_query(query_params, query)
                        return query.all()
                    except SQLAlchemyError:
                        db.session.rollback()
                        app.logger.exception("Error in _find_someone_elses_items_loggedin")
                        return []

            def _find_someone_elses_items_notloggedin():
                with app.app_context():
                    try:
                        query = db.session.query(*_base_entities(include_userinventory=True)).select_from(Item)
                        query = query.join(ItemType, ItemType.id == Item.item_type, isouter=True)
                        query = query.join(Location, Location.id == Item.location_id, isouter=True)
                        query = query.join(InventoryItem, InventoryItem.item_id == Item.id)
                        query = query.join(Inventory, Inventory.id == InventoryItem.inventory_id)
                        # still join UserInventory so DB knows the relation even if we don't check a user id
                        query = query.join(UserInventory, UserInventory.inventory_id == Inventory.id)

                        if inventory_id not in (None, ''):
                            query = query.filter(InventoryItem.inventory_id == inventory_id)
                            query = query.filter(UserInventory.inventory_id == inventory_id)

                        if request_user_id is not None:
                            query = query.filter(Item.user_id == request_user_id)

                        query = _find_query_parameters(query, query_params)
                        query = _pagination_query(query_params, query)
                        return query.all()
                    except SQLAlchemyError:
                        db.session.rollback()
                        app.logger.exception("Error in _find_someone_elses_items_notloggedin")
                        return []

            # --- decide path and execute ---
            if logged_in_user is not None and requested_user is None:
                return _find_my_items()

            if logged_in_user is not None and logged_in_user_id == request_user_id:
                return _find_my_items()

            if logged_in_user is not None:
                return _find_someone_elses_items_loggedin()
            else:
                return _find_someone_elses_items_notloggedin()

        except Exception:
            app.logger.exception("Unhandled error in find_items_new")
            return []

    @staticmethod
    def update_item_fields(data, item_id: int):
        with app.app_context():
            stmt2 = select(Field.id, ItemField) \
                .join(Item) \
                .join(Field) \
                .filter(ItemField.item_id == item_id) \
                .filter(ItemField.field_id.in_(list(data.keys())))

            ddd2 = db.session.execute(stmt2).all()

            for k, v in dict(ddd2).items():
                v.value = data[k]

            try:
                db.session.commit()
                db.session.flush()
            except Exception as e:
                db.session.rollback()
                raise e

    @staticmethod
    def find_items_query(requested_username: str, logged_in_user, inventory_id: int, request_params):
        query_params = {
            'item_type': request_params["requested_item_type_id"],
            'item_location': request_params["requested_item_location_id"],
            'item_specific_location': request_params["requested_item_specific_location"],
            'item_tags': request_params["requested_tag_strings"],
            'page': request_params.get("page", 1),
        }

        items_ = ItemService.find_items_new(inventory_id=inventory_id,
                                            query_params=query_params,
                                            requested_username=requested_username,
                                            logged_in_user=logged_in_user)

        item_id_list = []
        data_dict = []
        for i in items_:

            if inventory_id is not None and logged_in_user is not None:
                item_ = i[0]
                types_ = i[1]
                location_ = i[2]
                item_access_level_ = i[3]
                item_is_link_ = i[4]
                # user_inventory_ = i[5]
            else:
                item_ = i[0]
                types_ = i[1]
                location_ = i[2]
                item_access_level_ = i[3]
                item_is_link_ = i[4]
                # user_inventory_ = None

            item_id_list.append(item_.id)
            dat = {"item": item_, "types": types_, "location": location_,
                   "item_access_level": item_access_level_, "item_is_link": item_is_link_}

            data_dict.append(
                dat
            )

        return data_dict, item_id_list

    @staticmethod
    def update_item_by_token(item_data: dict, item_token: str, user: User) -> Dict[
        str, Union[str, Dict[str, Union[int, str]]]]:
        if item_token is None:
            return {
                "status": "error",
                "message": "Item ID cannot be None",
                "item": None
            }

        if user is None:
            return {
                "status": "error",
                "message": "User cannot be None",
                "item": None
            }

        with app.app_context():
            db.session.expire_on_commit = False

            select_statement = select(Item).where(Item.item_token == item_token)  # .where(Item.user_id == user.id)

            item_result = db.session.execute(select_statement).one_or_none()

            if item_result is None:
                return_data = {
                    "status": "error",
                    "message": "Not found",
                    "item": None
                }
                return return_data

            _found = True
            if item_result[0].user_id != user.id:
                _found = False
                for _inv in item_result[0].inventories:
                    for _user in _inv.users:
                        if _user.id == user.id:
                            _found = True

            if not _found:
                return_data = {
                    "status": "error",
                    "message": "",
                    "item": None
                }
                return return_data

            item_result[0].name = item_data['name']
            item_result[0].slug = f"{str(item_result[0].id)}-{slugify(item_data['name'])}"
            item_result[0].description = item_data['description']
            item_result[0].quantity = item_data['item_quantity']
            item_result[0].location_id = item_data['item_location']
            item_result[0].url = item_data.get('item_url', None)
            item_result[0].specific_location = item_data['item_specific_location']

            item_tags = item_data['item_tags']
            tags_objects = []
            if not isinstance(item_data['item_tags'], list):
                item_tags = [t.strip().replace(" ", "@#$") for t in item_data['item_tags'].split(",")]

            for tag in item_tags:
                instance = db.session.query(Tag).filter_by(tag=tag).one_or_none()
                if not instance:
                    instance = Tag(tag=tag, user_id=user.id)
                if instance is not None:
                    tags_objects.append(instance)

            item_result[0].tags = tags_objects

            _item_type = item_data.get('item_type', None)
            if isinstance(_item_type, int):
                item_result[0].item_type = _item_type
            elif isinstance(_item_type, str):
                status, msg, added_item_type = ItemTypeService.get_or_add_new_user_item_type(name=_item_type,
                                                                                             user_id=user.id)
                if status:
                    item_result[0].item_type = added_item_type['id']
                else:
                    # set ity to default "Not Set"
                    item_result[0].item_type = ItemTypeService.get_or_add_new_user_item_type(name=None, user_id=None)

            try:
                db.session.commit()
                return_data = {
                    "status": "success",
                    "message": "",
                    "item": {
                        "id": item_result[0].id,
                        "name": item_result[0].name,
                        "slug": item_result[0].slug,
                        "description": item_result[0].description,
                        "user_id": item_result[0].user_id,
                    }
                }
                return return_data
            except SQLAlchemyError as ex:
                db.session.rollback()
                app.logger.error(
                    f"Could not update item with item_token {item_token} for user {user.username} : {str(ex)}")
                return_data = {
                    "status": "error",
                    "message": "",
                    "item": {
                        "id": None,
                        "name": None,
                        "slug": None,
                        "description": None,
                        "user_id": None,
                    }
                }
                return return_data

    @staticmethod
    def update_item_by_id(item_data: dict, item_id: int, user: User) -> Dict[
        str, Union[str, Dict[str, Union[int, str]]]]:
        if item_id is None:
            return {
                "status": "error",
                "message": "Item ID cannot be None",
                "item": {
                    "id": None,
                    "name": None,
                    "slug": None,
                    "description": None,
                    "user_id": None,
                }
            }

        if user is None:
            return {
                "status": "error",
                "message": "User cannot be None",
                "item": {
                    "id": None,
                    "name": None,
                    "slug": None,
                    "description": None,
                    "user_id": None,
                }
            }

        with app.app_context():
            db.session.expire_on_commit = False

            select_statement = select(Item).where(Item.id == item_id)  # .where(Item.user_id == user.id)

            item_result = db.session.execute(select_statement).one_or_none()

            if item_result is None:
                return_data = {
                    "status": "error",
                    "message": "Not found",
                    "item": {
                        "id": None,
                        "name": None,
                        "slug": None,
                        "description": None,
                        "user_id": None,
                    }
                }
                return return_data

            _found = True
            if item_result[0].user_id != user.id:
                _found = False
                for _inv in item_result[0].inventories:
                    for _user in _inv.users:
                        if _user.id == user.id:
                            _found = True

            if not _found:
                return_data = {
                    "status": "error",
                    "message": "",
                    "item": {
                        "id": None,
                        "name": None,
                        "slug": None,
                        "description": None,
                        "user_id": None,
                    }
                }
                return return_data

            item_result[0].name = item_data['name']
            item_result[0].slug = f"{str(item_result[0].id)}-{slugify(item_data['name'])}"
            item_result[0].description = item_data['description']
            item_result[0].quantity = item_data['item_quantity']
            item_result[0].location_id = item_data['item_location']
            item_result[0].url = item_data['item_url']
            item_result[0].specific_location = item_data['item_specific_location']

            item_tags = item_data['item_tags']
            tags_objects = []
            if not isinstance(item_data['item_tags'], list):
                item_tags = [t.strip().replace(" ", "@#$") for t in item_data['item_tags'].split(",")]

            for tag in item_tags:
                instance = db.session.query(Tag).filter_by(tag=tag).one_or_none()
                if not instance:
                    instance = Tag(tag=tag, user_id=user.id)
                tags_objects.append(instance)

            item_result[0].tags = tags_objects
            item_result[0].item_type = _get_itemtype_id(item_data, user.id)

            try:
                db.session.commit()
                return_data = {
                    "status": "success",
                    "message": "",
                    "item": {
                        "id": item_result[0].id,
                        "name": item_result[0].name,
                        "slug": item_result[0].slug,
                        "description": item_result[0].description,
                        "user_id": item_result[0].user_id,
                    }
                }
                return return_data
            except SQLAlchemyError as ex:
                db.session.rollback()
                app.logger.error(f"Could not update item with id {item_id} for user {user.username} : {str(ex)}")
                return_data = {
                    "status": "error",
                    "message": "",
                    "item": {
                        "id": None,
                        "name": None,
                        "slug": None,
                        "description": None,
                        "user_id": None,
                    }
                }
                return return_data

    @staticmethod
    def get_items_to_delete(user_id: int, item_ids: list, inventory_id: int = None):
        """

        Method: get_items_to_delete

        Parameters:
        - user_id: User ID - The user ID for whom to get the items to be deleted.
        - item_ids: list - A list of item IDs to be deleted.

        Return Type:
        - list - A list of items to be deleted.

        Description:
        This method takes a user and a list of item IDs as parameters and returns a list of items to be deleted. If either the item_ids list is empty or the user parameter is None, it returns
        * 0. Otherwise, it constructs a database statement using SQLAlchemy's select method to retrieve the items associated with the given user and matching the specified item IDs. Finally
        *, it executes the statement and returns a list of items.

        """
        if not item_ids or user_id is None:
            return 0

        if len(item_ids) == 0:
            return 0

        query = db.session.query(Item, InventoryItem).join(InventoryItem, InventoryItem.item_id == Item.id)
        if inventory_id is not None:
            query = query.filter(InventoryItem.inventory_id == inventory_id)
        query = query.filter(Item.user_id == user_id, Item.id.in_(item_ids))

        # return list of (Item, InventoryItem) tuples
        return query.all()

    @staticmethod
    def delete_items(item_ids: list, user_id: int, inventory_id: int = None) -> int:
        """

        Delete Items

        Deletes items based on the given item IDs list and user.

        Parameters:
        - item_ids (list): A list of item IDs to be deleted.
        - user_id (int): The user ID performing the deletion.

        Returns:
        - int: The number of items deleted.

        Note:
        - If the item_ids list is empty or the user is None, the function will return 0.
        - If the item_ids list -s [-1] then all items are deleted.
        - If no item IDs are provided, the function will return 0.
        - Related item relationships and item images associated with each item will also be deleted.

        """
        if not item_ids or user_id is None:
            return 0

        if len(item_ids) == 0:
            return 0

        with app.app_context():
            # if item IDs = [-1] then delete all items
            if len(item_ids) == 1 and item_ids[0] == -1:
                item_ids = InventoryService.get_all_item_ids_in_inventory(user_id=user_id, inventory_id=inventory_id)

            items_to_delete = ItemService.get_items_to_delete(user_id=user_id, item_ids=item_ids,
                                                              inventory_id=inventory_id)

            number_items_deleted = 0
            # Disable autoflush while we stage relationship changes / deletes
            with db.session.no_autoflush:
                for item_, inventory_item_ in items_to_delete:
                    # item_ = item_[0]
                    if item_ is not None:
                        # check if this item is in multiple directories
                        # if so, only remove the link to this item from the current inventory

                        # if this is a link we need to delete the InventoryItem but no the item itself
                        if inventory_item_.is_link is True:
                            db.session.delete(inventory_item_)
                            # status, msg = _commit()
                            # if not status:
                            #    app.logger.error(f"Could not delete item(s) link: {msg}")
                            # return 0

                        if inventory_id is not None:

                            for itinv in item_.inventories:
                                if itinv.id == inventory_id:
                                    item_.inventories.remove(itinv)

                            status, msg = _commit()
                            if status:
                                number_items_deleted += 1

                        # remove related item relationships
                        related_items = ItemService.get_related_items(item_.id)
                        # for related_item in related_items:
                        #     db.session.delete(related_item)
                        for related_item in related_items:
                            # related_item might be a model instance; if not, try to extract first element
                            rel = related_item
                            if isinstance(related_item, (tuple, list)):
                                rel = related_item[0]
                            # guard: only delete mapped instances
                            if rel is None:
                                continue
                            try:
                                db.session.delete(rel)
                            except Exception:
                                # defensive: if it's not a mapped instance, skip
                                app.logger.exception("Could not delete related item entry")
                                continue

                        # remove item images
                        ItemService.delete_item_images(item_, user_id)

                        db.session.delete(item_)
                        number_items_deleted += 1

            status, msg = _commit()
            if not status:
                app.logger.error(f"Could not delete item(s) link: {msg}")
                return 0
            return number_items_deleted

    @staticmethod
    def find_all_my_items(logged_in_user_id: User):
        with app.app_context():
            query = db.session.query(Item)
            query = query.filter(Item.user_id == logged_in_user_id)
            results_ = query.all()
            return results_


    @staticmethod
    def delete_item_images(item_: Item, user_id: int) -> (bool, str):
        if item_ is None:
            return False, "Item ID cannot be None"

        with app.app_context():
            for image_ in item_.images:
                try:
                    os.remove(os.path.join(app.root_path, app.config['USER_IMAGES_BASE_PATH'], str(user_id),
                                           image_.image_filename))
                except OSError as er:
                    app.logger.error(f"Error deleting image file: {image_.image_filename}")
                    app.logger.error(f"Error message: {er}")
                    return False, f"Error deleting image file: {image_.image_filename}"

            item_.images = []
            item_.main_image = None
            try:
                db.session.commit()
                return True, "Item images deleted successfully"
            except SQLAlchemyError:
                db.session.rollback()
                return False, "Error deleting item images"

    @staticmethod
    def change_item_access_level(item_ids: int | list[int], access_level: int, user_id: int) -> tuple[bool, str]:
        """
        Change access level for InventoryItem entries for the given item ids owned by the user.

        Returns (success, message).
        """
        from sqlalchemy import update
        from sqlalchemy.exc import SQLAlchemyError

        # Validate inputs
        if not isinstance(access_level, int) or not isinstance(user_id, int):
            app.logger.error("change_item_access_level: access_level and user_id must be integers")
            return False, "Invalid access_level or user_id"

        # Normalize item_ids to a list of ints
        if item_ids is None:
            return False, "item_ids cannot be None"

        if not isinstance(item_ids, list):
            item_ids = [item_ids]

        # Filter and coerce valid ints, remove duplicates
        try:
            item_ids = list({int(i) for i in item_ids})
        except (TypeError, ValueError):
            app.logger.error("change_item_access_level: item_ids must be integers or list of integers")
            return False, "Invalid item_ids"

        if len(item_ids) == 0:
            return False, "No valid item_ids provided"

        with app.app_context():
            try:
                # Perform a set-based update: update InventoryItem rows for the provided item ids
                # but only for items that belong to the given user (join via Item).
                stmt = (
                    update(InventoryItem)
                    .where(InventoryItem.item_id.in_(item_ids))
                    .where(InventoryItem.item_id == Item.id)
                    .where(Item.user_id == user_id)
                    .values(access_level=access_level)
                )
                result = db.session.execute(stmt)
                db.session.commit()

                changed = result.rowcount if result is not None else 0
                return True, f"Updated access_level for {changed} inventory item(s)"
            except SQLAlchemyError as e:
                app.logger.exception(f"Error changing item access level: {e}")
                try:
                    db.session.rollback()
                except Exception:
                    pass
                return False, "Database error changing access level"

    @staticmethod
    def delete_all_user_items(user_id: int):
        if user_id is None:
            return 0

        with app.app_context():
            item_ids_to_delete = ItemService.get_all_user_item_ids(user_id=user_id)

            number_items_deleted = ItemService.delete_items(item_ids=item_ids_to_delete, user_id=user_id)
            return number_items_deleted

    @staticmethod
    def get_all_user_item_ids(user_id: int) -> list[Item]:
        with app.app_context():
            _query = db.session.query(Item.id).filter(Item.user_id == user_id)
            _ids = [x.id for x in _query.distinct()]

        return _ids

    @staticmethod
    def copy_items(item_ids: list, user: User, inventory_id: int):
        """
            link - just add new line in ItemInventory
            move - change inventory id in ItemInventory
            copy - duplicate item, add new line in ItemInventory
        """
        if not item_ids or user is None:
            msg = "Item IDs cannot be None"
            app.logger.error(msg)
            return {"status": "error", "message": msg, "count": 0}

        if len(item_ids) == 0:
            return {"status": "error", "message": "List of item IDs is empty", "count": 0}

        with app.app_context():
            try:
                if inventory_id == -1:
                    user_default_inventory = InventoryService.get_user_default_inventory(user_id=user.id)
                    if user_default_inventory is None:
                        msg = f"No default inventory found for user {user.username}"
                        app.logger.error(msg)
                        return {"status": "error", "message": msg, "count": 0}

                    inventory_id = user_default_inventory.id

                stmt = db.session.query(Item, InventoryItem) \
                    .join(InventoryItem, InventoryItem.item_id == Item.id) \
                    .join(User) \
                    .where(Item.user_id == user.id) \
                    .where(Item.id.in_(item_ids))
                results_ = db.session.execute(stmt).all()

                for item_, inventory_item_ in results_:

                    tag_arr = []
                    for tag in item_.tags:
                        tag_arr.append(tag.tag.replace("@#$", " "))

                    new_ = InventoryService.add_item_to_inventory(item_name=item_.name, item_desc=item_.description,
                                                                  item_type_name_or_id=item_.item_type,
                                                                  item_quantity=item_.quantity,
                                                                  item_tags=tag_arr, inventory_id=inventory_id,
                                                                  item_location_id=item_.location_id,
                                                                  item_specific_location=item_.specific_location,
                                                                  user_id=user.id, custom_fields=item_.fields)
                    if new_["status"] == "error":
                        # log this error
                        return {"status": "error", "count": 0}

                db.session.commit()
                return {"status": "success", "count": len(results_)}
            except Exception as e:
                # log this error
                return {"status": "error", "count": 0}

    @staticmethod
    def link_items(item_ids: list, user_id: int, inventory_id: int) -> dict:
        """
        Link user's items into another inventory by creating InventoryItem rows with `is_link=True`.

        - Validates inputs and normalizes item ids.
        - Resolves inventory_id == -1 to the user's default inventory.
        - Skips items that are already present in the target inventory.
        - Copies access_level from an existing InventoryItem for the item (if any).
        - Uses a transaction and rolls back on error.
        """
        if user_id is None:
            return {"status": "error", "count": 0, "message": "user_id is required"}

        if not item_ids:
            return {"status": "error", "count": 0, "message": "no item_ids provided"}

        # normalize and deduplicate item ids
        try:
            item_ids_set = {int(i) for i in item_ids}
        except (TypeError, ValueError):
            return {"status": "error", "count": 0, "message": "item_ids must be integers"}

        if not item_ids_set:
            return {"status": "error", "count": 0, "message": "no valid item_ids"}

        with app.app_context():
            try:
                # resolve special inventory id
                if inventory_id == -1:
                    user_default_inventory = InventoryService.get_user_default_inventory(user_id=user_id)
                    if user_default_inventory is None:
                        return {"status": "error", "count": 0, "message": "user default inventory not found"}
                    inventory_id = user_default_inventory.id

                # find items actually owned by the user from the requested ids
                owned_rows = db.session.query(Item.id).filter(Item.user_id == user_id, Item.id.in_(item_ids_set)).all()
                owned_ids = {r[0] for r in owned_rows}
                if not owned_ids:
                    return {"status": "error", "count": 0, "message": "no matching items owned by user"}

                # find which of those items are already present in the target inventory
                existing_in_target = db.session.query(InventoryItem.item_id).filter(
                    InventoryItem.inventory_id == inventory_id,
                    InventoryItem.item_id.in_(owned_ids)
                ).all()
                existing_item_ids = {r[0] for r in existing_in_target}

                # items we need to create links for
                to_link_ids = owned_ids - existing_item_ids
                if not to_link_ids:
                    return {"status": "success", "count": 0, "message": "no new links needed"}

                # get a source InventoryItem for each item to copy access_level (if any)
                src_rows = db.session.query(InventoryItem).filter(InventoryItem.item_id.in_(to_link_ids)).all()
                src_map = {r.item_id: r for r in src_rows}

                new_count = 0
                # create InventoryItem link rows
                for iid in to_link_ids:
                    src = src_map.get(iid)
                    access_level = src.access_level if src is not None else 0
                    new_inv_item = InventoryItem(
                        inventory_id=inventory_id,
                        item_id=iid,
                        access_level=access_level,
                        is_link=True
                    )
                    db.session.add(new_inv_item)
                    new_count += 1

                db.session.commit()
                return {"status": "success", "count": new_count}
            except SQLAlchemyError as e:
                app.logger.exception(f"link_items DB error: {e}")
                try:
                    db.session.rollback()
                except Exception:
                    pass
                return {"status": "error", "count": 0, "message": "database error"}
            except Exception as e:
                app.logger.exception(f"link_items unexpected error: {e}")
                try:
                    db.session.rollback()
                except Exception:
                    pass
                return {"status": "error", "count": 0, "message": "unexpected error"}

    @staticmethod
    def move_items(item_ids: list, user: User, inventory_id: int) -> dict:
        """
        Move items to another inventory by updating InventoryItem.inventory_id.

        - Validates inputs.
        - Resolves inventory_id == -1 to the user's default inventory.
        - Performs a single bulk UPDATE only for InventoryItem rows that belong to items owned by the user.
        - Uses a transaction and rolls back on error.
        """
        from sqlalchemy import update

        if user is None or not isinstance(user, User):
            return {"status": "error", "count": 0, "message": "Invalid user"}

        if not item_ids:
            return {"status": "error", "count": 0, "message": "No item IDs provided"}

        # normalize item_ids to unique ints
        try:
            item_ids_set = {int(i) for i in item_ids}
        except (TypeError, ValueError):
            return {"status": "error", "count": 0, "message": "item_ids must be integers"}

        if len(item_ids_set) == 0:
            return {"status": "error", "count": 0, "message": "No valid item IDs"}

        with app.app_context():
            try:
                # resolve special inventory id
                if inventory_id == -1:
                    user_default_inventory = InventoryService.get_user_default_inventory(user_id=user.id)
                    if user_default_inventory is None:
                        return {"status": "error", "count": 0, "message": "User default inventory not found"}
                    inventory_id = user_default_inventory.id

                # find InventoryItem ids that match ownership (join with Item)
                sel = select(InventoryItem.id).join(Item, Item.id == InventoryItem.item_id).where(
                    Item.user_id == user.id,
                    InventoryItem.item_id.in_(list(item_ids_set))
                )
                rows = db.session.execute(sel).all()
                inventory_item_ids = [r[0] for r in rows]

                if not inventory_item_ids:
                    return {"status": "error", "count": 0, "message": "No matching inventory items found for user"}

                # perform bulk update
                upd = update(InventoryItem).where(InventoryItem.id.in_(inventory_item_ids)).values(
                    inventory_id=inventory_id)
                result = db.session.execute(upd)
                db.session.commit()
                # result.rowcount may be None for some DB backends; fall back to length of ids
                affected = result.rowcount if result.rowcount is not None else len(inventory_item_ids)

                return {"status": "success", "count": int(affected)}
            except SQLAlchemyError as e:
                app.logger.error(f"move_items error: {e}")
                try:
                    db.session.rollback()
                except Exception:
                    pass
                return {"status": "error", "count": 0, "message": "Database error"}
            except Exception as e:
                app.logger.error(f"move_items unexpected error: {e}")
                return {"status": "error", "count": 0, "message": "Unexpected error"}

    @staticmethod
    def get_user_item_count(user_id: int):
        with app.app_context():
            item_count_ = db.session.query(Item).filter(Item.user_id == user_id).count()
            return item_count_

    @staticmethod
    def find_related_items(item_id: int) -> (bool, list[Item]):
        with app.app_context():
            try:
                item_ = Item.query.filter_by(id=item_id).first()
                return True, item_.related_items
            except (NoResultFound, InvalidRequestError, SQLAlchemyError) as err:
                app.logger.error(f"Could not find related items for item with id {item_id} [{str(err)}]")
                return False, []

    @staticmethod
    def unrelate_items_by_id(item1_id: int, item2_id: int) -> (bool, str):
        """

        Unrelate Items By ID

        Unrelates two items by their IDs.

        Parameters:
        - item1_id (int): The ID of the first item.
        - item2_id (int): The ID of the second item.

        Returns:
        - Tuple with two elements representing the result of the operation:
          - success (bool): True if the items were successfully unrelated, False otherwise.
          - message (str): A message describing the result of the operation.

        """
        if item1_id is None or item2_id is None:
            return False, "Item IDs cannot be None"
        with app.app_context():
            item1_ = Item.query.filter(Item.id == item1_id).one_or_none()
            if item1_ is None:
                return False, f"No item with id {item1_id} found"
            item2_ = Item.query.filter(Item.id == item2_id).one_or_none()
            if item2_ is None:
                return False, f"No item with id {item2_id} found"

            if item2_ in item1_.related_items and item1_ in item2_.related_items:
                try:
                    item1_.related_items.remove(item2_)
                    # db.session.commit()
                    item2_.related_items.remove(item1_)
                    db.session.commit()
                    return True, f"Items with ids {item1_id} and {item2_id} unrelated"
                except (TypeError | SQLAlchemyError) as err:
                    app.logger.error(f"Could not unrelate items with ids {item1_id} and {item2_id} [{str(err)}]")
                    db.session.rollback()
                    return False, f"Could not unrelate items with ids {item1_id} and {item2_id}"
            else:
                return False, f"Items with ids {item1_id} and {item2_id} are not related"

    @staticmethod
    def relate_items_by_id(item1_id: int, item2_id: int) -> (bool, str):
        """
        Relates two items by their IDs.

        Parameters:
            item1_id (int): The ID of the first item.
            item2_id (int): The ID of the second item.

        Returns:
            tuple (bool, str): A tuple containing a boolean value and a string.
            The boolean value indicates whether the items were successfully related or not.
            The string provides additional information about the result.

        Raises:
            None
        """
        if item1_id is None or item2_id is None:
            return False, "Item IDs cannot be None"
        with app.app_context():
            item1_ = Item.query.filter(Item.id == item1_id).one_or_none()
            if item1_ is None:
                return False, f"No item with id {item1_id} found"
            item2_ = Item.query.filter(Item.id == item2_id).one_or_none()
            if item2_ is None:
                return False, f"No item with id {item2_id} found"

            if item2_ not in item1_.related_items and item1_ not in item2_.related_items:
                item1_.related_items.append(item2_)
                item2_.related_items.append(item1_)
                try:
                    db.session.commit()
                except SQLAlchemyError:
                    db.session.rollback()
                    return False, f"Could not relate items with ids {item1_id} and {item2_id}"
            else:
                return False, f"Items with ids {item1_id} and {item2_id} are already related"

    @staticmethod
    def edit_items_locations(item_ids: list, user: User, location_id: int, specific_location: str) -> (bool, str):
        """
        Edit items locations.

        Edit the locations of items based on the provided item IDs, user, location ID, and specific location.

        Parameters:
        - item_ids (list): A list of item IDs to edit their locations.
        - user (User): The user object to perform the edit.
        - location_id (int): The ID of the location to assign to the items. Set to 0 to not assign any location.
        - specific_location (str): The specific location description to assign to the items. Set to None to not assign any specific location.

        Returns:
        (bool, str): A tuple containing a boolean indicating the success of the operation and a message describing the result.
        """
        if not item_ids or user is None:
            return False, "Item IDs cannot be None"

        if len(item_ids) == 0:
            return False, "No item IDs provided"

        if location_id is None:
            return False, "Location ID cannot be None"

        with app.app_context():
            stmt = select(Item).where(Item.user_id == user.id).where(Item.id.in_(item_ids))  # type: ignore
            results_ = db.session.execute(stmt).all()
            if results_ is None:
                return False, "No items found"

            for item_ in results_:
                if location_id != 0:
                    item_[0].location_id = location_id

                if specific_location is not None:
                    item_[0].specific_location = specific_location

            try:
                db.session.commit()
                return True, "Items updated successfully"
            except SQLAlchemyError:
                db.session.rollback()
                return False, "Could not update items"


    @staticmethod
    def get_item_by_id(item_id: int, user_id: Optional[int] = None) -> Optional[Item]:
        if item_id is None:
            return None
        try:
            if user_id is None:
                return db.session.get(Item, item_id)
            return db.session.query(Item).filter_by(id=item_id, user_id=user_id).one_or_none()
        except SQLAlchemyError as ex:
            app.logger.error(f"Error fetching item by id {item_id}: {ex}")
            db.session.rollback()
            return None

    @staticmethod
    def find_items_by_field_value(user_id: int, field_name: str, field_value: str):
        with app.app_context():
            field_id_ = FieldService.find_field_by_name(field_name=field_name)

            query = db.session.query(ItemField, Item).join(ItemField, ItemField.item_id == Item.id) \
                .filter(ItemField.field_id == field_id_.id) \
                .filter(ItemField.value == field_value) \
                .filter(Item.user_id == user_id)
            results_ = query.all()

            return results_

    @staticmethod
    def get_item_by_slug(item_slug: str, user_id: Optional[int] = None) -> Tuple[
        Optional[Item], Optional[ItemType], Optional[InventoryItem]]:
        if not item_slug:
            return None, None, None,
        try:
            # base select: Item + ItemType + InventoryItem; add UserInventory when user_id provided
            if user_id is None:
                stmt = select(Item, ItemType, InventoryItem).select_from(Item) \
                    .outerjoin(ItemType, ItemType.id == Item.item_type) \
                    .outerjoin(InventoryItem, InventoryItem.item_id == Item.id) \
                    .where(Item.slug == item_slug).limit(1)

                row = db.session.execute(stmt).first()
                if not row:
                    return None, None, None,

                item_obj, itemtype_obj, inventory_item_obj = row[0], row[1], row[2]
                return item_obj, itemtype_obj, inventory_item_obj

            else:
                stmt = select(Item, ItemType, InventoryItem).select_from(Item) \
                    .outerjoin(ItemType, ItemType.id == Item.item_type) \
                    .outerjoin(InventoryItem, InventoryItem.item_id == Item.id) \
 \
                    .where(Item.slug == item_slug).limit(1)

                row = db.session.execute(stmt).first()
                if not row:
                    return None, None, None

                item_obj, itemtype_obj, inventory_item_obj = row[0], row[1], row[2]
                return item_obj, itemtype_obj, inventory_item_obj

        except SQLAlchemyError as ex:
            app.logger.error(f"Error fetching item by slug {item_slug}: {ex}")
            db.session.rollback()
            return None, None, None

    @staticmethod
    def get_item_by_token(item_token: str, user_id: Optional[int] = None) -> Optional[Item]:
        if not item_token:
            return None
        try:
            q = db.session.query(Item).filter_by(item_token=item_token)
            if user_id is not None:
                q = q.filter_by(user_id=user_id)
            return q.one_or_none()
        except SQLAlchemyError as ex:
            app.logger.error(f"Error fetching item by item_token {item_token}: {ex}")
            db.session.rollback()
            return None

    def relate_items(self, user_id: int, item_a_id: int, item_b_id: int) -> None:
        """
        Create a bidirectional relation between item_a and item_b.
        If Relateditems table has a `user_id` column, the user_id will be stored.
        Raises ValueError if items not found, IntegrityError on conflict.
        """
        # ensure items exist (will raise ValueError via get())
        self.get(item_a_id)
        self.get(item_b_id)

        cols = Relateditems.__table__.c
        base_a = {'item_id': item_a_id, 'related_item_id': item_b_id}
        base_b = {'item_id': item_b_id, 'related_item_id': item_a_id}
        if 'user_id' in cols:
            base_a['user_id'] = user_id
            base_b['user_id'] = user_id

        # if a relation already exists in either direction (and scoped by user if applicable), return early
        cond_a = (Relateditems.item_id == item_a_id) & (Relateditems.related_item_id == item_b_id)
        cond_b = (Relateditems.item_id == item_b_id) & (Relateditems.related_item_id == item_a_id)
        if 'user_id' in cols:
            cond_a = cond_a & (Relateditems.user_id == user_id)
            cond_b = cond_b & (Relateditems.user_id == user_id)

        existing = db.session.query(Relateditems).filter(cond_a | cond_b).first()
        if existing:
            return

        try:
            # insert both directions
            db.session.execute(Relateditems.__table__.insert().values(base_a))
            db.session.execute(Relateditems.__table__.insert().values(base_b))
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            raise

    def unrelate_items(self, user_id: int, item_a_id: int, item_b_id: int) -> None:
        """
        Remove bidirectional relation between item_a and item_b.
        If Relateditems table has `user_id`, the deletion will be scoped to that user.
        Raises ValueError if no relation rows were removed.
        """
        cols = Relateditems.__table__.c
        where_a = (cols.item_id == item_a_id) & (cols.related_item_id == item_b_id)
        where_b = (cols.item_id == item_b_id) & (cols.related_item_id == item_a_id)
        if 'user_id' in cols:
            where_a = where_a & (cols.user_id == user_id)
            where_b = where_b & (cols.user_id == user_id)

        try:
            res1 = db.session.execute(Relateditems.__table__.delete().where(where_a))
            res2 = db.session.execute(Relateditems.__table__.delete().where(where_b))
            affected = (getattr(res1, "rowcount", 0) or 0) + (getattr(res2, "rowcount", 0) or 0)
            if affected == 0:
                db.session.rollback()
                raise ValueError("no relation found to remove")
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            raise

    @staticmethod
    def add_new_item_field(item: Item, custom_fields: dict, user_id: int, app_context=None):
        """
        Add or update custom fields for an Item.

        Returns (success: bool, message: str).
        """
        if custom_fields is None:
            custom_fields = {}

        if item is None:
            app.logger.error("No item provided")
            return False, "No item provided"

        if user_id is None:
            return False, "No user ID provided"

        if app_context is None:
            app_context = app.app_context()

        with app_context:
            try:
                for field_name, field_value in custom_fields.items():
                    if not field_name:
                        continue

                    # safe slugify
                    try:
                        field_slug = slugify(field_name)
                    except Exception:
                        field_slug = str(field_name).lower().replace(" ", "-")

                    # prefer user-specific field, fallback to system/global (user_id IS NULL)
                    q = db.session.query(Field).filter(Field.slug == field_slug)
                    q = q.filter(or_(Field.user_id == user_id, Field.user_id.is_(None)))
                    field_ = q.order_by(Field.user_id.desc()).first()  # prefer user-specific

                    if field_ is None:
                        field_ = Field(field=field_name, slug=field_slug, user_id=user_id)
                        db.session.add(field_)
                        db.session.flush()  # ensure field_.id available

                    # ensure association between field and item
                    if item not in field_.items:
                        field_.items.append(item)

                    # find or create ItemField record
                    item_field_ = db.session.query(ItemField).filter_by(field_id=field_.id,
                                                                        item_id=item.id).one_or_none()
                    if item_field_ is None:
                        item_field_ = ItemField(field_id=field_.id, item_id=item.id)
                        db.session.add(item_field_)

                    # set values
                    item_field_.value = field_value
                    item_field_.show = True
                    item_field_.user_id = user_id

                db.session.commit()
                return True, "fields updated"
            except IntegrityError as e:
                app.logger.exception(f"add_new_item_field integrity error: {e}")
                try:
                    db.session.rollback()
                except Exception:
                    pass
                return False, "database integrity error"
            except SQLAlchemyError as e:
                app.logger.exception(f"add_new_item_field db error: {e}")
                try:
                    db.session.rollback()
                except Exception:
                    pass
                return False, "database error"
            except Exception as e:
                app.logger.exception(f"add_new_item_field unexpected error: {e}")
                try:
                    db.session.rollback()
                except Exception:
                    pass
                return False, "unexpected error"
