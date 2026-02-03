import os
import uuid
from datetime import datetime
from secrets import token_urlsafe
from typing import Dict, Any, List, Optional, Union, Tuple

import flask_bcrypt
from slugify import slugify
from sqlalchemy import select, or_, ClauseElement, func, and_
from sqlalchemy.exc import IntegrityError, SQLAlchemyError, NoResultFound, InvalidRequestError
from app import db, app

from models import UserInventory, Relateditems, Inventory, User, Item, Location, ItemType, FieldTemplate, \
    TemplateField, Field, Tag, InventoryItem, ItemField

from site_globals import __DEFAULT__, __NONE__, __PRIVATE__, __INVENTORY__, __PUBLIC__, __none__, __OWNER__


def _to_dict(object_: db.Model) -> dict:
    if isinstance(object_, dict):
        return object_
    _dict = object_.__dict__
    _dict.pop('_sa_instance_state', None)
    return _dict


def _commit() -> Tuple[bool, str]:
    try:
        db.session.commit()
        return True, "success"
    except Exception as error:  # noqa
        app.logger.error(f"Could not commit changes: {str(error)}")
        db.session.rollback()
        return False, "Could not edit list"


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


def get_or_create(model, defaults=None, **kwargs):
    with app.app_context():
        instance = db.session.query(model).filter_by(**kwargs).first()
        if instance:
            return instance, True
        else:
            params = {k: v for k, v in kwargs.items() if not isinstance(v, ClauseElement)}
            params.update(defaults or {})
            instance = model(**params)
            try:
                db.session.add(instance)
                db.session.commit()

            except Exception as e:
                print(e)
                db.session.rollback()
                instance = db.session.query(model).filter_by(**kwargs).one()
                return instance, False
            else:
                return instance, True


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
        _ret = InventoryService.add_user_list(name=f"{__DEFAULT__}_{new_user.username}",
                                              description=f"Default inventory for {new_user.username}",
                                              access_level=0,
                                              inventory_type=1,
                                              user_id=new_user.id)
        LocationService.get_or_add_new_location(location_name=f"{__DEFAULT__}_{new_user.username}",
                                                location_description=f"Default location for {new_user.username}",
                                                to_user_id=new_user.id)
        # add_new_user_itemtype(name=_NONE_, user_id=new_user.id)

        # create folder for user uploads
        user_upload_folder = os.path.join(app.config['USER_IMAGES_BASE_PATH'], str(new_user.id))
        if not os.path.exists(user_upload_folder):
            os.makedirs(user_upload_folder)

    # add default locations, types


class UserService:

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


class ItemService:

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
    def get_item_custom_field_data(user_id: int, item_list=None):
        with app.app_context():
            item_field_data_ = db.session.query(Item.id, Field.field, ItemField.value, Field.slug) \
                .join(ItemField, ItemField.field_id == Field.id) \
                .join(Item, ItemField.item_id == Item.id) \
                .filter(Item.user_id == user_id) \
                .filter(ItemField.show == True)

            if item_list is not None:
                if isinstance(item_list, list):
                    item_field_data_ = item_field_data_.filter(Item.id.in_(item_list))

            item_field_data_ = item_field_data_.all()

            slugs = []
            sdsd = {}
            sdsd2 = {}
            for row in item_field_data_:
                _t = {"name": row[1], "value": row[2], "slug": row[3]}
                if row[0] in sdsd:
                    sdsd[row[0]][row[1]] = row[2]
                    sdsd2[row[0]].append(_t)
                else:
                    sdsd[row[0]] = {row[1]: row[2]}
                    sdsd2[row[0]] = [_t]

                if row[3] not in slugs:
                    slugs.append(row[3])

            return sdsd, slugs, sdsd2

    @staticmethod
    def find_items_new(logged_in_user=None, requested_username=None, inventory_id=None, query_params=None):

        def _find_my_items(logged_in_user: User, inventory_id, query_params):
            with app.app_context():
                if inventory_id is not None and inventory_id != '':
                    # query = db.session.query(Item, ItemType.name, Location.name, InventoryItem.access_level,
                    #                         InventoryItem.is_link, UserInventory) \
                    query = db.session.query(Item, ItemType.name, Location.name, InventoryItem.access_level,
                                             InventoryItem.is_link, UserInventory) \
                        .join(ItemType, ItemType.id == Item.item_type) \
                        .join(Location, or_(Location.id == Item.location_id, Item.location_id == None))

                    query = query.join(InventoryItem, InventoryItem.item_id == Item.id)
                    query = query.join(Inventory, Inventory.id == InventoryItem.inventory_id)
                    query = query.filter(InventoryItem.inventory_id == inventory_id)

                    query = query.filter(UserInventory.inventory_id == inventory_id)
                    query = query.filter(UserInventory.user_id == logged_in_user.id)
                else:
                    query = db.session.query(Item, ItemType.name, Location.name, InventoryItem.access_level,
                                             InventoryItem.is_link) \
                        .join(ItemType, ItemType.id == Item.item_type) \
                        .join(Location, Location.id == Item.location_id)

                    query = query.join(InventoryItem, InventoryItem.item_id == Item.id)

                query = query.filter(Item.user_id == logged_in_user.id)

                query = _find_query_parameters(query_=query, query_params=query_params)

                query = _pagination_query(query_params, query)

                results_ = query.all()

                return results_

        def _find_query_parameters(query_, query_params):
            item_type = query_params.get('item_type', None)
            item_location = query_params.get('item_location', None)
            item_specific_location = query_params.get('item_specific_location', None)
            item_tags = query_params.get('item_tags', None)

            if item_type is not None and item_type != '':
                query_ = query_.filter(Item.item_type == item_type)

            if item_location is not None and item_location != '':
                query_ = query_.filter(Location.id == item_location)

            if item_specific_location is not None and item_specific_location != '':
                query_ = query_.filter(Item.specific_location == item_specific_location)

            if item_tags is not None and item_tags != "":
                item_tags = item_tags.split(",")

                for tag_ in item_tags:
                    tag_ = tag_.strip()
                    # tag_ = tag_.replace(" ", "@#$")
                    t_ = TagService.get_tag_by_str(tag_str=tag_)

                    if t_ is not None:
                        query_ = query_.filter(Item.tags.contains(t_))

            return query_

        def _pagination_query(query_params, query):
            search = query_params.get("search", None)

            if search is not None:
                if search != "":
                    query = query.filter(Item.name.contains(search))

            start = query_params.get("start", 0)
            length = query_params.get("length", 50)

            order_0 = query_params.get("order_0", None)
            dir_0 = query_params.get("dir_0", None)

            if order_0 is not None and dir_0 is not None:
                if order_0 == '0':
                    if dir_0 == 'asc':
                        query = query.order_by(Item.name.asc())
                    else:
                        query = query.order_by(Item.name.desc())
                elif order_0 == '1':
                    if dir_0 == 'asc':
                        query = query.order_by(ItemType.name.asc())
                    else:
                        query = query.order_by(ItemType.name.desc())
                elif order_0 == '2':
                    if dir_0 == 'asc':
                        query = query.order_by(Location.name.asc())
                    else:
                        query = query.order_by(Location.name.desc())

            page = int((int(start) / int(length)))
            # page = query_params.get("page", 1)
            per_page = int(query_params.get("length", 50))

            if length is not None:
                query = query.limit(per_page)
            if page is not None:
                query = query.offset(page * per_page)

            return query

        def _find_someone_elses_items_loggedin(logged_in_user: User, request_user_id, inventory_id, query_params):
            with app.app_context():
                query = db.session.query(Item, ItemType.name, Location.name, InventoryItem.access_level,
                                         InventoryItem.is_link) \
                    .join(ItemType, ItemType.id == Item.item_type) \
                    .join(Location, Location.id == Item.location_id)

                query = query.join(InventoryItem, InventoryItem.item_id == Item.id)
                query = query.join(Inventory, Inventory.id == InventoryItem.inventory_id)
                query = query.filter(InventoryItem.inventory_id == inventory_id)

                query = query.filter(and_(
                    UserInventory.user_id == logged_in_user.id,
                    UserInventory.inventory_id == inventory_id))

                query = query.filter(Item.user_id == request_user_id)
                # query = query.filter(InventoryItem.access_level == 2)

                query = _find_query_parameters(query_=query, query_params=query_params)
                query = _pagination_query(query_params, query)

                results_ = query.all()

                return results_

        def _find_someone_elses_items_notloggedin(request_user_id, inventory_id, query_params):
            with app.app_context():
                query = db.session.query(Item, ItemType.name, Location.name, InventoryItem.access_level,
                                         InventoryItem.is_link) \
                    .join(ItemType, ItemType.id == Item.item_type) \
                    .join(Location, Location.id == Item.location_id)

                query = query.join(InventoryItem, InventoryItem.item_id == Item.id)
                query = query.join(Inventory, Inventory.id == InventoryItem.inventory_id)
                query = query.filter(InventoryItem.inventory_id == inventory_id)

                query = query.filter(and_(
                    # UserInventory.user_id == logged_in_user.id,
                    UserInventory.inventory_id == inventory_id))

                query = query.filter(Item.user_id == request_user_id)
                # query = query.filter(InventoryItem.access_level == 2)

                query = _find_query_parameters(query_=query, query_params=query_params)

                results_ = query.all()

                return results_

        if query_params is None:
            query_params = {}

        logged_in_user_id = None
        request_user_id = None
        requested_user = None

        if logged_in_user is not None:
            logged_in_user_id = logged_in_user.id

        if requested_username is None:
            request_user_id = None
        else:
            if logged_in_user is not None:
                if requested_username == logged_in_user.username:
                    requested_user = logged_in_user
                else:
                    requested_user = UserService.get_user_by_username(username=requested_username)
            else:
                requested_user = UserService.get_user_by_username(username=requested_username)

            if requested_user is not None:
                request_user_id = requested_user.id

        if logged_in_user is None and requested_user is None:
            return {}

        if logged_in_user is not None and requested_user is None:
            return _find_my_items(logged_in_user=logged_in_user, inventory_id=inventory_id, query_params=query_params)

        if logged_in_user is not None and logged_in_user_id == request_user_id:
            return _find_my_items(logged_in_user=logged_in_user, inventory_id=inventory_id, query_params=query_params)

        if logged_in_user is not None:
            # if logged_in_user is not None:
            return _find_someone_elses_items_loggedin(request_user_id=request_user_id, inventory_id=inventory_id,
                                                      query_params=query_params, logged_in_user=logged_in_user)
        else:
            return _find_someone_elses_items_notloggedin(request_user_id=request_user_id, inventory_id=inventory_id,
                                                         query_params=query_params)

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


