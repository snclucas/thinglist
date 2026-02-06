import uuid
from secrets import token_urlsafe
from typing import Dict, Optional, Union, Tuple, List, Any

from slugify import slugify
from sqlalchemy import select, func, and_
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from app import db, app

from models import UserInventory, Inventory, User, Item, ItemType, Tag, InventoryItem
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
        if inventory_id is None:
            return None

        with app.app_context():
            stmt = db.session.query(User, UserInventory.access_level) \
                .join(User, UserInventory.user_id == User.id) \
                .filter(UserInventory.inventory_id == inventory_id)

            try:
                result = db.session.execute(stmt).all()
                return dict(result)
            except Exception as e:
                app.logger.error(f"Could not get users for inventory {inventory_id} due to: {str(e)}")
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
                    return True, "Could not edit list"

            else:
                return True, "Could not edit list"

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
                              item_token=None) -> dict:
        from services.item_service import ItemService
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

