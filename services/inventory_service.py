import hashlib
import hmac
import os
import uuid
from secrets import token_urlsafe
from typing import Dict, Optional, Union, Tuple, List, Any

from slugify import slugify
from sqlalchemy import select, func, and_, or_
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import selectinload

from app import db, app

from models import UserInventory, Inventory, User, Item, ItemType, Tag, InventoryItem, ItemField, Field, TemplateField, FieldTemplate
import base64
from services.item_type_service import ItemTypeService
from services.location_service import LocationService
from services.notification_service import NotificationService
from services.user_service import UserService

from site_globals import __DEFAULT__, __PRIVATE__, __INVENTORY__, __PUBLIC__, __OWNER__


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

    # improved
    @staticmethod
    def get_user_public_lists(for_user_id: int) -> list[dict]:
        """Return public inventories for `for_user_id` with item counts.

        Uses a single query (outer join + group_by) to avoid loading relationships
        per-inventory and to reduce DB roundtrips.
        """
        if not isinstance(for_user_id, int):
            app.logger.debug("get_user_public_lists: for_user_id must be an int")
            return []

        if for_user_id is None:
            return []

        try:
            with app.app_context():
                stmt = (
                    db.session.query(
                        Inventory.id,
                        Inventory.name,
                        Inventory.description,
                        Inventory.slug,
                        Inventory.access_level,
                        Inventory.type,
                        func.count(InventoryItem.id).label("item_count"),
                    )
                    .outerjoin(InventoryItem, InventoryItem.inventory_id == Inventory.id)
                    .filter(
                        Inventory.owner_id == for_user_id,
                        Inventory.access_level == __PUBLIC__,
                    )
                    .group_by(
                        Inventory.id,
                        Inventory.name,
                        Inventory.description,
                        Inventory.slug,
                        Inventory.access_level,
                        Inventory.type,
                    )
                )

                rows = db.session.execute(stmt).all()

                if not rows:
                    return []

                ret_results: list[dict] = []
                for row in rows:
                    # row is a SQLAlchemy Row; access by position or by label
                    item_count = int(row["item_count"] or 0)
                    d = {
                        "inventory_id": int(row[0]),
                        "inventory_name": row[1],
                        "inventory_description": row[2],
                        "inventory_slug": row[3],
                        "inventory_access_level": int(row[4]),
                        "inventory_item_count": item_count,
                        "inventory_type": int(row[5]) if row[5] is not None else None,
                        "userinventory_access_level": __PRIVATE__,
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
    def get_user_default_inventory_id(user_id: int) -> int:
        """Return the user's default inventory id, or -1 if not found or on error."""
        if not isinstance(user_id, int):
            app.logger.debug("get_user_default_inventory_id: user_id must be an integer")
            return -1

        try:
            with app.app_context():
                di_ = InventoryService.get_user_default_inventory(user_id=user_id)
                return int(di_.id) if di_ is not None and getattr(di_, "id", None) is not None else -1
        except Exception as e:
            app.logger.exception(f"Error getting default inventory id for user {user_id}: {e}")
            try:
                db.session.rollback()
            except Exception:
                pass
            return -1

    @staticmethod
    def find_all_user_inventory_meta(user_id: int) -> list[tuple[int, str, str]]:
        """
        Return a list of (Inventory, UserInventory) tuples for the given `user_id`.
        Validates input, runs the query inside the Flask app context, and handles DB errors.
        """
        if not isinstance(user_id, int):
            app.logger.debug("find_all_user_inventory_meta: user_id must be an int")
            return []

        try:
            with app.app_context():
                stmt = select(Inventory.id, Inventory.name, Inventory.slug, UserInventory).join(UserInventory).where(UserInventory.user_id == user_id)
                rows = db.session.execute(stmt).all()
                # normalize SQLAlchemy Row objects to simple tuples
                return [(r[0], r[1], r[2]) for r in rows]
        except SQLAlchemyError as e:
            app.logger.exception("find_all_user_inventory_meta DB error: %s", e)
            try:
                db.session.rollback()
            except Exception:
                pass
            return []
        except Exception as e:
            app.logger.exception("find_all_user_inventory_meta unexpected error: %s", e)
            return []


    @staticmethod
    def find_all_user_inventories(user_id: int) -> list[tuple[Inventory, UserInventory]]:
        """
        Return a list of (UserInventory, Inventory) tuples for the given `user_id`.
        Validates input, runs the query inside the Flask app context, and handles DB errors.
        """
        if not isinstance(user_id, int):
            app.logger.debug("find_all_user_inventories: user_id must be an int")
            return []

        try:
            with app.app_context():
                stmt = select(UserInventory, Inventory).join(Inventory).where(UserInventory.user_id == user_id)
                rows = db.session.execute(stmt).all()
                # normalize SQLAlchemy Row objects to simple tuples
                return [(r[1], r[0]) for r in rows]
        except SQLAlchemyError as e:
            app.logger.exception("find_all_user_inventories DB error: %s", e)
            try:
                db.session.rollback()
            except Exception:
                pass
            return []
        except Exception as e:
            app.logger.exception("find_all_user_inventories unexpected error: %s", e)
            return []

    @staticmethod
    def add_user_to_inventory_from_token(inventory_id: int, user_to_add: User, added_user_access_level: int) -> bool:
        with app.app_context():

            user_inventory_ = UserInventory.query.filter(UserInventory.inventory_id == inventory_id) \
                .filter(UserInventory.user_id == user_to_add.id).one_or_none()

            if user_inventory_ is None:

                _new_user_inventory = UserInventory(user_id=user_to_add.id, inventory_id=inventory_id,
                                                    access_level=added_user_access_level)
                db.session.add(_new_user_inventory)
                db.session.commit()

                inv_ = Inventory.query.filter(Inventory.id == inventory_id).one_or_none()
                if inv_ is not None:
                    msg = f"User @{user_to_add.username} has been added to your inventory " \
                          f"{inv_.name} as viewer using access token"
                    NotificationService.add_user_notification(to_user_id=inv_.owner_id, from_user_id=user_to_add.id,
                                                              message=msg)

                return True

            return False

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
    def save_user_inventory_view(user_id: int, inventory_id: int, view: int):
        with app.app_context():
            user_inventory_ = InventoryService.get_user_inventory_by_id(user_id=user_id, inventory_id=inventory_id)
            if user_inventory_ is not None:
                user_inventory_[0].view = view
                db.session.commit()

    @staticmethod
    def get_user_inventory_by_id(user_id: int, inventory_id: int) -> Optional[UserInventory]:
        if user_id is None or inventory_id is None:
            app.logger.debug("get_user_inventory_by_id called with None parameter(s)")
            return None

        with app.app_context():
            try:
                return UserInventory.query.filter_by(user_id=user_id, inventory_id=inventory_id).one_or_none()
            except SQLAlchemyError:
                app.logger.exception("Database error in get_user_inventory_by_id")
                db.session.rollback()
                return None

    @staticmethod
    def get_users_for_inventory(inventory_id: int) -> Optional[dict]:
        def get_users_for_inventory(inventory_id: int) -> Optional[dict]:
            if inventory_id is None or not isinstance(inventory_id, int):
                return None

            with app.app_context():
                try:
                    stmt = select(User.username, UserInventory.access_level).join(
                        UserInventory, User.id == UserInventory.user_id
                    ).where(UserInventory.inventory_id == inventory_id)

                    rows = db.session.execute(stmt).all()
                    # build a simple username -> access_level map without loading full ORM objects
                    return {row[0]: row[1] for row in rows} if rows else {}
                except SQLAlchemyError as e:
                    app.logger.exception(f"get_users_for_inventory DB error for inventory {inventory_id}: {e}")
                    try:
                        db.session.rollback()
                    except Exception:
                        pass
                    return None
                except Exception as e:
                    app.logger.exception(f"get_users_for_inventory unexpected error for inventory {inventory_id}: {e}")
                    return None

    @staticmethod
    def delete_user_to_inventory(inventory_id: int, user_to_delete_id: int) -> (bool, str):
        if inventory_id is None or user_to_delete_id is None:
            return False, "Inventory ID or user ID cannot be None"

        with app.app_context():
            user_inventory_ = UserInventory.query.filter(UserInventory.inventory_id == inventory_id) \
                .filter(UserInventory.user_id == user_to_delete_id).one_or_none()

            if user_inventory_ is not None:
                if user_inventory_.access_level != __OWNER__:
                    db.session.delete(user_inventory_)
                    db.session.commit()
                    return True, "User deleted successfully"
                else:
                    return False, "Cannot delete owner from inventory"
            else:
                return False, "User not found in inventory"
    @staticmethod
    def delete_item_from_inventory(user: User, inventory_id: int, item_id: int) -> None:
        stmt = select(UserInventory, Item).join(Inventory).join(User).filter(
            and_(User.id == user.id, Inventory.id == inventory_id, Item.id == item_id))

        item = db.session.execute(stmt).first()
        if item is not None:
            item = item[1]
            db.session.delete(item)
            db.session.commit()

    @staticmethod
    def count_all_item_ids_in_inventory(user_id: int, inventory_id: int) -> int:
        """
        Count all item IDs in a specific inventory for a given user.

        This function performs the following:
        - Validates that `user_id` and `inventory_id` are integers.
        - Executes an efficient SQL COUNT query to count the number of items in the specified inventory.
        - Logs any exceptions that occur during the process.
        - Rolls back the database session in case of an error.

        Args:
            user_id (int): The ID of the user whose inventory items are being counted.
            inventory_id (int): The ID of the inventory to count items in.

        Returns:
            int: The total number of items in the specified inventory. Returns 0 if an error occurs or if the inputs are invalid.
        """
        if not isinstance(user_id, int) or not isinstance(inventory_id, int):
            app.logger.error("count_all_item_ids_in_inventory: user_id and inventory_id must be integers")
            return 0

        with app.app_context():
            try:
                stmt = (
                    select(func.count())
                    .select_from(Item)
                    .join(InventoryItem, InventoryItem.item_id == Item.id)
                    .where(Item.user_id == user_id, InventoryItem.inventory_id == inventory_id)
                )
                count = db.session.execute(stmt).scalar_one()
                return int(count or 0)
            except SQLAlchemyError as e:
                app.logger.exception(f"Error counting items in inventory: {e}")
                try:
                    db.session.rollback()
                except Exception:
                    pass
                return 0

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
    def get_number_user_inventories(user_id: int) -> int:
        if not isinstance(user_id, int):
            app.logger.debug("get_number_user_inventories: user_id must be an int")
            return 0

        with app.app_context():
            try:
                stmt = select(func.count()).select_from(UserInventory).where(UserInventory.user_id == user_id)
                count = db.session.execute(stmt).scalar_one()
                return int(count or 0)
            except SQLAlchemyError as e:
                app.logger.exception(f"Error counting user inventories: {e}")
                try:
                    db.session.rollback()
                except Exception:
                    pass
                return 0

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

        with app.app_context():
            # base query selecting the same three entities so result rows are consistent
            base_q = db.session.query(Inventory, UserInventory, User) \
                .join(UserInventory, UserInventory.inventory_id == Inventory.id) \
                .join(User, User.id == Inventory.owner_id)

            if current_user_id is not None and requesting_user_id is not None:
                is_current_user = (current_user_id == requesting_user_id)
            else:
                if requesting_user_id is None:
                    return [], True, ""
                is_current_user = False

            if is_current_user:
                if access_level == -1:
                    stmt = base_q.filter(UserInventory.user_id == current_user_id)
                else:
                    stmt = base_q.filter(
                        UserInventory.user_id == current_user_id,
                        UserInventory.access_level == access_level
                    )
            else:
                # ensure we still select User so unpacking into (inv, user_inv, owner) is valid
                stmt = base_q.filter(
                    Inventory.owner_id == requesting_user_id,
                    Inventory.access_level == __PUBLIC__
                )

            try:
                r = db.session.execute(stmt).all()
            except SQLAlchemyError as e:
                app.logger.exception("get_user_inventories DB error: %s", e)
                try:
                    db.session.rollback()
                except Exception:
                    pass
                return [], False, "Database error"

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
                    "is_default": 1 if inv.is_default else 0,
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
    def add_default_user_list(user_id: int) -> Tuple[Optional[dict], bool, str]:
        user_ = UserService.get_user_by_id(user_id=user_id)
        default_list_dict, status, status_msg = InventoryService.add_user_list(name=f"{__DEFAULT__}_{user_.username}",
                                              description=f"Default inventory for {user_.username}",
                                              access_level=0,
                                              inventory_type=1,
                                              user_id=user_.id)
        return default_list_dict, status, status_msg

    @staticmethod
    def get_user_default_inventory(user_id: int) -> Optional[Inventory]:
        """
        Return the user's default Inventory or None.

        - Validates `user_id`.
        - Safely handles missing user or username.
        - Uses a single query and handles DB errors with logging/rollback.
        """
        if not isinstance(user_id, int):
            app.logger.debug("get_user_default_inventory: user_id must be an int")
            return None

        try:
            with app.app_context():
                user_ = UserService.get_user_by_id(user_id=user_id)
                if user_ is None:
                    app.logger.debug("get_user_default_inventory: user not found for id %s", user_id)
                    return None

                username = getattr(user_, "username", None)
                if not isinstance(username, str) or not username:
                    app.logger.debug("get_user_default_inventory: invalid username for user id %s", user_id)
                    return None

                default_name = f"{__DEFAULT__}_{username}"
                inventory_ = db.session.query(Inventory).filter(
                    Inventory.name == default_name,
                    Inventory.owner_id == user_.id
                ).one_or_none()
                return inventory_
        except SQLAlchemyError as e:
            app.logger.exception("get_user_default_inventory DB error: %s", e)
            try:
                db.session.rollback()
            except Exception:
                pass
            return None
        except Exception as e:
            app.logger.exception("get_user_default_inventory unexpected error: %s", e)
            return None

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
                     is_default: bool = False,
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
                                      is_default=is_default,
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
    def edit_inventory_data(user_id: int, inventory_id: int, name: str,
                            description: str, inventory_type: int,
                            show_default_fields: int,
                            show_item_images: int,
                            show_item_type: int,
                            show_item_location: int,
                            show_item_tags: int,
                            show_item_url: int,
                            access_level: int) -> Tuple[bool, str]:
        with app.app_context():

            stmt = select(UserInventory, Inventory).join(Inventory) \
                .where(UserInventory.user_id == user_id) \
                .where(UserInventory.inventory_id == inventory_id)

            results_ = db.session.execute(stmt).one_or_none()

            if results_ is not None:
                results_[1].name = name
                results_[1].description = description
                results_[1].type = inventory_type
                results_[1].show_default_fields = show_default_fields

                results_[1].show_item_images = show_item_images
                results_[1].show_item_type = show_item_type
                results_[1].show_item_url = show_item_url
                results_[1].show_item_location = show_item_location
                results_[1].show_item_tags = show_item_tags

                results_[1].access_level = access_level

                try:
                    db.session.commit()
                    return True, "success"
                except SQLAlchemyError as error:
                    return False, "Could not edit list"

            else:
                return False, "Could not edit list"

    @staticmethod
    def regenerate_inventory_token(user_id, inventory_id, new_token) -> Tuple[bool, str]:
        with app.app_context():
            query = db.session.query(UserInventory, Inventory).join(Inventory) \
                .filter(UserInventory.user_id == user_id) \
                .filter(UserInventory.inventory_id == inventory_id)

            results = query.one_or_none()
            if results is not None:
                user_inventory_, inventory_ = results
                inventory_.token = new_token

                try:
                    db.session.commit()
                    return True, "Token updated successfully"
                except SQLAlchemyError as ex:
                    return False, ex

            return False, "No inventory found"

    @staticmethod
    def add_user_list(name: str, description: str, inventory_type: int, user_id: int,
                      show_default_fields: int = True,
                      show_item_images: int = True,
                      show_item_type: int = True,
                      show_item_location: int = True,
                      show_item_tags: int = True,
                      show_item_url: int = False,
                      is_default: bool = False,
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
                                                                                is_default=is_default,
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
                return None, False, "Could not add list"

    @staticmethod
    def set_inventory_default_fields(inventory_id, user, default_fields):
        with app.app_context():
            if inventory_id == '':
                inventory_ = InventoryService.get_user_default_inventory(user_id=user.id)
            else:
                inventory_ = Inventory.query.filter_by(id=inventory_id).first()

            user_inventory_ = UserInventory.query \
                .filter_by(inventory_id=inventory_.id).filter_by(user_id=user.id).first()
            inventory_.default_fields = ",".join(default_fields)

            db.session.commit()
            return

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
    def get_user_inventories2(current_user_id: int, requesting_user_id: int, access_level: int = -1):
        if not isinstance(access_level, int):
            return [], False, "access_level must be an integer"

        if not isinstance(current_user_id, int) and current_user_id is not None:
            return [], False, "current_user_id must be an integer"

        if not isinstance(requesting_user_id, int) and requesting_user_id is not None:
            return [], False, "requesting_user_id must be an integer"

        with app.app_context():
            # eager load Inventory.items and each Item's related_items, location and item_type
            base_q = db.session.query(Inventory, UserInventory, User) \
                .options(
                selectinload(Inventory.items).selectinload(Item.related_items),
                selectinload(Inventory.items).selectinload(Item.location),
                selectinload(Inventory.items).selectinload(Item.item_type_obj),
            ) \
                .join(UserInventory, UserInventory.inventory_id == Inventory.id) \
                .join(User, User.id == Inventory.owner_id)

            if current_user_id is not None and requesting_user_id is not None:
                is_current_user = (current_user_id == requesting_user_id)
            else:
                if requesting_user_id is None:
                    return [], True, ""
                is_current_user = False

            if is_current_user:
                if access_level == -1:
                    stmt = base_q.filter(UserInventory.user_id == current_user_id)
                else:
                    stmt = base_q.filter(
                        UserInventory.user_id == current_user_id,
                        UserInventory.access_level == access_level
                    )
            else:
                stmt = base_q.filter(
                    Inventory.owner_id == requesting_user_id,
                    Inventory.access_level == __PUBLIC__
                )

            try:
                # scalars() returns the Inventory instances (first entity) with the eager-loaded relationships
                r = db.session.execute(stmt).scalars().all()
            except SQLAlchemyError as e:
                app.logger.exception("get_user_inventories DB error: %s", e)
                try:
                    db.session.rollback()
                except Exception:
                    pass
                return [], False, "Database error"

            # Attach extra field values (from item_fields) to each Item as `extra_fields`.
            # Also, if an Inventory has a `field_template`, include template-defined fields (even without values)
            try:
                # collect all item ids from the inventories
                item_ids = set()
                template_ids = set()
                for inv in r:
                    if getattr(inv, 'field_template', None):
                        template_ids.add(inv.field_template)
                    for it in getattr(inv, 'items', []) or []:
                        if getattr(it, 'id', None) is not None:
                            item_ids.add(it.id)

                # map item_id -> { field_id: {meta... , value: ...} }
                item_field_map = {}
                if item_ids:
                    stmt_if = select(ItemField, Field).join(Field, ItemField.field_id == Field.id) \
                        .where(ItemField.item_id.in_(list(item_ids)))
                    rows_if = db.session.execute(stmt_if).all()
                    for itemfield, field in rows_if:
                        imap = item_field_map.setdefault(itemfield.item_id, {})
                        imap[field.id] = {
                            "item_field_id": itemfield.id,
                            "field_id": field.id,
                            "field_name": field.field,
                            "field_slug": field.slug,
                            "field_type": field.type,
                            "field_data": field.data,
                            "field_ident": field.ident,
                            "value": itemfield.value,
                            "show": bool(itemfield.show)
                        }

                # build template_fields_map: {template_id: [field_meta ordered by TemplateField.order]}
                template_fields_map = {}
                if template_ids:
                    stmt_tf = select(TemplateField, Field).join(Field, TemplateField.field_id == Field.id) \
                        .where(TemplateField.template_id.in_(list(template_ids)))
                    rows_tf = db.session.execute(stmt_tf).all()
                    # collect and then sort per template
                    for tf, field in rows_tf:
                        lst = template_fields_map.setdefault(tf.template_id, [])
                        lst.append({
                            "field_id": field.id,
                            "field_name": field.field,
                            "field_slug": field.slug,
                            "field_type": field.type,
                            "field_data": field.data,
                            "field_ident": field.ident,
                            "order": tf.order
                        })
                    for tid, fl in template_fields_map.items():
                        fl.sort(key=lambda x: (x.get('order', 9999), x.get('field_id')))

                # attach extra_fields to each item on the Inventory objects
                for inv in r:
                    tpl_fields = template_fields_map.get(inv.field_template)
                    for it in getattr(inv, 'items', []) or []:
                        imap = item_field_map.get(it.id, {})
                        extras = []
                        if tpl_fields:
                            # include each template-defined field in order, filling values from imap when present
                            for f in tpl_fields:
                                val = imap.get(f['field_id'])
                                if val:
                                    # remove field_id, and item_field_id
                                    val.pop('field_id', None)
                                    val.pop('item_field_id', None)
                                    extras.append(val)
                                else:
                                    extras.append({
                                        #"item_field_id": None,
                                        #"field_id": f['field_id'],
                                        "field_name": f['field_name'],
                                        "field_slug": f['field_slug'],
                                        "field_type": f['field_type'],
                                        "field_data": f['field_data'],
                                        "field_ident": f['field_ident'],
                                        "value": None,
                                        "show": False
                                    })
                        else:
                            # no template: include only fields that have values for this item
                            extras = sorted(list(imap.values()), key=lambda x: x.get('field_name'))

                        setattr(it, 'extra_fields', extras)

            except Exception as e:
                app.logger.exception(f"Error attaching extra item fields: {e}")

            return r

    @staticmethod
    def get_serialized_user_inventories(inventories, include_images: bool = True) -> list:
        """
        Return a JSON-serializable list of inventories (with items, locations, item types, related items)
        for `user_id`. All relationships are eager-loaded and accessed while the session is open.
        """
        with app.app_context():
            out = []

            # batch owner ids, template ids, and inventory ids
            owner_ids = set()
            template_ids = set()
            inv_ids = []
            for inv in inventories:
                inv_ids.append(inv.id)
                if getattr(inv, 'owner_id', None) is not None:
                    owner_ids.add(inv.owner_id)
                if getattr(inv, 'field_template', None):
                    template_ids.add(inv.field_template)

            # batch fetch owner usernames
            owner_map = {}
            if owner_ids:
                try:
                    owner_rows = db.session.query(User.id, User.username).filter(User.id.in_(list(owner_ids))).all()
                    owner_map = {r[0]: r[1] for r in owner_rows}
                except Exception:
                    owner_map = {}

            # batch fetch template field slugs/names
            template_meta = {}
            if template_ids:
                try:
                    # get template basic info
                    ft_rows = db.session.query(FieldTemplate.id, FieldTemplate.ident, FieldTemplate.name).filter(FieldTemplate.id.in_(list(template_ids))).all()
                    for tid, ident, name in ft_rows:
                        template_meta[tid] = {"ident": ident, "name": name, "slugs": []}

                    # fetch fields for these templates
                    if template_meta:
                        stmt_tf = select(TemplateField, Field).join(Field, TemplateField.field_id == Field.id).where(TemplateField.template_id.in_(list(template_meta.keys())))
                        rows_tf = db.session.execute(stmt_tf).all()
                        for tf, field in rows_tf:
                            if tf.template_id in template_meta:
                                template_meta[tf.template_id]["slugs"].append(field.slug)
                        # ensure order is preserved by TemplateField.order
                        # map of template_id -> list of (order, slug)
                        if template_meta:
                            ordered = {tid: [] for tid in template_meta.keys()}
                            for tf, field in rows_tf:
                                ordered[tf.template_id].append((getattr(tf, 'order', 9999), field.slug))
                            for tid, lst in ordered.items():
                                lst.sort()
                                template_meta[tid]["slugs"] = [s for _, s in lst]
                except Exception:
                    template_meta = {}

            # batch fetch user_inventory collaborators per inventory
            inv_users_map = {}
            if inv_ids:
                try:
                    ui_rows = db.session.query(UserInventory.inventory_id, User.username, UserInventory.access_level).join(User, User.id == UserInventory.user_id).filter(UserInventory.inventory_id.in_(inv_ids)).all()
                    for inv_id, uname, alevel in ui_rows:
                        inv_users_map.setdefault(inv_id, []).append((uname, alevel))
                except Exception:
                    inv_users_map = {}

            # Now iterate inventories and build output using maps (avoids per-inv DB queries)
            user_images_base = app.config.get('USER_IMAGES_BASE_PATH')
            image_secret_key = app.config.get('IMAGE_SECRET_KEY')

            for inv in inventories:
                owner_username = owner_map.get(getattr(inv, 'owner_id', None))

                inv_dict = {
                    "ident": inv.ident,
                    "name": inv.name,
                    "description": inv.description,
                    "slug": inv.slug,
                    "inventory_token": getattr(inv, 'inventory_token', None) or getattr(inv, 'token', None),
                    "type": inv.type,
                    "default_fields": getattr(inv, 'default_fields', None),
                    "show_default_fields": 1 if getattr(inv, 'show_default_fields', False) else 0,
                    "show_item_images": 1 if getattr(inv, 'show_item_images', False) else 0,
                    "show_item_type": 1 if getattr(inv, 'show_item_type', False) else 0,
                    "show_item_location": 1 if getattr(inv, 'show_item_location', False) else 0,
                    "show_item_tags": 1 if getattr(inv, 'show_item_tags', False) else 0,
                    "show_item_url": 1 if getattr(inv, 'show_item_url', False) else 0,
                    "access_level": inv.access_level,
                    "owner": owner_username,
                    "items": []
                }

                for item in getattr(inv, "items", []) or []:
                    item_dict = {
                        "ident": item.ident,
                        "item_token": getattr(item, 'item_token', None),
                        "name": item.name,
                        "description": item.description,
                        "quantity": item.quantity,
                        "specific_location": getattr(item, "specific_location", None),
                        "location": {
                            "ident": item.location.ident,
                            "name": item.location.name
                        } if getattr(item, "location", None) else None,
                        "item_type": {
                            "slug": getattr(getattr(item, "item_type_obj", None), 'slug', None),
                            "name": getattr(getattr(item, "item_type_obj", None), 'name', None)
                        } if getattr(item, "item_type_obj", None) else None,
                        "type_slug": getattr(getattr(item, "item_type_obj", None), 'slug', None) or 'none',
                        "related_items": [
                            {"ident": ri.ident, "item_token": ri.item_token, "name": ri.name}
                            for ri in getattr(item, "related_items", []) or []
                        ],
                        "tags": [t.tag for t in getattr(item, "tags", []) or []],
                        "images": []
                    }

                    # include image binary data and hash for each image so imports can recreate files
                    for img in getattr(item, 'images', []) or []:
                        img_filename = getattr(img, 'image_filename', None)
                        is_main = 'true' if img_filename and getattr(item, 'main_image', None) == img_filename else 'false'
                        image_entry = {"image_filename": img_filename, "is_main": is_main}
                        try:
                            if include_images and img_filename and user_images_base and image_secret_key is not None:
                                img_path = os.path.join(app.root_path, user_images_base, str(inv.owner_id), img_filename)
                                with open(img_path, 'rb') as f:
                                    data = f.read()
                                b64 = base64.b64encode(data).decode('utf-8')
                                image_entry['image_data'] = b64
                                raw = b64.encode('utf-8')
                                hashed = hmac.new(image_secret_key.encode('utf-8') if isinstance(image_secret_key, str) else image_secret_key, raw, hashlib.sha1)
                                img_hmac_hash = base64.encodebytes(hashed.digest()).decode('utf-8')
                                image_entry['image_hash'] = img_hmac_hash
                            else:
                                image_entry['image_data'] = None
                                image_entry['image_hash'] = None
                        except Exception:
                            image_entry['image_data'] = None
                            image_entry['image_hash'] = None
                        item_dict['images'].append(image_entry)

                    # include extra_fields if attached by get_user_inventories2
                    extras = getattr(item, 'extra_fields', None)
                    if extras is not None:
                        cleaned_extras = []
                        custom_map = {}
                        for ef in extras:
                            field_slug = ef.get('field_slug') or ef.get('field_ident')
                            cleaned = {
                                "field_ident": ef.get('field_ident'),
                                "field_slug": field_slug,
                                "field_name": ef.get('field_name'),
                                "field_type": ef.get('field_type'),
                                "field_data": ef.get('field_data'),
                                "value": ef.get('value'),
                                "show": bool(ef.get('show', False))
                            }
                            cleaned_extras.append(cleaned)
                            key = field_slug or ef.get('field_ident')
                            custom_map[key] = ef.get('value')

                        item_dict['extra_fields'] = cleaned_extras
                        item_dict['custom_fields'] = custom_map

                    inv_dict["items"].append(item_dict)

                # include inventory's field template as a field_set for re-import (use pre-fetched meta)
                if getattr(inv, 'field_template', None) and template_meta:
                    meta = template_meta.get(inv.field_template)
                    if meta:
                        inv_dict['field_set'] = {"ident": meta.get('ident'), "name": meta.get('name'), "slugs": meta.get('slugs', [])}

                # include user inventory (sharing) entries by username and access_level (no numeric ids)
                try:
                    inv_dict['user_inventory'] = []
                    for uname, alevel in inv_users_map.get(inv.id, []):
                        if uname == owner_username:
                            continue
                        inv_dict['user_inventory'].append({"username": uname, "access_level": alevel})
                except Exception:
                    inv_dict['user_inventory'] = []

                out.append(inv_dict)

            return out

    @staticmethod
    def get_inventory_by_access_token(access_token: str) -> Optional[Inventory]:
        if not isinstance(access_token, str) or not access_token.strip():
            app.logger.error("get_inventory_by_access_token: access_token must be a non-empty string")
            return None
        with app.app_context():
            try:
                # try both column names used in the codebase (some places use `inventory_token`, others `token`)
                inventory_ = db.session.query(Inventory).filter(Inventory.inventory_token == access_token).one_or_none()
                if inventory_ is None:
                    inventory_ = db.session.query(Inventory).filter(Inventory.token == access_token).one_or_none()
                return inventory_
            except SQLAlchemyError as e:
                app.logger.exception(f"Database error finding inventory by access token: {e}")
                try:
                    db.session.rollback()
                except Exception:
                    pass
                return None
            except Exception as e:
                app.logger.exception(f"Unexpected error finding inventory by access token: {e}")
                return None

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

            if inventory_owner_id is not None and not isinstance(inventory_owner_id, int):
                err_msg = f"Error finding inventory by {_q_str}: supplied inventory_owner_id is not an integer"
                app.logger.error(err_msg)
                return None, None

            user_is_logged_in = (viewing_user_id is not None)

            try:
                # Build a single query that returns Inventory and (optional) UserInventory in one round-trip.
                # Use an ON clause for the left join so we only get the UserInventory for the viewing_user_id.
                from sqlalchemy import and_

                join_condition = and_(UserInventory.inventory_id == Inventory.id,
                                      UserInventory.user_id == viewing_user_id)

                query = db.session.query(Inventory, UserInventory).outerjoin(UserInventory, join_condition).filter(_q == _qa)

                # If an owner id is supplied, narrow the search to that owner (fast path).
                if inventory_owner_id is not None:
                    query = query.filter(Inventory.owner_id == inventory_owner_id)

                row = query.one_or_none()
                if not row:
                    return None, None

                inventory_obj, user_inventory_obj = row[0], row[1]

                # If user not logged in, only allow access to public inventories
                if not user_is_logged_in:
                    if inventory_obj.access_level != __PUBLIC__:
                        return None, None
                    return inventory_obj, None

                # user is logged in: if we have a UserInventory row that matches viewing_user_id return it
                if user_inventory_obj is not None:
                    return inventory_obj, user_inventory_obj

                # otherwise, if inventory is public allow access without a UserInventory entry
                if inventory_obj.access_level == __PUBLIC__:
                    return inventory_obj, None

                # not public and no explicit user access
                return None, None

            except SQLAlchemyError as e:
                app.logger.exception(f"_find_inventory_by DB error: {e}")
                try:
                    db.session.rollback()
                except Exception:
                    pass
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
    def add_user_to_inventory(inventory_id: int, current_user_id: int, user_to_add_username: str,
                              added_user_access_level: int) -> Tuple[bool, str]:
        if inventory_id is None or current_user_id is None or not user_to_add_username:
            return False, "Invalid parameters"

        with app.app_context():
            try:
                user_inventory_ = UserInventory.query.filter_by(inventory_id=inventory_id,
                                                                user_id=current_user_id).one_or_none()
                if user_inventory_ is None:
                    return False, "Inventory not found"

                if user_inventory_.access_level != __OWNER__:
                    return False, "User is not the owner of the inventory"

                if added_user_access_level == __OWNER__:
                    return False, "Cannot add user as owner"

                user_to_add_ = User.query.filter_by(username=user_to_add_username).one_or_none()
                if user_to_add_ is None:
                    return False, "User not found"

                user_to_add_inventory_ = UserInventory.query.filter_by(inventory_id=inventory_id,
                                                                       user_id=user_to_add_.id).one_or_none()

                if user_to_add_inventory_ is not None:
                    user_to_add_inventory_.access_level = added_user_access_level
                else:
                    ui = UserInventory(user_id=user_to_add_.id, inventory_id=inventory_id,
                                       access_level=added_user_access_level)
                    db.session.add(ui)

                db.session.commit()

                # notify the added user; don't fail the operation if notification fails
                try:
                    NotificationService.add_user_notification(to_user_id=user_to_add_.id, from_user_id=current_user_id,
                                                              message="You have been added to the following inventory")
                except Exception:
                    app.logger.exception("Failed to send inventory notification")

                return True, "User added successfully"

            except SQLAlchemyError:
                db.session.rollback()
                app.logger.exception("Database error while adding user to inventory")
                return False, "Database error"

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
                              item_ident=None) -> dict:
        from services.item_service import ItemService
        app.logger.debug(f"add_item_to_inventory called with item_type_name_or_id={item_type_name_or_id!r} (type={type(item_type_name_or_id)}), user_id={user_id}")
        # Coerce numeric-looking item_type parameters to int if possible (handles strings like '196')
        try:
            if item_type_name_or_id is not None and not isinstance(item_type_name_or_id, int):
                if isinstance(item_type_name_or_id, str) and item_type_name_or_id.isdigit():
                    item_type_name_or_id = int(item_type_name_or_id)
                else:
                    # try generic int() coercion for numeric-like objects
                    try:
                        coerced = int(item_type_name_or_id)
                        item_type_name_or_id = coerced
                    except Exception:
                        pass
        except Exception:
            pass
        app.logger.debug(f"add_item_to_inventory called with item_type_name_or_id={item_type_name_or_id!r} (type={type(item_type_name_or_id)}), user_id={user_id}")
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

                # If no item_type provided (None or empty string), ensure there's a system-level 'not-set' ItemType and use it
                if _item_type_int is not None:
                    app.logger.debug(f"Numeric item_type provided; skipping name-resolution. _item_type_int={_item_type_int}")
                # If no item_type provided (None or empty string), ensure there's a system-level 'not-set' ItemType and use it
                elif item_type_name_or_id in (None, ''):
                    item_type_ = db.session.query(ItemType).filter_by(slug="not-set", user_id=None).one_or_none()
                    if item_type_ is None:
                        # create system-level 'not-set' type if missing
                        try:
                            new_it = ItemType(name='Not Set', user_id=None)
                            new_it.slug = 'not-set'
                            db.session.add(new_it)
                            db.session.commit()
                            item_type_ = new_it
                            app.logger.info("Created system item type 'not-set' (id=%s)", getattr(item_type_, 'id', None))
                        except IntegrityError:
                            try:
                                db.session.rollback()
                            except Exception:
                                pass
                            item_type_ = db.session.query(ItemType).filter_by(slug='not-set', user_id=None).one_or_none()

                    if item_type_ is not None:
                        _item_type_int = item_type_.id
                        app.logger.debug("Using system item type 'not-set' id=%s for user_id=%s", _item_type_int, user_id)
                else:
                    # check if the user has an item type with the same name
                    item_type_ = ItemTypeService.get_user_or_system_item_type(user_id=user_id,
                                                                              item_type_name_or_slug=_item_type_str)

                    if item_type_ is None:
                        # If an item type name/string was provided, resolve or create it safely.
                        if _item_type_str:
                            # Prefer existing user/system item type
                            item_type_ = ItemTypeService.get_user_or_system_item_type(user_id=user_id,
                                                                                      item_type_name_or_slug=_item_type_str)

                            if item_type_ is None:
                                # Try to find by computed slug first to avoid duplicate insert races
                                try:
                                    slug_candidate = slugify(_item_type_str)
                                except Exception:
                                    slug_candidate = str(_item_type_str).lower()

                                item_type_ = db.session.query(ItemType).filter(
                                    ItemType.slug == slug_candidate,
                                    or_(ItemType.user_id == user_id, ItemType.user_id.is_(None))
                                ).one_or_none()

                            if item_type_ is None:
                                # Create new ItemType but guard against unique constraint by catching IntegrityError
                                try:
                                    new_it = ItemType(name=str(_item_type_str), user_id=user_id)
                                    db.session.add(new_it)
                                    db.session.commit()
                                    db.session.flush()
                                    item_type_ = new_it
                                except IntegrityError:
                                    # Another transaction likely created it concurrently; rollback and fetch it
                                    try:
                                        db.session.rollback()
                                    except Exception:
                                        pass
                                    item_type_ = ItemTypeService.get_user_or_system_item_type(user_id=user_id,
                                                                                              item_type_name_or_slug=_item_type_str)
                                    if item_type_ is None:
                                        # as a last resort, try system 'not-set' type
                                        item_type_ = db.session.query(ItemType).filter_by(slug='not-set', user_id=None).one_or_none()

                        _item_type_int = getattr(item_type_, 'id', None)
                    else:
                        # We already found an existing item_type_; use its id
                        _item_type_int = getattr(item_type_, 'id', None)

                # If caller provided an item_ident, try to resolve existing item first
                if item_ident is not None:
                    new_item = ItemService.get_item_by_ident(user_id=user_id, item_ident=item_ident)

                # Debug: log resolved item type id before creating the item
                try:
                    app.logger.info(f"Resolved _item_type_int BEFORE create: {_item_type_int} (type={type(_item_type_int)}) for user_id={user_id} incoming_param={item_type_name_or_id!r})")
                except Exception:
                    pass

                # Final safety BEFORE creating the Item: ensure _item_type_int is resolved (so INSERT won't attempt NULL)
                if _item_type_int is None:
                    item_type_ = db.session.query(ItemType).filter_by(slug='not-set', user_id=None).one_or_none()
                    if item_type_ is None:
                        try:
                            new_it = ItemType(name='Not Set', user_id=None)
                            new_it.slug = 'not-set'
                            db.session.add(new_it)
                            db.session.commit()
                            item_type_ = new_it
                            app.logger.info("Created system item type 'not-set' in fallback (id=%s)", getattr(item_type_, 'id', None))
                        except IntegrityError:
                            try:
                                db.session.rollback()
                            except Exception:
                                pass
                            item_type_ = db.session.query(ItemType).filter_by(slug='not-set', user_id=None).one_or_none()

                    if item_type_ is not None:
                        _item_type_int = item_type_.id
                        app.logger.debug("Resolved fallback _item_type_int=%s for user_id=%s", _item_type_int, user_id)

                if item_ident is None or new_item is None:
                    # create the new item
                    new_item = Item(name=item_name, description=item_desc, user_id=user_id, quantity=item_quantity,
                                    url=item_url, item_type=_item_type_int,
                                    location_id=item_location_id, specific_location=item_specific_location)
                    db.session.add(new_item)
                    if item_ident is not None:
                        new_item.ident = item_ident
                    else:
                        new_item.token = str(uuid.uuid4())
                    # get new item ID and set the item slug
                    db.session.flush()
                    item_slug = f"{str(new_item.id)}-{slugify(item_name)}"
                    new_item.slug = item_slug

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
                # Log full exception with traceback to help debugging
                app.logger.exception(f"add_item_to_inventory unexpected error: {e}")
                return_data = {
                    "status": "error",
                    "item": {},
                    "msg": str(e)
                }

            return return_data

    @staticmethod
    def find_inventory_meta_by_slug(inventory_slug: str, inventory_owner_id: int = None, viewing_user_id: int = None) -> Optional[dict]:
        """
        Lightweight metadata lookup for an inventory by slug (fast path).

        Returns a dict (or None) with keys:
          - inventory_id (int)
          - owner_id (int)
          - inventory_access_level (int)
          - user_access_level (Optional[int])  # None if no UserInventory entry for viewing_user_id

        This avoids creating full ORM Inventory/UserInventory objects and is suitable
        for early permission checks in high-traffic endpoints.
        """
        if not isinstance(inventory_slug, str) or inventory_slug == "":
            return None

        if inventory_owner_id is not None and not isinstance(inventory_owner_id, int):
            return None

        try:
            with app.app_context():
                from sqlalchemy import and_
                # select minimal columns
                stmt = db.session.query(
                    Inventory.id.label('inventory_id'),
                    Inventory.owner_id.label('owner_id'),
                    Inventory.access_level.label('inv_access'),
                    UserInventory.access_level.label('ui_access')
                ).outerjoin(UserInventory, and_(UserInventory.inventory_id == Inventory.id,
                                                UserInventory.user_id == viewing_user_id))

                stmt = stmt.filter(Inventory.slug == inventory_slug)
                if inventory_owner_id is not None:
                    stmt = stmt.filter(Inventory.owner_id == inventory_owner_id)

                row = db.session.execute(stmt).first()
                if not row:
                    return None

                # row may be positional or mapping-like
                try:
                    inv_id = int(row['inventory_id'])
                    owner_id = int(row['owner_id'])
                    inv_access = int(row['inv_access'])
                    ui_access = row['ui_access'] if 'ui_access' in row and row['ui_access'] is not None else None
                except Exception:
                    # fallback positional
                    inv_id = int(row[0])
                    owner_id = int(row[1])
                    inv_access = int(row[2])
                    ui_access = row[3] if len(row) > 3 and row[3] is not None else None

                return {
                    'inventory_id': inv_id,
                    'owner_id': owner_id,
                    'inventory_access_level': inv_access,
                    'user_access_level': ui_access
                }
        except SQLAlchemyError:
            try:
                db.session.rollback()
            except Exception:
                pass
            return None