class SearchService:

    @staticmethod
    def search_items(query: str, user_id: int):

        def _search_by_field_value(field_id: int, user_id: int, query: str):
            looking_for = '%{0}%'.format(query)
            with app.app_context():
                items_ = db.session.query(Item) \
                    .join(ItemField, ItemField.item_id == Item.id) \
                    .filter(ItemField.field_id == field_id) \
                    .filter(ItemField.user_id == user_id) \
                    .filter(ItemField.value.ilike(looking_for)).all()

                return items_

        items_arr = []
        with app.app_context():

            # see if there is a search modifier
            if ':' in query:
                search_modifier = query.split(':')[0]
                query = query.split(':')[1].strip()

                if search_modifier.lower() == 'location':
                    locations_ = Location.query \
                        .filter(Location.user_id == user_id) \
                        .filter(Location.name.ilike(query)).all()

                    for location in locations_:
                        loc_id_ = location.id
                        items_ = Item.query.filter(or_(
                            Item.location_id == loc_id_,
                            Item.specific_location == query
                        )
                        ).all()

                        if len(items_) > 0:
                            for item in items_:
                                items_arr.append(item.__dict__)

                    looking_for = '%{0}%'.format(query)
                    items_ = Item.query.filter(
                        Item.specific_location.ilike(looking_for)
                    ).all()

                    if len(items_) > 0:
                        for item in items_:
                            items_arr.append(item.__dict__)

                elif search_modifier.lower() == 'tags' or search_modifier.lower() == 'tag':
                    query = query.split(",")
                    q_ = Item.query

                    any_tags_found = False
                    for tag_ in query:
                        tag_ = tag_.strip()
                        tag_ = tag_.replace(" ", "@#$")
                        t_ = TagService.get_tag_by_str(tag_str=tag_)

                        if t_ is not None:
                            any_tags_found = True
                            q_ = q_.filter(Item.tags.contains(t_))

                    if any_tags_found:
                        items_ = q_.all()

                        if len(items_) > 0:
                            for item in items_:
                                items_arr.append(item.__dict__)

                elif search_modifier.lower() == 'type':
                    query = query.split(",")

                    types_ = ItemType.query \
                        .filter(ItemType.user_id == user_id) \
                        .filter(ItemType.name.like(query)).all()

                    type_ids = []
                    for type_ in types_:
                        type_ids.append(type_.id)

                    items_ = Item.query.filter(Item.user_id == user_id).filter(Item.item_type.in_([type_ids])).all()

                    if len(items_) > 0:
                        for item in items_:
                            items_arr.append(item.__dict__)

                else:  # we have a custom field
                    field_ = FieldService.find_field_by_name(field_name=search_modifier)
                    if field_ is not None:
                        field_id = field_.id
                        items_ = _search_by_field_value(field_id=field_id, user_id=user_id, query=query)

                        if len(items_) > 0:
                            for item in items_:
                                items_arr.append(item.__dict__)

            else:
                # search simple string
                looking_for = '%{0}%'.format(query)

                items_ = Item.query.filter(or_(
                    Item.name.ilike(looking_for),
                    Item.description.ilike(looking_for)
                )
                ).all()

                if len(items_) > 0:
                    for item in items_:
                        items_arr.append(item.__dict__)

            return items_arr

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


class FieldTemplateService:

    @staticmethod
    def find_template_by_id(template_id: int) -> Optional[FieldTemplate]:
        """
        Args:
            template_id: The ID of the template to be found.

        Returns:
            An instance of FieldTemplate if a template with the specified ID is found, otherwise returns None.
        """
        if template_id is not None:
            field_template_ = FieldTemplate.query.filter_by(id=template_id).one_or_none()
            return field_template_
        else:
            return None

    @staticmethod
    def delete_all_user_field_templates(user_id: int) -> int:
        """
        Deletes all field templates associated with a user.

        Args:
            user_id (int): The ID of the user whose field templates are to be deleted.

        Returns:
            int: The number of field templates deleted.
        """
        if user_id is None:
            return 0

        with app.app_context():
            templates_to_delete = FieldTemplate.query.filter_by(user_id=user_id).all()
            number_templates_deleted = 0

            for template in templates_to_delete:
                db.session.delete(template)
                number_templates_deleted += 1

            status, msg = _commit()
            if not status:
                app.logger.error(f"Could not delete user field templates: {msg}")
                return 0

            return number_templates_deleted

    @staticmethod
    def save_inventory_fieldtemplate(inventory_id: int, inventory_template: int, user_id: int) -> Tuple[bool, str]:
        """
        Args:
            inventory_id: An integer representing the ID of the inventory.
            inventory_template: An integer representing the ID of the field template.
            user_id: An integer representing the ID of the user.

        Returns:
            A tuple containing a boolean value indicating the success of the operation and a string message indicating the result of the operation.
        """
        with app.app_context():
            inventory_, user_inventory_ = InventoryService.find_inventory_by_id(inventory_id=inventory_id,
                                                                                user_id=user_id)
            inventory_ = db.session.merge(inventory_)
            if inventory_ is None or user_inventory_ is None:
                app.logger.error(f"System failed to find inventory with ID: {inventory_id}")
                return False, "Failed to find inventory"

            if user_inventory_.access_level == 0:
                inventory_.field_template = inventory_template

                template_ = db.session.query(FieldTemplate).filter(FieldTemplate.id == inventory_template).one_or_none()
                if template_ is not None:
                    template_ = db.session.merge(template_)
                    temp_fields = template_.fields
                    field_ids = [x.id for x in temp_fields]

                    items_ = inventory_.items

                    for item in items_:
                        FieldService.set_field_status(item_id=item.id, field_ids=field_ids)
                else:
                    app.logger.error(f"Failed to find template with ID: {inventory_template}")
                    return False, "Failed to find template"

            try:
                db.session.commit()
            except Exception as e:
                app.logger.error(f"Failed to save inventory field template: {str(e)}")
                db.session.rollback()
                return False, "Failed to save inventory field template"

        return True, ""

    @staticmethod
    def add_new_template(name: str, fields: str, to_user: User) -> Optional[FieldTemplate]:
        with app.app_context():
            try:
                template_ = FieldTemplate(name=name, fields=fields, user_id=to_user.id)
                db.session.add(template_)
                db.session.commit()
                db.session.flush()
                db.session.expire_all()
                return template_
            except Exception as e:
                print(e)

    @staticmethod
    def save_template_fields(template_name: str, fields: list[int], user_id: int) -> Tuple[bool, str, Optional[int]]:
        field_type = 1
        if len(fields) > 0:
            if isinstance(fields[0], int):
                field_type = 1
            else:
                field_type = 2

        if template_name is None:
            return False, "Template name cannot be None", None

        with app.app_context():

            field_template_ = FieldTemplate.query.filter_by(name=template_name).filter_by(user_id=user_id).one_or_none()

            if field_template_ is None:
                field_template_ = FieldTemplate(name=template_name, user_id=user_id)
                db.session.add(field_template_)

                for field in fields:
                    if field_type == 1:
                        field_ = Field.query.filter_by(id=field).one_or_none()
                    else:
                        field_ = Field.query.filter_by(slug=field).one_or_none()
                    if field_ is not None:
                        field_template_.fields.append(field_)

            else:
                field_template_.name = template_name

                field_template_.fields = []
                for field in fields:
                    if field_type == 1:
                        field_ = Field.query.filter_by(id=field).one_or_none()
                    else:
                        field_ = Field.query.filter_by(slug=field).one_or_none()
                    if field_ is not None:
                        field_template_.fields.append(field_)

                db.session.commit()

                inventories_ = Inventory.query.filter_by(field_template=field_template_.id).all()
                if inventories_ is not None:
                    for inventory in inventories_:
                        FieldTemplateService.save_inventory_fieldtemplate(inventory_id=inventory.id,
                                                                          inventory_template=field_template_.id,
                                                                          user_id=user_id)

            db.session.commit()

            # now do the sorting
            stmt = select(TemplateField).where(FieldTemplate.id == field_template_.id)  # type: ignore
            r = db.session.execute(stmt).all()

            max_order = db.session.query(func.max(TemplateField.order)).scalar()

            for row in r:
                if row[0].order == 0:
                    max_order += 1
                    row[0].order = max_order

            db.session.commit()

            return True, "success", field_template_.id

    @staticmethod
    def update_template_by_id(template_data: dict, user: User) -> Tuple[bool, str, Optional[int]]:
        """
        Update a template by its ID.

        Parameters:
        - template_data (dict): A dictionary containing the updated template data. It should have the following keys:
            - 'id' (int): The ID of the template to be updated.
            - 'name' (str): The new name for the template.
            - 'fields' (list): A list of fields for the template.

        - user (User): The user object of the user making the request.

        Returns:
        - Tuple (bool, str): A tuple containing a boolean value indicating whether the update operation was successful, and a string message providing information about the outcome. If the update
        * is successful, the boolean value will be True and the message will be "Template updated successfully". Otherwise, the boolean value will be False and the message will indicate the
        * reason for failure, such as "Invalid user", "Template data must be a dictionary", "Template ID must be provided", "Template name must be provided", "Template fields must be provided
        *", "Template fields must be a list", "No template with id {template_id} found for user {user.username}", or "Could not update template".
        """
        if user is None or not isinstance(user, User):
            return False, "Invalid user"

        if not isinstance(template_data, dict):
            return False, "Template data must be a dictionary"

        if 'id' not in template_data:
            return False, "Template ID must be provided"

        if 'name' not in template_data:
            return False, "Template name must be provided"

        if 'fields' not in template_data:
            return False, "Template fields must be provided"

        if not isinstance(template_data['fields'], list):
            return False, "Template fields must be a list"

        return FieldTemplateService.save_template_fields(template_name=template_data['name'],
                                                         fields=template_data['fields'], user_id=user.id)

    @staticmethod
    def get_user_templates(user_id: int):
        """
        Retrieve the templates associated with a given user.

        :param user_id: The user id for which templates are to be retrieved.

        :return: A list of templates associated with the user.
        :rtype: list
        """
        with app.app_context():
            stmt = select(FieldTemplate).join(User).where(User.id == user_id)
            r = db.session.execute(stmt).all()
            return r

    @staticmethod
    def add_field(self, template_id: int, field_id: int, order: Optional[int] = None) -> TemplateField:
        """
        Add a field to a field template. If order is None the field is appended
        after the current highest order. Returns the created TemplateField record.
        """
        ft = self.get(template_id)

        if order is None:
            max_rec = db.session.query(TemplateField).filter(
                TemplateField.template_id == template_id
            ).order_by(TemplateField.order.desc()).first()
            order = (max_rec.order + 1) if (max_rec and max_rec.order is not None) else 0

        rec = TemplateField(field_id=field_id, template_id=template_id, order=order)
        db.session.add(rec)
        try:
            db.session.commit()
            return rec
        except IntegrityError:
            db.session.rollback()
            # concurrent insert may have created the same mapping; try to return it
            existing = db.session.query(TemplateField).filter_by(
                field_id=field_id, template_id=template_id
            ).first()
            if existing:
                return existing
            raise


class InventoryService:

    @staticmethod
    def get_all_item_ids_in_inventory(user_id: int, inventory_id: int) -> list[int]:
        """
        Return a list of item ids for the given user and inventory.

        - Validates inputs.
        - Uses .scalars() to get a flat list of ids.
        - Logs exceptions with traceback and performs a rollback on error.
        """
        if not isinstance(user_id, int) or not isinstance(inventory_id, int):
            app.logger.error("get_all_item_ids_in_inventory: user_id and inventory_id must be integers")
            return []

        with app.app_context():
            try:
                stmt = select(Item.id).join(
                    InventoryItem, InventoryItem.item_id == Item.id
                ).where(
                    Item.user_id == user_id,
                    InventoryItem.inventory_id == inventory_id
                ).distinct()
                results = db.session.execute(stmt).scalars().all()
                return [int(x) for x in results]
            except SQLAlchemyError as e:
                app.logger.exception(f"Error finding all item ids in inventory: {e}")
                try:
                    db.session.rollback()
                except Exception:
                    pass
                return []

    @staticmethod
    def get_user_public_lists(for_user_id: int) -> list:
        if for_user_id is None:
            return []

        try:
            with app.app_context():
                inventories = db.session.query(Inventory).filter(
                    Inventory.owner_id == for_user_id,
                    Inventory.access_level == __PUBLIC__
                ).all()

                ret_results: list = []
                for inv in inventories:
                    # Prefer counting items via relationship, fall back to a safe 0
                    try:
                        item_count = len(inv.items) if getattr(inv, "items", None) is not None else 0
                    except Exception:
                        # defensive fallback if relationship access fails
                        try:
                            item_count = db.session.query(func.count(InventoryItem.id)).filter(
                                InventoryItem.inventory_id == inv.id
                            ).scalar() or 0
                        except Exception:
                            item_count = 0

                    d = {
                        "inventory_id": inv.id,
                        "inventory_name": inv.name,
                        "inventory_description": inv.description,
                        "inventory_slug": inv.slug,
                        "inventory_access_level": inv.access_level,
                        "inventory_item_count": int(item_count),
                        "inventory_type": inv.type,
                        "userinventory_access_level": __PRIVATE__
                    }
                    ret_results.append(d)

                return ret_results
        except SQLAlchemyError as e:
            app.logger.exception(f"get_user_public_lists DB error: {e}")
            try:
                db.session.rollback()
            except Exception:
                pass
            return []
        except Exception as e:
            app.logger.exception(f"get_user_public_lists unexpected error: {e}")
            return []

    @staticmethod
    def get_number_user_lists(user_id: int) -> int:
        with app.app_context():
            _inv_count = UserInventory.query.filter_by(user_id=user_id).count()
            return _inv_count

    @staticmethod
    def get_user_default_inventory_id(user_id: int) -> int:
        with app.app_context():
            di_ = InventoryService.get_user_default_inventory(user_id=user_id)
            if di_ is not None:
                return di_.id
            else:
                return -1

    @staticmethod
    def find_all_user_inventories(user_id: int) -> list:
        if user_id is None:
            raise ValueError("User cannot be None")

        try:
            select_query = select(UserInventory, Inventory) \
                .join(Inventory) \
                .join(User) \
                .where(user_id == UserInventory.user_id)
            result = db.session.execute(select_query).all()
            return result
        except Exception as ex:
            app.logger.error(f"Error finding all user inventories: {str(ex)}")
            return []

    @staticmethod
    def delete_all_user_lists(user_id: int):
        _user_inventories, status, msg = InventoryService.get_user_inventories(current_user_id=user_id,
                                                                               requesting_user_id=user_id)

        list_ids_ = []
        for list_ in _user_inventories:
            if __DEFAULT__ not in list_["inventory_name"]:
                list_ids_.append(list_["inventory_id"])

        InventoryService.delete_lists_by_id(inventory_ids=list_ids_, user_id=user_id)

    @staticmethod
    def delete_lists_by_id(inventory_ids: Union[int, List[int]], user_id: int) -> Tuple[bool, str]:
        """
        If the User has Items within the Inventory - re-link Items to Users default Inventory via the ItemInventory table
        Delete the UserInventory for the user
        If there are no more UserInventory links to the Inventory - delete the Inventory
        """

        if not isinstance(inventory_ids, list):
            inventory_ids = [inventory_ids]

        with app.app_context():

            stmt = select(UserInventory).join(User) \
                .where(UserInventory.user_id == user_id) \
                .where(UserInventory.inventory_id.in_(inventory_ids))
            user_inventories_ = db.session.execute(stmt).all()

            for user_inventory_ in user_inventories_:  # type: UserInventory

                if user_inventory_ is not None:
                    user_inventory_ = user_inventory_[0]

                    """ If not inventory owner, just delete the UserInventory entry """
                    if user_inventory_.access_level != __OWNER__:
                        db.session.delete(user_inventory_)
                        try:
                            db.session.commit()
                            return True, ""
                        except SQLAlchemyError as error:
                            app.logger.error(f"Error deleting user inventory entry: {str(error)}")
                            return False, f"Error deleting user inventory entry: {str(error)}"

                    # Find out if any other users point to this inventory, if not delete it
                    inventory_id_to_delete = user_inventory_.inventory_id

                    # Get the current user's default inventory
                    user_default_inventory_ = InventoryService.get_user_default_inventory(user_id=user_id)

                    inv_items_ = InventoryItem.query.filter_by(inventory_id=inventory_id_to_delete).all()
                    for row in inv_items_:
                        # Add the items that are in this inventory to the user's default
                        row.inventory_id = user_default_inventory_.id

                    # Delete the UserInventory for the user
                    db.session.delete(user_inventory_)
                    try:
                        db.session.commit()
                    except SQLAlchemyError as error:
                        app.logger.error(f"Error deleting user inventory entry: {str(error)}")
                        return False, f"Error deleting user inventory entry: {str(error)}"

                    users_invs_ = UserInventory.query.filter_by(inventory_id=inventory_id_to_delete).all()
                    if len(users_invs_) == 0:
                        # remove the actual inventory
                        inv_ = Inventory.query.filter_by(id=inventory_id_to_delete).first()
                        if inv_ is not None:
                            db.session.delete(inv_)
                            try:
                                db.session.commit()

                            except SQLAlchemyError as error:
                                app.logger.error(f"Error deleting inventory: {str(error)}")
                                return False, f"Error deleting inventory: {str(error)}"

            return True, ""

    @staticmethod
    def get_or_create(self, data: Dict[str, Any]) -> Inventory:
        # avoid mutating caller's dict
        data = dict(data)
        users = data.pop("user_ids", None)
        items = data.pop("item_ids", None)

        q = db.session.query(Inventory).filter(Inventory.name == data["name"])
        if data.get("owner_id") is not None:
            q = q.filter(Inventory.owner_id == data["owner_id"])
        existing = q.first()
        if existing:
            return existing

        inv = Inventory(**data)
        db.session.add(inv)
        try:
            db.session.flush()
            if users:
                for uid in users:
                    db.session.execute(UserInventory.__table__.insert().values(user_id=uid, inventory_id=inv.id))
            if items:
                for iid in items:
                    db.session.execute("INSERT INTO inventory_items (inventory_id, item_id) VALUES (:inv, :it)",
                                       {"inv": inv.id, "it": iid})
            db.session.commit()
            return inv
        except IntegrityError:
            db.session.rollback()

            # concurrent insert may have won; try to find existing by name (+ owner)
            if data.get("name"):
                q = db.session.query(Inventory).filter(Inventory.name == data["name"])
                if data.get("owner_id") is not None:
                    q = q.filter(Inventory.owner_id == data["owner_id"])
                existing = q.first()
                if existing:
                    return existing
            raise

    @staticmethod
    def get_user_inventories(current_user_id: int, requesting_user_id: int, access_level: int = -1) -> Tuple[
        list, bool, str]:
        """
        Gets the inventories associated with a user.

        Parameters:
        - current_user_id (int): The ID of the current user. If None, all inventories associated with
          the requesting user will be returned.
        - requesting_user_id (int): The ID of the user requesting the inventories.
        - access_level (int, optional): The access level of the inventories to filter by. If -1, no
          filtering will be applied based on access level. Default is -1.

        Returns:
        - List[dict]: A list of dictionaries representing the inventories. Each dictionary contains
          the following keys:
            - inventory_id (int): The ID of the inventory.
            - inventory_name (str): The name of the inventory.
            - inventory_description (str): The description of the inventory.
            - inventory_slug (str): The slug of the inventory.
            - inventory_access_level (int): The access level of the inventory.
            - inventory_owner (str): The username of the inventory's owner.
            - inventory_item_count (int): The number of items in the inventory.
            - userinventory_access_level (int): The access level of the user for the inventory.
        """

        if not isinstance(access_level, int):
            return [], False, "access_level must be an integer"

        if not isinstance(current_user_id, int) and current_user_id is not None:
            return [], False, "current_user_id must be an integer"

        if not isinstance(requesting_user_id, int) and requesting_user_id is not None:
            return [], False, "requesting_user_id must be an integer"

        with ((app.app_context())):

            # stmt = db.session.query(Inventory, UserInventory).join(UserInventory).filter(UserInventory.user_id==1).all()
            stmt = db.session.query(Inventory, UserInventory, User
                                    ).join(UserInventory, UserInventory.inventory_id == Inventory.id
                                           ).join(User, User.id == Inventory.owner_id)

            if current_user_id is not None and requesting_user_id is not None:
                is_current_user = (current_user_id == requesting_user_id)
            else:
                if requesting_user_id is None:
                    return [], True, ""
                is_current_user = False

            if is_current_user:
                if access_level == -1:
                    stmt = stmt.filter(UserInventory.user_id == current_user_id)
                else:
                    stmt = stmt.filter(UserInventory.user_id == current_user_id) \
                        .filter(UserInventory.access_level == access_level)
            else:
                # stmt = stmt.filter(UserInventory.user_id == requesting_user_id).filter(UserInventory.access_level != 0)
                stmt = db.session.query(Inventory, UserInventory
                                        ).join(UserInventory, UserInventory.inventory_id == Inventory.id
                                               ).filter(Inventory.owner_id == requesting_user_id
                                                        ).filter(Inventory.access_level == 1)

            r = db.session.execute(stmt).all()

            ret_results = []

            for inv, user_inv, owner in r:
                d = {
                    "inventory_id": inv.id,
                    "inventory_name": inv.name,
                    "inventory_description": inv.description,
                    "inventory_slug": inv.slug,
                    "inventory_access_level": inv.access_level,
                    "inventory_owner": owner.username,
                    "inventory_item_count": len(inv.items),
                    "inventory_type": inv.type,
                    "inventory_show_default_fields": 1 if inv.show_default_fields else 0,

                    "inventory_show_item_images": 1 if inv.show_item_images else 0,
                    "inventory_show_item_type": 1 if inv.show_item_type else 0,
                    "inventory_show_item_url": 1 if inv.show_item_url else 0,
                    "inventory_show_item_location": 1 if inv.show_item_location else 0,
                    "inventory_show_item_tags": 1 if inv.show_item_tags else 0,
                    "userinventory_access_level": user_inv.access_level
                }
                ret_results.append(d)

            return ret_results, True, ""

    @staticmethod
    def get_user_default_inventory(user_id: int) -> Optional[Inventory]:
        def _get_user_default_inventory_name(username: str) -> str:
            from site_globals import __DEFAULT__
            return f"{__DEFAULT__}_{username}"

        with app.app_context():
            # Find user default inventory
            user_ = UserService.get_user_by_id(user_id=user_id)
            user_default_inventory_ = Inventory.query.filter_by(
                name=_get_user_default_inventory_name(user_.username)).filter_by().first()
            return user_default_inventory_

    @staticmethod
    def _create_list(name: str,
                     description: str,
                     slug: str,
                     inventory_type: int = __INVENTORY__,
                     show_default_fields: int = 1,
                     show_item_images: int = 1,
                     show_item_type: int = 1,
                     show_item_location: int = 1,
                     show_item_tags: int = 1,
                     show_item_url: int = 1,
                     to_user: User = None,
                     access_level: int = __PRIVATE__, token=None):
        """
        Create a new inventory.

        Parameters:
        - name (str): The name of the inventory.
        - description (str): The description of the inventory.
        - slug (str): The slug of the inventory.
        - to_user (User): The user to whom the inventory belongs.
        - access_level (int): The access level of the inventory.

        Returns:
        - Inventory: The newly created inventory.

        """
        with app.app_context():
            to_user = db.session.merge(to_user)

            inventory_token = uuid.uuid4().hex
            new_inventory = Inventory(name=name, description=description, token=inventory_token,
                                      slug=slug, owner_id=to_user.id, type=inventory_type,
                                      show_default_fields=show_default_fields,
                                      show_item_images=show_item_images,
                                      show_item_type=show_item_type,
                                      show_item_url=show_item_url,
                                      show_item_location=show_item_location,
                                      show_item_tags=show_item_tags,
                                      access_level=access_level)
            db.session.expire_on_commit = False
            db.session.add(new_inventory)
            db.session.flush()
            new_inventory_id = new_inventory.id
            to_user.inventories.append(new_inventory)
            db.session.commit()
            db.session.expunge_all()
            if token is not None:
                new_inventory.inventory_token = token
                db.session.commit()
            return new_inventory, new_inventory_id

    @staticmethod
    def add_user_list(name: str, description: str, inventory_type: int, user_id: int,
                      show_default_fields: int = True,
                      show_item_images: int = True,
                      show_item_type: int = True,
                      show_item_location: int = True,
                      show_item_tags: int = True,
                      show_item_url: int = False,
                      slug: str = None,
                      access_level: int = 1, token=None) -> Tuple[Optional[dict], bool, str]:
        if name == "":
            return None, False, "List name cannot be empty"

        if slug is None:
            slug = slugify(name)

        with app.app_context():
            try:
                # add it initially private
                to_user = User.query.filter_by(id=user_id).first()
                if to_user is None:
                    return None, False, "User not found"

                new_inventory, new_inventory_id = InventoryService._create_list(name=name, description=description,
                                                                                inventory_type=inventory_type,
                                                                                show_default_fields=show_default_fields,
                                                                                show_item_images=show_item_images,
                                                                                show_item_type=show_item_type,
                                                                                show_item_url=show_item_url,
                                                                                show_item_location=show_item_location,
                                                                                show_item_tags=show_item_tags,
                                                                                slug=slug, to_user=to_user,
                                                                                access_level=access_level,
                                                                                token=token)

                result_return_value = {
                    "id": new_inventory_id,
                    "name": name,
                    "description": description,
                    "slug": slug,
                    "type": inventory_type,
                    "access_level": access_level
                }

                return result_return_value, True, "success"

            except SQLAlchemyError as error:
                app.logger.error(f"Error adding list: {str(error)}")
                return None, True, "Could not add list"

    def add_items(self, inventory_id: int, item_or_itemid: Union[List[Item], int]) -> None:
        inv = self.get(inventory_id)
        # precompute existing item ids to avoid repeated membership checks and N+1 behavior
        existing_ids = {it.id for it in inv.items}

        if not isinstance(item_or_itemid, list):
            item_or_itemid = [item_or_itemid]

        for entry in item_or_itemid:
            if isinstance(entry, Item):
                item = entry
            else:
                item = db.session.get(Item, entry)

            if not item:
                raise ValueError("item not found")

            # skip already-present items and continue adding others
            if item.id in existing_ids:
                continue

            inv.items.append(item)
            existing_ids.add(item.id)

        db.session.commit()

    @staticmethod
    def get_inventory_by_access_token(access_token: str) -> Optional[Inventory]:
        if access_token is None:
            err_msg = f"Error finding inventory by access token: access token is None"
            app.logger.error(err_msg)
            return None
        with app.app_context():
            inventory_ = Inventory.query.filter_by(token=access_token).first()
            if inventory_ is None:
                return None
            else:
                return inventory_

    @staticmethod
    def find_inventory_by_id(inventory_id: int, user_id: int) -> Tuple[Optional[Inventory], Optional[UserInventory]]:
        """Find inventory by ID and user ID.

        This method receives the ID of an inventory and the ID of a user as parameters and returns a tuple
        containing the corresponding Inventory and UserInventory objects. If the inventory or the user is not found,
        the method returns None for both objects.

        Parameters:
            inventory_id (int): The ID of the inventory to find.
            user_id (int): The ID of the user associated with the inventory.

        Returns:
            Tuple[Optional[Inventory], Optional[UserInventory]]: A tuple containing the found Inventory and UserInventory
            objects, or None if either the inventory or the user is not found.

        """

        with app.app_context():
            if not isinstance(inventory_id, int):
                err_msg = f"Error finding inventory by ID: supplied inventory_id is not an integer"
                app.logger.error(err_msg)
                return None, None

            if not isinstance(user_id, int):
                err_msg = f"Error finding inventory by ID: supplied user_id is not an integer"
                app.logger.error(err_msg)
                return None, None

            inventory_ = Inventory.query.filter_by(id=inventory_id).first()
            if inventory_ is None:
                err_msg = f"Error finding inventory by ID: inventory not found"
                app.logger.error(err_msg)
                return None, None

            user_inventory_ = UserInventory.query \
                .filter_by(inventory_id=inventory_.id).filter_by(user_id=user_id).first()
            return inventory_, user_inventory_

    @staticmethod
    def _find_inventory_by(_q_str, _q_str_val, _q, _qa, inventory_owner_id, viewing_user_id) -> Tuple[
        Optional[Inventory], Optional[UserInventory]]:
        with app.app_context():
            if not isinstance(_q_str_val, str):
                err_msg = f"Error finding inventory by {_q_str}: supplied token is not a string"
                app.logger.error(err_msg)
                return None, None

            if not isinstance(inventory_owner_id, int):
                err_msg = f"Error finding inventory by slug: supplied inventory_owner_id is not an integer"
                app.logger.error(err_msg)
                return None, None

            user_is_logged_in = (viewing_user_id is not None)

            # do some new code here to fix
            # try to find a user inventory for the user and the inventory id
            inventory_ = Inventory.query.filter(_q == _qa).one_or_none()
            if not inventory_:
                return None, None

            inventory_id = inventory_.id

            # if the user is not logged in, then we can only get the inventory if it is public
            if not user_is_logged_in:
                if inventory_.access_level != __PUBLIC__:
                    return None, None
                else:
                    # There will not be a user inventory
                    return inventory_, None

            else:
                # if the user is logged in, then we can get the
                # inventory if it is public or if the user has access to it
                user_inventory_ = UserInventory.query.filter(UserInventory.user_id == viewing_user_id).filter(
                    UserInventory.inventory_id == inventory_id).one_or_none()

                if user_inventory_ is not None:
                    return inventory_, user_inventory_
                else:
                    if inventory_.access_level == __PUBLIC__:
                        return inventory_, None
                    else:
                        return None, None

    @staticmethod
    def find_inventory_by_token(inventory_token: str,
                                inventory_owner_id: int = None,
                                viewing_user_id: int = None) -> Tuple[Optional[Inventory], Optional[UserInventory]]:
        """
        Find inventory by slug.

        Searches for an inventory using its unique slug. Optionally, you can provide the owner's ID and the ID of the viewing user.

        :param inventory_token: The slug of the inventory to find.
        :type inventory_token: str
        :param inventory_owner_id: The ID of the owner of the inventory (optional).
        :type inventory_owner_id: int, default None
        :param viewing_user_id: The ID of the viewing user (optional).
        :type viewing_user_id: int, default None
        :return: A tuple containing the found inventory and user inventory (if applicable).
        :rtype: Tuple[Optional[Inventory], Optional[UserInventory]]
        """
        return InventoryService._find_inventory_by(_q_str="token", _q_str_val=inventory_token,
                                                   _q=Inventory.inventory_token,
                                                   _qa=inventory_token, inventory_owner_id=inventory_owner_id,
                                                   viewing_user_id=viewing_user_id)

    @staticmethod
    def find_inventory_by_slug(inventory_slug: str,
                               inventory_owner_id: int = None,
                               viewing_user_id: int = None) -> Tuple[Optional[Inventory], Optional[UserInventory]]:
        """
        Find inventory by slug.

        Searches for an inventory using its unique slug. Optionally, you can provide the owner's ID and the ID of the viewing user.

        :param inventory_slug: The slug of the inventory to find.
        :type inventory_slug: str
        :param inventory_owner_id: The ID of the owner of the inventory (optional).
        :type inventory_owner_id: int, default None
        :param viewing_user_id: The ID of the viewing user (optional).
        :type viewing_user_id: int, default None
        :return: A tuple containing the found inventory and user inventory (if applicable).
        :rtype: Tuple[Optional[Inventory], Optional[UserInventory]]
        """
        return InventoryService._find_inventory_by(_q_str="slug", _q_str_val=inventory_slug, _q=Inventory.slug,
                                                   _qa=inventory_slug, inventory_owner_id=inventory_owner_id,
                                                   viewing_user_id=viewing_user_id)

    @staticmethod
    def add_item_to_inventory(item_id=None, item_name=None, item_desc=None, item_type_name_or_id=None, item_tags=None,
                              inventory_id=None, user_id=None, item_quantity=1, item_url=None,
                              item_location_id=None, item_specific_location="", custom_fields=None,
                              item_token=None) -> dict:

        if item_name is None:
            return {"status": "error", "item": {}, "msg": "Item name cannot be None"}
        if item_desc is None:
            item_desc = item_name
        if item_location_id is None:
            _default_user_location = LocationService.find_default_user_location(user_id=user_id)
            item_location_id = _default_user_location.id

        app_context = app.app_context()

        with app_context:

            try:
                if custom_fields is None:
                    custom_fields = {}

                _item_type_int = None
                _item_type_str = None
                if isinstance(item_type_name_or_id, int):
                    _item_type_int = item_type_name_or_id
                else:
                    _item_type_str = item_type_name_or_id

                # If item_type is none set it to the in-built Not Set item type
                if item_type_name_or_id is None:
                    item_type_ = db.session.query(ItemType).filter_by(slug="not-set").filter_by(
                        user_id=None).one_or_none()
                    if item_type_ is not None:
                        _item_type_int = item_type_.id

                else:
                    # check if the user has an item type with the same name
                    item_type_ = ItemTypeService.get_user_or_system_item_type(user_id=user_id,
                                                                              item_type_name_or_slug=_item_type_str)

                    if item_type_ is None:
                        # add new user item type
                        item_type_ = ItemType(name=_item_type_str, user_id=user_id)
                        db.session.add(item_type_)
                        db.session.commit()
                        db.session.flush()

                    _item_type_int = item_type_.id

                if item_token is not None:
                    new_item = ItemService.get_item_by_token(user_id=user_id, item_token=item_token)

                if item_token is None or new_item is None:
                    # create the new item
                    new_item = Item(name=item_name, description=item_desc, user_id=user_id, quantity=item_quantity,
                                    url=item_url, item_type=_item_type_int,
                                    location_id=item_location_id, specific_location=item_specific_location)
                    db.session.add(new_item)
                    if item_token is not None:
                        new_item.item_token = item_token
                    else:
                        new_item.token = token_urlsafe()
                    # get new item ID and set the item slug
                    db.session.flush()
                    item_slug = f"{str(new_item.id)}-{slugify(item_name)}"
                    new_item.slug = item_slug

                # new_item.item_type = item_type_.id
                # db.session.commit()

                if item_tags is not None:
                    for tag in item_tags:
                        if tag != '':
                            tag = tag.strip()
                            tag = tag.replace(" ", "@#$")
                            instance = db.session.query(Tag).filter_by(tag=tag).one_or_none()
                            if not instance:
                                instance = Tag(tag=tag, user_id=user_id)

                            if instance not in new_item.tags:
                                new_item.tags.append(instance)

                if inventory_id is None or inventory_id == '' or inventory_id == -1:
                    default_user_inventory_ = InventoryService.get_user_default_inventory(user_id=user_id)
                    if default_user_inventory_ is not None:
                        default_user_inventory_id_ = default_user_inventory_.id
                        stmt = db.session.query(Inventory).where(Inventory.id == default_user_inventory_id_)
                        inventory_ = db.session.execute(stmt).first()[0]
                else:
                    stmt = db.session.query(Inventory).where(Inventory.id == inventory_id)
                    inventory_ = db.session.execute(stmt).first()[0]

                inventory_.items.append(new_item)

                if item_id is None:
                    db.session.add(new_item)

                db.session.commit()

                ItemService.add_new_item_field(new_item, custom_fields, user_id=user_id, app_context=app_context)

                return_data = {
                    "status": "success",
                    "item": {
                        "id": new_item.id,
                        "name": new_item.name,
                        "description": new_item.description,
                        "user_id": new_item.user_id,
                        "quantity": new_item.quantity,
                        "url": new_item.url,
                        "location_id": new_item.location_id,
                        # "tags": [t.tag for t in new_item.tags],
                        "specific_location": new_item.specific_location

                    }
                }
                return_data['item']['tags'] = []
                item_tags = new_item.tags
                for tag in item_tags:
                    return_data['item']['tags'].append({"tag": tag.tag})

            except Exception as e:
                return_data = {
                    "status": "error",
                    "item": {},
                    "msg": str(e)
                }
                # log this error

            return return_data


class LocationService:

    @staticmethod
    def delete_locations(user_id: int, location_ids) -> dict:
        location_ids_list = []
        with app.app_context():
            if not isinstance(location_ids, list):
                location_ids_list = [location_ids]
            else:
                location_ids_list = location_ids

            stmt = select(Location).join(User) \
                .where(Location.user_id == user_id) \
                .where(Location.id.in_(location_ids_list))
            locations_from_db = db.session.execute(stmt).all()

            user_default_location_ = Location.query.filter_by(name="None") \
                .filter_by(user_id=user_id).one_or_none()

            for location_ in locations_from_db:
                if location_[0] is not None:
                    location_ = location_[0]

                    location_id = location_.id
                    try:
                        # find any items with this location and chnge to None
                        if user_default_location_ is not None:
                            items_ = Item.query.filter_by(location_id=location_id) \
                                .filter_by(user_id=user_id).all()
                            for row in items_:
                                row.location_id = user_default_location_.id
                            # db.session.commit()

                        db.session.delete(location_)
                        # db.session.commit()

                    except SQLAlchemyError as err:
                        app.logger.error(f"Failed to delete locations by IDs: {str(err)}")
                        return {"success": False}

            db.session.commit()
            return {"success": True}

    @staticmethod
    def delete_user_locations(user_id: int) -> int:
        if user_id is None:
            return 0

        with app.app_context():
            locations_to_delete = Location.query.filter_by(user_id=user_id).all()
            number_locations_deleted = 0

            for location_ in locations_to_delete:
                db.session.delete(location_)
                number_locations_deleted += 1

            status, msg = _commit()
            if not status:
                app.logger.error(f"Could not delete user locations: {msg}")
                return 0

            return number_locations_deleted

    @staticmethod
    def get_user_location_by_id(location_id: str, user_id: int) -> Optional[dict]:
        if location_id is None:
            app.logger.error(f"Location was attempted to be added with ID=None for user {user_id}")
            return None
        if user_id is None:
            app.logger.error(f"Location was attempted to be added with ID={location_id} with user_id=None")
            return None

        with app.app_context():
            try:
                stmt = select(Location).join(User).where(User.id == user_id).where(Location.id == location_id)
                result = db.session.execute(stmt).one_or_none()
                if result is not None:
                    return _to_dict(result[0])
            except SQLAlchemyError as err:
                app.logger.error(f"Failed trying to find a user location id={location_id}. {str(err)}")
                return None
            return None

    @staticmethod
    def get_or_add_new_location(location_name: str, location_description: str, to_user_id: User) -> dict:
        """
        Get or add a new location to the database.

        :param location_name: The name of the location.
        :param location_description: The description of the location.
        :param to_user_id: The user ID associated with the location.
        :type location_name: str
        :type location_description: str
        :type to_user_id: User
        :return: A dictionary containing the status, ID, name, and description of the location.
        :rtype: dict
        """
        with app.app_context():
            location_ = Location.query.filter_by(name=location_name).filter_by(user_id=to_user_id).one_or_none()
            if location_ is None:
                try:
                    location_ = Location(name=location_name, description=location_description, user_id=to_user_id)
                    db.session.add(location_)
                    db.session.commit()
                    db.session.flush()
                    db.session.expire_all()
                except Exception as e:
                    err_msg = f"Failed to add new location due to: {str(e)}"
                    app.logger.error(err_msg)
                    db.session.rollback()
                    return {
                        "status": False,
                        "new": True,
                        "message": err_msg,
                        "id": -1,
                        "name": "",
                        "description": ""
                    }
            return {
                "status": True,
                "new": False,
                "message": "",
                "id": location_.id,
                "name": location_.name,
                "description": location_.description
            }

    @staticmethod
    def find_default_user_location(user_id: int) -> Optional[Location]:
        """
        Return the user's default Location or None.

        - Validates `user_id`.
        - Safely resolves the user and queries for the default location named
          `__DEFAULT___<username>`.
        - Catches and logs database errors and returns None on failure.
        """
        if not user_id:
            app.logger.debug("find_default_user_location called with empty user_id")
            return None

        with app.app_context():
            try:
                user_ = UserService.get_user_by_id(user_id=user_id)
                if user_ is None:
                    app.logger.debug(f"find_default_user_location: user not found for id={user_id}")
                    return None

                default_name = f"{__DEFAULT__}_{user_.username}"
                location_ = db.session.query(Location).filter_by(user_id=user_id, name=default_name).one_or_none()
                return location_
            except SQLAlchemyError as ex:
                app.logger.error(f"Error fetching default location for user {user_id}: {ex}")
                db.session.rollback()
                return None
            except Exception as ex:
                app.logger.error(f"Unexpected error in find_default_user_location for user {user_id}: {ex}")
                return None

    @staticmethod
    def get_user_locations_by_id(user_id: int) -> List[dict]:
        with app.app_context():
            try:
                stmt = select(Location).where(Location.user_id == user_id)
                _result = db.session.execute(stmt).all()
                locations_results = []
                for row in _result:
                    locations_results.append(
                        {
                            "id": row[0].id,
                            "name": row[0].name,
                            "description": row[0].description,
                            "user_id": row[0].user_id
                        }
                    )
                return locations_results
            except SQLAlchemyError as err:
                app.logger.error(f"Failed to get user locations ny ID: {str(err)}")
                return []

    @staticmethod
    def get_location_by_id(location_id: int) -> Union[dict, None]:
        """
        Find location by id.

        :param location_id: The id of the location to find.
        :return: A dictionary representing the location if found, otherwise None.
        """

        if location_id is None:
            return None

        try:
            location_ = Location.query.filter_by(id=location_id).one_or_none()
        except (NoResultFound, InvalidRequestError, SQLAlchemyError):
            return None
        if location_ is not None:
            return location_.__dict__
        return None

    @staticmethod
    def get_location_by_name(location_name: str) -> Union[dict, None]:
        """
        Find location by name.

        :param location_name: The name of the location to find.
        :return: A dictionary representing the location if found, otherwise None.
        """

        if location_name is None:
            return None

        try:
            location_ = Location.query.filter_by(name=location_name).one_or_none()
        except (NoResultFound, InvalidRequestError, SQLAlchemyError):
            return None
        if location_ is not None:
            return location_.__dict__
        return None

    @staticmethod
    def update_location_by_id(location_data: dict, user: User) -> Tuple[bool, str]:
        """
        Update the location information by ID for a given user.

        :param location_data: A dictionary containing the updated location information.
        :param user: An instance of User representing the user whose location is being updated.

        :return: A tuple containing a boolean value indicating the success of the update operation, and a string message indicating the result or any error.

        The location_data parameter must be a dictionary containing the following keys:
            - 'id': The ID of the location to be updated.
            - 'name': The updated name for the location.
            - 'description': The updated description for the location.

        If the user parameter is None or not an instance of User, the method returns (False, "Invalid user").

        If the location_data parameter is not a dictionary, the method returns (False, "Location data must be a dictionary").

        If there is no location with the specified ID found for the given user, the method returns (False, "No location with ID <location_id> found for user <user.username>").

        If the update operation is successful, the method returns (True, "Location updated successfully").

        If there is an error during the update operation, the method returns (False, "Could not update location with ID <location_id> for user <user.username>").

        Note: This method requires the application context to be active.
        """
        if user is None or not isinstance(user, User):
            msg = "Invalid user"
            app.logger.error(msg)
            return False, msg

        if not isinstance(location_data, dict):
            msg = f"Location data must be a dictionary"
            app.logger.error(msg)
            return False, msg

        with app.app_context():
            location_id = location_data['id']

            location_ = Location.query.filter_by(id=location_id).filter_by(user_id=user.id).one()
            if location_ is None:
                msg = f"No location with id {location_id} found for user {user.username}"
                app.logger.error(msg)
                return False, msg

            location_.name = location_data['name']
            location_.description = location_data['description']

            try:
                # db.session.merge(location_)
                db.session.commit()
                return True, "Location updated successfully"
            except SQLAlchemyError as e:
                print(e)
                db.session.rollback()
                msg = f"Could not update location with id {location_id} for user {user.username}"
                app.logger.error(msg)
                return False, msg

    @staticmethod
    def get_all_user_locations(user_id: int) -> list[Location]:
        """
        Return all Location objects for a user.

        - `user_id` must be a positive int.
        - Verifies the user exists via `UserService.get_user_by_id`.
        - Uses a safe SQLAlchemy select, orders by name, and returns a flat list.
        - Logs exceptions and rolls back the session on error, returning an empty list.
        """
        if not isinstance(user_id, int) or user_id <= 0:
            app.logger.error("get_all_user_locations: user_id must be a positive integer")
            return []

        with app.app_context():
            try:
                # verify user exists to avoid querying for non-existent users
                if UserService.get_user_by_id(user_id=user_id) is None:
                    app.logger.debug(f"get_all_user_locations: no user found for id={user_id}")
                    return []

                stmt = select(Location).where(Location.user_id == user_id).order_by(Location.name)
                locations = db.session.execute(stmt).scalars().all()
                return locations
            except SQLAlchemyError as e:
                app.logger.exception(f"Error fetching locations for user_id={user_id}: {e}")
                try:
                    db.session.rollback()
                except Exception:
                    pass
                return []


class ItemTypeService:

    @staticmethod
    def get_itemtype_by_slug(slug: str, user_id: int = None) -> Optional[ItemType]:
        with app.app_context():
            item_type_ = ItemType.query.filter_by(slug=slug.lower().strip()) \
                .filter(or_(ItemType.user_id == user_id, ItemType.user_id == None)).one_or_none()

            if item_type_ is not None:
                return _to_dict(item_type_)

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
                # # Ensure a per-user __NONE__ ItemType exists
                # user_none_type_ = ItemType.query.filter_by(user_id=user_id, name=__NONE__).one_or_none()
                # if user_none_type_ is None:
                #     user_none_type_ = ItemType(name=__NONE__, user_id=user_id, slug=slugify(__NONE__))
                #     db.session.add(user_none_type_)
                #     db.session.flush()  # ensure id is populated

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


class UserInventoryService:
    def add_user_to_inventory(self, user_id: int, inventory_id: int, access_level: int = 0,
                              view: int = 0) -> UserInventory:
        # return existing membership early if present
        existing = db.session.query(UserInventory).filter_by(user_id=user_id, inventory_id=inventory_id).first()
        if existing:
            return existing

        rec = UserInventory(user_id=user_id, inventory_id=inventory_id, access_level=access_level, view=view)
        db.session.add(rec)
        try:
            db.session.commit()
            return rec
        except IntegrityError:
            db.session.rollback()
            # concurrent insert may have created the membership; try to fetch and return it
            existing = db.session.query(UserInventory).filter_by(user_id=user_id, inventory_id=inventory_id).first()
            if existing:
                return existing
            raise

    def remove_user_from_inventory(self, user_id: int, inventory_id: int) -> None:
        rec = db.session.query(UserInventory).filter_by(user_id=user_id, inventory_id=inventory_id).first()
        if not rec:
            raise ValueError("membership not found")
        db.session.delete(rec)
        db.session.commit()

    def list_members(self, inventory_id: int) -> List[UserInventory]:
        return db.session.query(UserInventory).filter_by(inventory_id=inventory_id).all()

    def update_membership(self, user_id: int, inventory_id: int, data: Dict[str, Any]) -> UserInventory:
        rec = db.session.query(UserInventory).filter_by(user_id=user_id, inventory_id=inventory_id).first()
        if not rec:
            raise ValueError("membership not found")
        for k, v in data.items():
            setattr(rec, k, v)
        db.session.commit()
        return rec


class NotificationService:
    pass


class TagService:

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
