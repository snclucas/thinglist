import datetime
import os

import uuid
from typing import Union, List, Tuple, Optional

import flask_bcrypt

from slugify import slugify
from sqlalchemy import select, and_, ClauseElement, or_
from sqlalchemy.exc import SQLAlchemyError, NoResultFound, InvalidRequestError
from sqlalchemy.sql.functions import func

from app import db, app
from email_utils import send_email
from models import Inventory, User, Item, UserInventory, InventoryItem, ItemType, Tag, \
    Location, Image, Field, ItemField, FieldTemplate, Notification, TemplateField, Relateditems, ItemImage

_NONE_ = "None"


__PRIVATE__ = 0
__OWNER__ = 0
__VIEWER__ = 1
__COLLABORATOR__ = 2
__PUBLIC__ = 3

__INVENTORY__ = 1
__LIST__ = 2


def drop_then_create():
    try:
        db.drop_all()
        db.create_all()
        db.session.commit()
    except Exception as e:
        print(e)


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
        add_user_inventory(name=f"__default__{new_user.username}", description=f"Default inventory",
                           access_level=0,
                           inventory_type=1,
                           user_id=new_user.id)
        get_or_add_new_location(location_name=_NONE_, location_description="No location (default)",
                                to_user_id=new_user.id)
        add_new_user_itemtype(name=_NONE_, user_id=new_user.id)

        # create folder for user uploads
        user_upload_folder = os.path.join(app.config['USER_IMAGES_BASE_PATH'], str(new_user.id))
        if not os.path.exists(user_upload_folder):
            os.makedirs(user_upload_folder)


    # add default locations, types


# --- Users ---


def add_user_by_details(username: str, email: str, password: str) -> User:
    """

    Parameters:
    - username (str): The username of the user to be added.
    - email (str): The email address of the user to be added.
    - password (str): The password of the user to be added.

    Returns:
    - User: The User object representing the new user.

    Note:
    This method adds a new user to the system by using the provided username, email, and password. It generates a password hash for the provided password and creates a new User object with
    * the given details. The 'activated' flag is set to True by default for the new user.

    The method then calls the 'save_new_user' function to save the new user to the database. If the user is successfully saved, the method returns the User object. Otherwise, it logs an
    * error message and returns the user object.

    Example usage:

    user = add_user_by_details("john_doe", "john@example.com", "password123")
    if user:
        print("User added successfully!")
    else:
        print("Error adding user.")
    """
    with app.app_context():
        password_hash = flask_bcrypt.generate_password_hash(password)
        user = User(username=username, email=email, password=password_hash, activated=True)

        status, message, user = save_new_user(user_=user)

        if status:
            return user
        else:
            err_msg = f"Error adding user by details: {message}"
            app.logger.error(err_msg)
        return user


def find_user(username_or_email: str) -> User:
    user = find_user_by_username(username=username_or_email)
    if not user:
        user = find_user_by_email(email=username_or_email)
    return user


def find_user_by_id2(id: int) -> Optional[User]:
    """
    Args:
        id: The id of the user to find.

    Returns:
        An instance of the User class if the user is found, or None if not found or an error occurs.
    """
    try:
        user = User.query.filter_by(id=id).first()
    except (NoResultFound, InvalidRequestError, SQLAlchemyError) as e:
        err_msg = f"Error finding user by id: {str(e)}"
        app.logger.error(err_msg)
        return None
    return user


def find_user_by_username(username: str) -> Optional[User]:
    """
    Args:
        username: The username of the user to find.

    Returns:
        An instance of the User class if the user is found, or None if not found or an error occurs.
    """
    if username is None:
        return None
    try:
        user = User.query.filter_by(username=username).first()
    except (NoResultFound, InvalidRequestError, SQLAlchemyError) as e:
        err_msg = f"Error finding user by username: {str(e)}"
        app.logger.error(err_msg)
        return None
    return user


def find_user_by_email(email: str) -> Optional[User]:
    """
    Finds a user by email.

    Parameters:
    email (str): The email of the user to find.

    Returns:
    User: The user with the specified email. Returns None if no user is found.

    Raises:
    NoResultFound: If no user is found with the specified email.
    InvalidRequestError: If there is an invalid request error when querying the database.
    SQLAlchemyError: If there is an error with the SQLAlchemy library.

    """
    try:
        user = User.query.filter_by(email=email).first()
    except (NoResultFound, InvalidRequestError, SQLAlchemyError) as e:
        err_msg = f"Error finding user by email: {str(e)}"
        app.logger.error(err_msg)
        return None
    return user


def find_user_by_token(token: str) -> Optional[User]:
    """

    Find user by token.

    Args:
        token (str): The token string used to search for the user.

    Returns:
        User: The user object found by the token, or None if not found.

    """
    try:
        user = User.query.filter_by(token=token).first()
    except (NoResultFound, InvalidRequestError, SQLAlchemyError) as e:
        err_msg = f"Error finding user by token: {str(e)}"
        app.logger.error(err_msg)
        return None
    return user


def find_user_by_id(user_id: int) -> User:
    with app.app_context():
        user_ = db.session.query(User).filter(User.id == user_id).one()
        db.session.flush()
        db.session.expunge_all()
        db.session.close()
        return user_


def save_new_user(user_: User) -> Tuple[bool, str, Optional[User]]:
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
        potential_user_ = find_user_by_username(username=user_.username)
        if potential_user_ is not None:
            return False, "Username taken", None

        potential_user_ = find_user_by_email(email=user_.email)
        if potential_user_ is not None:
            return False, "Email taken", None

        db.session.add(user_)
        db.session.commit()

        post_user_add_hook(new_user=user_)
        return True, "success", user_





# --- Inventories ---

def find_inventory(inventory_id: int) -> Optional[Inventory]:
    """
    Method to find an inventory based on the inventory ID.

    Parameters:
    - inventory_id (int): The ID of the inventory to find.

    Returns:
    - Optional[Inventory]: The found inventory object, or None if no inventory with the given ID is found.
    """

    try:
        inventory_ = Inventory.query.filter_by(id=inventory_id).first()
    except (NoResultFound, InvalidRequestError, SQLAlchemyError) as e:
        err_msg = f"Error finding inventory: {str(e)}"
        app.logger.error(err_msg)
        return None
    return inventory_


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


def find_inventory_by_access_token(access_token: str) -> Optional[Inventory]:
    """
    Finds an inventory by the given access token.

    Args:
        access_token (str): The access token to search the inventory by.

    Returns:
        Optional[Inventory]: The inventory found by the access token, or None if not found.

    """
    if access_token is None:
        err_msg = f"Error finding inventory by access token: access token is None"
        app.logger.error(err_msg)
        return None

    inventory_ = Inventory.query.filter_by(token=access_token).first()
    if inventory_ is not None:
        return inventory_
    else:
        return None


def find_inventory_by_slug(inventory_slug: str, inventory_owner_id: int = None,
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
    if not isinstance(inventory_slug, str):
        err_msg = f"Error finding inventory by slug: supplied inventory_slug is not a string"
        app.logger.error(err_msg)
        return None, None

    if not isinstance(inventory_owner_id, int):
        err_msg = f"Error finding inventory by slug: supplied inventory_owner_id is not an integer"
        app.logger.error(err_msg)
        return None, None

    # if not isinstance(viewing_user_id, int):
    #     err_msg = f"Error finding inventory by slug: supplied viewing_user_id is not an integer"
    #     app.logger.error(err_msg)
    #     return None, None

    user_is_logged_in = (viewing_user_id is not None)

    # do some new code here to fix
    # try to find a user inventory for the user and the inventory id
    inventory_ = Inventory.query.filter(Inventory.slug == inventory_slug).one_or_none()
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
        print('An error occurred:', ex)
        return []





def send_inventory_invite(recipient_username: str, text_body: str, html_body: str):
    recipient_user_ = find_user_by_username(username=recipient_username)
    if recipient_user_ is not None:
        send_email("New user registration", recipients=[recipient_user_.email], text_body=text_body, html_body=html_body)


def confirm_inventory_invite_():
    pass


def backup_to_json():
    with app.app_context():
        backup_json = {}



def create_inventory(name: str, description: str, slug: str, inventory_type: int, to_user, access_level):
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
    inventory_token = uuid.uuid4().hex
    new_inventory = Inventory(name=name, description=description, token=inventory_token,
                              slug=slug, owner=to_user, type=inventory_type, access_level=access_level)
    db.session.expire_on_commit = False
    db.session.add(new_inventory)
    db.session.flush()
    new_inventory_id = new_inventory.id
    to_user.inventories.append(new_inventory)
    db.session.commit()
    db.session.expunge_all()
    return new_inventory, new_inventory_id


def add_user_inventory(name: str, description: str, inventory_type: int, slug: str = None,
                       access_level: int = 1, user_id: int = None) -> Tuple[Optional[dict], str]:
    """
    Add a new inventory to a user.

    Args:
        name (str): The name of the inventory.
        description (str): The description of the inventory.
        inventory_type (int): The type of the inventory.
        access_level (int): The access level of the inventory.
        user_id (int): The ID of the user.

    Returns:
        Tuple[Optional[dict], str]: A tuple containing the result dictionary and a status message. The result dictionary
        contains the ID, name, description, slug, and access_level of the new inventory. The status message indicates the
        success or failure of the operation.

        If the name is empty, returns (None, "Name cannot be empty").
        If the user is not found, returns (None, "User not found").
        If an error occurs while adding the inventory, returns (None, "Could not add inventory").
        If the inventory is successfully added, returns the result dictionary and "success".
    """
    if name == "":
        return None, "Name cannot be empty"

    if slug is None:
        slug = slugify(name)

    with app.app_context():
        try:
            # add it initially private
            to_user = User.query.filter_by(id=user_id).first()
            if to_user is None:
                return None, "User not found"

            new_inventory, new_inventory_id = create_inventory(name=name, description=description,
                                                               inventory_type=inventory_type,
                                                               slug=slug, to_user=to_user, access_level=access_level)

            result_return_value = {
                "id": new_inventory_id,
                "name": name,
                "description": description,
                "slug": slug,
                "type": inventory_type,
                "access_level": access_level
            }

            return result_return_value, "success"

        except SQLAlchemyError as error:
            return None, "Could not add inventory"


def get_user_default_inventory(user_id: int):
    with app.app_context():
        # Find user default inventory
        user_ = find_user_by_id(user_id=user_id)
        user_default_inventory_ = Inventory.query.filter_by(name=f"__default__{user_.username}").filter_by().first()
        return user_default_inventory_



def delete_inventory_by_id(inventory_ids, user_id: int):
    """
    If the User has Items within the Inventory - re-link Items to Users default Inventory via the ItemInventory table
    Delete the UserInventory for the user
    If there are no more UserInventory links to the Inventory - delete the Inventory
    """

    if not isinstance(inventory_ids, list):
        inventory_ids = [inventory_ids]

    with app.app_context():

        stmt = select(UserInventory).join(User)\
            .where(UserInventory.user_id == user_id) \
            .where(UserInventory.inventory_id.in_(inventory_ids))
        user_inventories_ = db.session.execute(stmt).all()

        for user_inventory_ in user_inventories_:  # type: UserInventory

            if user_inventory_ is not None:
                user_inventory_ = user_inventory_[0]

                if user_inventory_.access_level !=0:
                    db.session.delete(user_inventory_)
                    db.session.commit()
                    return

                # Find out if any other users point to this inventory, if not delete it
                inventory_id_to_delete = user_inventory_.inventory_id

                # Get the current user's default inventory
                user_default_inventory_ = get_user_default_inventory(user_id=user_id)

                inv_items_ = InventoryItem.query.filter_by(inventory_id=inventory_id_to_delete).all()
                for row in inv_items_:
                    # Add the items that are in this inventory to the user's default
                    row.inventory_id = user_default_inventory_.id

                # Delete the UserInventory for the user
                db.session.delete(user_inventory_)
                db.session.commit()

                users_invs_ = UserInventory.query.filter_by(inventory_id=inventory_id_to_delete).all()
                if len(users_invs_) == 0:
                    # remove the actual inventory
                    inv_ = Inventory.query.filter_by(id=inventory_id_to_delete).first()
                    if inv_ is not None:
                        db.session.delete(inv_)
                        db.session.commit()


def delete_notification_by_id(notification_id: int, user: User):
    with app.app_context():
        notification_ = Notification.query.filter_by(id=notification_id).one_or_none()

        if notification_ is not None:
            db.session.delete(notification_)
           # user.notifications.remove(notification_)
            db.session.commit()
            return {
                "success": True,
                "message": f"Removed notification with ID {notification_.id} from user @{user.username}"
            }

        return {
            "success": False,
            "message": f"No notification with ID {notification_id} for user @{user.username}"
        }


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


def delete_itemtypes_from_db(itemtype_ids, user_id: int) -> (bool, str):
    with app.app_context():
        if not isinstance(itemtype_ids, list):
            itemtype_ids = [itemtype_ids]

        user_none_type_ = ItemType.query.filter_by(user_id=user_id).filter_by(name=_NONE_).first()

        stmt = select(ItemType).join(User) \
            .where(ItemType.user_id == user_id) \
            .where(ItemType.id.in_(itemtype_ids))
        itemtypes_ = db.session.execute(stmt).all()

        for itemtype_ in itemtypes_:
            itemtype_ = itemtype_[0]

            d = Item.query.filter_by(user_id=user_id).filter_by(item_type=itemtype_.id).all()
            for row in d:
                row.item_type = user_none_type_.id

            db.session.commit()

            db.session.delete(itemtype_)
            db.session.commit()


def get_user_item_count(user_id: int):
    with app.app_context():
        item_count_ = db.session.query(Item).filter(Item.user_id == user_id).count()
        return item_count_


def _find_field_by_name(field_name: str):
    field_slug = slugify(field_name)
    field_ = Field.query.filter(Field.slug == field_slug).one_or_none()
    return field_


def _search_by_field_value(field_id: int, user_id: int, query: str):
    looking_for = '%{0}%'.format(query)
    with app.app_context():
        items_ = db.session.query(Item) \
            .join(ItemField, ItemField.item_id == Item.id) \
            .filter(ItemField.field_id == field_id) \
            .filter(ItemField.user_id == user_id) \
            .filter(ItemField.value.ilike(looking_for)).all()

        return items_


def search_items(query: str, user_id: int):
    items_arr = []
    with app.app_context():

        # see if there is a search modifier
        if ':' in query:
            search_modifier = query.split(':')[0]
            query = query.split(':')[1]

            if search_modifier.lower() == 'location':
                locations_ = Location.query\
                    .filter(Location.user_id == user_id)\
                    .filter(Location.name.like(query)).all()

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

            elif search_modifier.lower() == 'tags':
                query = query.split(",")
                q_ = Item.query

                any_tags_found = False
                for tag_ in query:
                    tag_ = tag_.strip()
                    tag_ = tag_.replace(" ", "@#$")
                    t_ = find_tag(tag=tag_)

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
                field_ = _find_field_by_name(field_name=search_modifier)
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


def find_item(logged_in_user_id, request_user_id, item_id, item_slug):
    d = db.session.query(Item, ItemType.name, Location.name,
                         UserInventory, InventoryItem.access_level) \
        .join(InventoryItem, InventoryItem.item_id == Item.id) \
        .join(Inventory, Inventory.id == InventoryItem.inventory_id) \
        .join(ItemType, ItemType.id == Item.item_type) \
        .join(Location, Location.id == Item.location_id)

    if logged_in_user_id is None:
        if request_user_id is None:
            d = d.filter(InventoryItem.access_level == __PUBLIC__)
        else:
            d = d.filter(Item.user_id == request_user_id)
            d = d.filter(InventoryItem.access_level == __PUBLIC__)

    else:
        if request_user_id is None:
            d = d.filter(Item.user_id == logged_in_user_id)
        else:
            if request_user_id != logged_in_user_id:
                d = d.filter(Item.user_id == request_user_id)
                d = d.filter(InventoryItem.access_level == __PUBLIC__)
            else:
                d = d.filter(Item.user_id == request_user_id)

    if item_id is not None:
        d = d.filter(Item.id == item_id)

    if item_slug is not None:
        d = d.filter(Item.slug == item_slug)

    return d.first()


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
            tag_ = tag_.replace(" ", "@#$")
            t_ = find_tag(tag=tag_)

            if t_ is not None:
                query_ = query_.filter(Item.tags.contains(t_))

    return query_





















def regenerate_inventory_token(user_id, inventory_id, new_token):
    with app.app_context():
        query = db.session.query(UserInventory, Inventory).join(Inventory)\
                .filter(UserInventory.user_id == user_id)\
                .filter(UserInventory.inventory_id == inventory_id)

        results = query.one_or_none()
        if results is not None:
            user_inventory_, inventory_ = results
            inventory_.token = new_token
            db.session.commit()

            return new_token

        return None









def find_all_my_items(logged_in_user: User):
    with app.app_context():
        query = db.session.query(Item)
        query = query.filter(Item.user_id == logged_in_user.id)
        results_ = query.all()
        return results_


def _find_my_items_using_select(logged_in_user: User, inventory_id, query_params):
    with app.app_context():
        if inventory_id is not None and inventory_id != '':
            d = select(Item, ItemType, Location, InventoryItem, UserInventory) \
            .join(ItemType, ItemType.id == Item.item_type) \
            .join(Location, Location.id == Item.location_id) \
            .join(InventoryItem, InventoryItem.item_id == Item.id) \
            .where(InventoryItem.inventory_id == inventory_id)

            start = query_params.get("start", 0)
            length = query_params.get("length", 50)

            page = int((int(start) / int(length)) + 1)
            # page = query_params.get("page", 1)
            per_page = int(query_params.get("length", 50))

            page_data = db.paginate(d, page=page, per_page=per_page)

            d = 3


def _find_my_items(logged_in_user: User, inventory_id, query_params):
    with app.app_context():
        if inventory_id is not None and inventory_id != '':
            query = db.session.query(Item, ItemType.name, Location.name, InventoryItem.access_level, InventoryItem.is_link, UserInventory) \
                .join(ItemType, ItemType.id == Item.item_type) \
                .join(Location, Location.id == Item.location_id)

            query = query.join(InventoryItem, InventoryItem.item_id == Item.id)
            query = query.join(Inventory, Inventory.id == InventoryItem.inventory_id)
            query = query.filter(InventoryItem.inventory_id == inventory_id)

            query = query.filter(UserInventory.inventory_id == inventory_id)
            query = query.filter(UserInventory.user_id == logged_in_user.id)
        else:
            query = db.session.query(Item, ItemType.name, Location.name, InventoryItem.access_level, InventoryItem.is_link) \
                .join(ItemType, ItemType.id == Item.item_type) \
                .join(Location, Location.id == Item.location_id)

            query = query.join(InventoryItem, InventoryItem.item_id == Item.id)

        query = query.filter(Item.user_id == logged_in_user.id)

        query = _find_query_parameters(query_=query, query_params=query_params)

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

        page = int((int(start) / int(length)) )
        # page = query_params.get("page", 1)
        per_page = int(query_params.get("length", 50))

        if length is not None:
            query = query.limit(per_page)
        if page is not None:
            query = query.offset(page * per_page)

        results_ = query.all()

        return results_


"""
inventory access
0 - owner
1 - 
"""


def _find_someone_elses_items_loggedin(logged_in_user: User, request_user_id, inventory_id, query_params):
    with app.app_context():

        query = db.session.query(Item, ItemType.name, Location.name, InventoryItem.access_level, InventoryItem.is_link) \
            .join(ItemType, ItemType.id == Item.item_type) \
            .join(Location, Location.id == Item.location_id)

        query = query.join(InventoryItem, InventoryItem.item_id == Item.id)
        query = query.join(Inventory, Inventory.id == InventoryItem.inventory_id)
        query = query.filter(InventoryItem.inventory_id == inventory_id)

        query = query.filter(and_(
            UserInventory.user_id == logged_in_user.id,
            UserInventory.inventory_id == inventory_id))

        query = query.filter(Item.user_id == request_user_id)
        #query = query.filter(InventoryItem.access_level == 2)

        query = _find_query_parameters(query_=query, query_params=query_params)

        results_ = query.all()

        return results_


def _find_someone_elses_items_notloggedin(request_user_id, inventory_id, query_params):
    with app.app_context():

        query = db.session.query(Item, ItemType.name, Location.name, InventoryItem.access_level, InventoryItem.is_link) \
            .join(ItemType, ItemType.id == Item.item_type) \
            .join(Location, Location.id == Item.location_id)

        query = query.join(InventoryItem, InventoryItem.item_id == Item.id)
        query = query.join(Inventory, Inventory.id == InventoryItem.inventory_id)
        query = query.filter(InventoryItem.inventory_id == inventory_id)

        query = query.filter(and_(
            #UserInventory.user_id == logged_in_user.id,
            UserInventory.inventory_id == inventory_id))

        query = query.filter(Item.user_id == request_user_id)
        #query = query.filter(InventoryItem.access_level == 2)

        query = _find_query_parameters(query_=query, query_params=query_params)

        results_ = query.all()

        return results_


def find_items_new(logged_in_user=None, requested_username=None, inventory_id=None, query_params=None):
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
                requested_user = find_user_by_username(username=requested_username)
        else:
            requested_user = find_user_by_username(username=requested_username)

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


def get_all_item_ids_in_inventory(user_id: int, inventory_id: int):
    with app.app_context():
        stmt = select(Item.id).join(InventoryItem, InventoryItem.item_id == Item.id
                                 ).where(user_id == Item.user_id
                                         ).where(InventoryItem.inventory_id == inventory_id)

        results_ = db.session.execute(stmt).all()
        return [x[0] for x in results_]


def count_all_item_ids_in_inventory(user_id: int, inventory_id: int) -> int:
    with app.app_context():
        stmt = select(Item.id).join(InventoryItem, InventoryItem.item_id == Item.id
                                 ).where(user_id == Item.user_id
                                         ).where(InventoryItem.inventory_id == inventory_id)

        results_ = db.session.execute(stmt).all()
        return len(results_)


def delete_all_items_in_inventory(user_id: int, inventory_id: int):
    with app.app_context():
        query = db.session.query(Item, InventoryItem) \
            .join(InventoryItem, InventoryItem.item_id == Item.id)

        query = query.filter(InventoryItem.inventory_id == inventory_id)
        query = query.filter(Item.user_id == user_id)

        results_ = query.all()
        return results_


def find_items(inventory_id=None, item_type=None,
               item_tags=None, item_specific_location=None,
               item_location=None, logged_in_user=None,
               request_user=None):
    if logged_in_user is None:
        logged_in_user_id = None
    else:
        logged_in_user_id = logged_in_user.id

    if request_user is None:
        request_user_id = None
    else:
        request_user_id = request_user.id

    with app.app_context():

        if inventory_id is not None and inventory_id != '':
            d = db.session.query(Item, ItemType.name, Location.name, InventoryItem.access_level, UserInventory) \
                .join(ItemType, ItemType.id == Item.item_type) \
                .join(Location, Location.id == Item.location_id)

            d = d.join(InventoryItem, InventoryItem.item_id == Item.id)
            d = d.join(Inventory, Inventory.id == InventoryItem.inventory_id)
            d = d.filter(InventoryItem.inventory_id == inventory_id)
        else:
            d = db.session.query(Item, ItemType.name, Location.name, InventoryItem.access_level) \
                .join(ItemType, ItemType.id == Item.item_type) \
                .join(Location, Location.id == Item.location_id)

            d = d.join(InventoryItem, InventoryItem.item_id == Item.id)

        if logged_in_user_id is None:
            if request_user_id is None:
                d = d.filter(InventoryItem.access_level == 2)
            else:
                d = d.filter(Item.user_id == request_user_id)
                d = d.filter(InventoryItem.access_level == 2)

        else:
            if request_user_id is None:
                d = d.filter(Item.user_id == logged_in_user_id)
            else:
                if request_user_id != logged_in_user_id:
                    d = d.filter(Item.user_id == request_user_id)
                    d = d.filter(InventoryItem.access_level == 2)
                else:
                    d = d.filter(Item.user_id == request_user_id)

        d = _find_query_parameters(d, item_type, item_location, item_specific_location, item_tags)

    sd = d.all()

    return sd


def find_items_orig(inventory_id=None, item_type=None,
               item_tags=None, item_specific_location=None,
               item_location=None, logged_in_user=None,
               request_user=None):
    if logged_in_user is None:
        logged_in_user_id = None
    else:
        logged_in_user_id = logged_in_user.id

    if request_user is None:
        request_user_id = None
    else:
        request_user_id = request_user.id

    with app.app_context():

        if inventory_id is not None and inventory_id != '':
            d = db.session.query(Item, ItemType.name, Location.name, InventoryItem.access_level) \
                .join(ItemType, ItemType.id == Item.item_type) \
                .join(Location, Location.id == Item.location_id)

            d = d.join(InventoryItem, InventoryItem.item_id == Item.id)
            d = d.join(Inventory, Inventory.id == InventoryItem.inventory_id)
            d = d.filter(InventoryItem.inventory_id == inventory_id)
        else:
            d = db.session.query(Item, ItemType.name, Location.name, InventoryItem.access_level) \
                .join(ItemType, ItemType.id == Item.item_type) \
                .join(Location, Location.id == Item.location_id)

            d = d.join(InventoryItem, InventoryItem.item_id == Item.id)

        if logged_in_user_id is None:
            if request_user_id is None:
                d = d.filter(InventoryItem.access_level == 2)
            else:
                d = d.filter(Item.user_id == request_user_id)
                d = d.filter(InventoryItem.access_level == 2)

        else:
            if request_user_id is None:
                d = d.filter(Item.user_id == logged_in_user_id)
            else:
                if request_user_id != logged_in_user_id:
                    d = d.filter(Item.user_id == request_user_id)
                    d = d.filter(InventoryItem.access_level == 2)
                else:
                    d = d.filter(Item.user_id == request_user_id)

        if item_type is not None and item_type != '':
            d = d.filter(Item.item_type == item_type)

        if item_location is not None and item_location != '':
            d = d.filter(Location.id == item_location)

        if item_specific_location is not None and item_specific_location != '':
            d = d.filter(Item.specific_location == item_specific_location)

        if item_tags is not None and item_tags != "":
            item_tags = item_tags.split(",")

            for tag_ in item_tags:
                tag_ = tag_.strip()
                tag_ = tag_.replace(" ", "@#$")
                t_ = find_tag(tag=tag_)

                if t_ is not None:
                    d = d.filter(Item.tags.contains(t_))

    sd = d.all()

    return sd


def change_item_access_level(item_ids: int, access_level: int, user_id: int):
    if not isinstance(item_ids, list):
        item_ids = [item_ids]

    with app.app_context():
        d = db.session.query(Item, InventoryItem) \
            .join(InventoryItem, InventoryItem.item_id == Item.id) \
            .join(Inventory, Inventory.id == InventoryItem.inventory_id) \
            .join(UserInventory, UserInventory.user_id == Item.user_id) \
            .filter(Item.id.in_(item_ids)) \
            .filter(Item.user_id == user_id)

        results_ = d.all()
        for item_, inventory_item_ in results_:
            inventory_item_.access_level = access_level

        db.session.commit()





def get_all_user_locations(user_id: int) -> Optional[list[Location]]:
    user_locations_ = Location.query.filter_by(user_id=user_id).all()
    return user_locations_


def get_all_user_tags(user_id: int) -> list[Tag]:
    with app.app_context():
        res_ = db.session.query(Tag).filter(Tag.user_id == user_id).all()
    return res_


def get_all_item_types() -> list:
    item_types_ = ItemType.query.all()
    return item_types_


def get_item_types(item_id=None, user_id=None) -> list:
    item_types_ = ItemType.query
    if item_id is not None:
        item_types_ = item_types_.filter_by(item_id=item_id)

    if user_id is not None:
        item_types_ = item_types_.filter_by(user_id=user_id)
    return item_types_.all()


def add_new_user_itemtype(name: str, user_id: int):
    with app.app_context():
        item_type_ = find_type_by_text(type_text=name, user_id=user_id)

        if item_type_ is None:
            new_item_type_ = ItemType(name=name.lower(), user_id=user_id)
            db.session.add(new_item_type_)
            db.session.commit()





def find_type_by_text(type_text: str, user_id: int = None) -> Union[dict, None]:
    with app.app_context():

        if user_id is None:
            item_type_ = ItemType.query.filter_by(name=type_text.lower().strip()).one_or_none()
        else:
            item_type_ = ItemType.query.filter_by(name=type_text.lower().strip()) \
                .filter_by(user_id=user_id).one_or_none()

        if item_type_ is not None:
            return {"id": item_type_.id, "name": item_type_.name, "user_id": item_type_.user_id}

        return None


def get_all_itemtypes_for_user(user_id: int, string_list=True) -> list:
    if string_list:
        stmt = select(ItemType.name) \
            .where(ItemType.user_id == user_id)
    else:
        stmt = select(ItemType) \
            .where(ItemType.user_id == user_id)

    res = db.session.execute(stmt).all()

    ret_data = []
    if res is not None:
        for row in res:
            ret_data.append(row[0])

    return ret_data








def activate_user_in_db(user_id: int):
    with app.app_context():
        user_ = db.session.query(User).filter(User.id == user_id).one()
        user_.activated = True
        db.session.commit()


def find_item(item_id: int, user_id: int = None) -> Item:
    if user_id is None:
        item_ = Item.query.filter_by(id=item_id).first()
    else:
        item_ = Item.query.filter_by(id=item_id).filter_by(user_id=user_id).first()
    return item_


def find_item_by_slug(item_slug: int, user_id: int = None) -> Item:
    if user_id is None:
        item_ = Item.query.filter_by(slug=item_slug).first()
    else:
        item_ = Item.query.filter_by(slug=item_slug).filter_by(user_id=user_id).first()
    return item_


def find_tag(tag: str) -> User:
    tag_ = Tag.query.filter_by(tag=tag).first()
    return tag_


def find_location_by_id(location_id: int) -> Union[dict, None]:
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


def find_template(template_id: int) -> Location:
    template_ = FieldTemplate.query.filter_by(id=template_id).first()
    return template_


def find_location_by_name(location_name: str) -> Location:
    location_ = Location.query.filter_by(name=location_name).first()
    return location_










def unrelate_items_by_id(item1_id: int, item2_id: int)-> (bool, str):
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
                db.session.commit()
                item2_.related_items.remove(item1_)
                db.session.commit()
            except SQLAlchemyError:
                db.session.rollback()
                return False, f"Could not unrelate items with ids {item1_id} and {item2_id}"
        else:
            return False, f"Items with ids {item1_id} and {item2_id} are not related"

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


# def add_item_inventory(item, inventory): XXXX
#     with app.app_context():
#         stmt = select(Item).where(Item.id == item)
#         item_ = db.session.execute(stmt).first()
#
#         stmt = select(Inventory).where(Inventory.id == inventory)
#         inventory_ = db.session.execute(stmt).first()
#
#         inventory_[0].items.append(item_[0])
#         db.session.commit()


def set_item_main_image(main_image_url: str, item_id: int, user: User):
    """
    Sets the main image URL for an item.

    Parameters:
    - main_image_url (str): The URL of the main image for the item.
    - item_id (int): The ID of the item.
    - user (User): The user object associated with the item.

    Returns:
    - bool: Returns True if the main image URL is successfully set for the item, False otherwise.
    """
    if main_image_url is None or main_image_url == "":
        return False
    if item_id is None:
        return False
    if user is None:
        return False

    with app.app_context():
        item_ = find_item(item_id=item_id, user_id=user.id)

        if item_ is None:
            app.logger.error(f'No item with id {item_id} found for user id {user.id}')
            return False

        item_.main_image = main_image_url

        try:
            db.session.commit()
            return True
        except SQLAlchemyError:
            db.session.rollback()
            return False


def get_all_images(user_id: int = None) -> list[Image]:
    with app.app_context():
        images_ = Image.query.all()
        itemimages_ = ItemImage.query.all()
        return images_, itemimages_


def add_images_to_item(item_id: int, filenames: list[str], user: User)-> (bool, str):
    """
    Add images to an item.

    :param item_id: The ID of the item to add images to. (int)
    :param filenames: A list of filenames for the images to add. (list[str])
    :param user: The user who is adding the images. (User)

    :return: A tuple indicating the success of adding the images and a message. (bool, str)
    """
    if item_id is None:
        return False, "Item ID cannot be None"
    if filenames is None or len(filenames) == 0:
        return False, "No filenames provided"
    if user is None:
        return False, "User cannot be None"

    with app.app_context():
        item_ = find_item(item_id=item_id)
        if item_ is None:
            return False, f"No item with id {item_id} found for user {user.username}"

        for file in filenames:
            new_image = Image(image_filename=file, user_id=user.id)
            item_.images.append(new_image)

        item_.main_image = item_.images[0].image_filename

        try:
            db.session.commit()
            return True
        except SQLAlchemyError:
            db.session.rollback()
            return False


def find_image_by_filename(image_filename: str, user: User) -> Optional[Image]:
    """
    Args:
        image_filename: A string representing the filename of the image.
        user: An instance of the User class representing the user.

    Returns:
        An optional instance of the Image class if found, otherwise None.

    """
    if image_filename is None:
        return None
    if user is None:
        return None

    try:
        image_ = Image.query.filter_by(image_filename=image_filename).filter_by(user_id=user.id).first()
    except SQLAlchemyError:
        db.session.rollback()
        return None
    return image_





def delete_images_from_item(item_id: int, image_ids, user: User) -> (bool, str):

    if item_id is None:
        return False, "Item ID cannot be None"

    if image_ids is None or len(image_ids) == 0:
        return False, "No image IDs provided"

    with app.app_context():
        item_ = find_item(item_id=item_id)
        if item_ is None:
            return False, f"No item with id {item_id} found for user {user.username}"

        for image_id in image_ids:
            image_ = find_image_by_filename(image_filename=image_id, user=user)
            if image_ is None:
                return False, f"No image with id {image_id} found for user {user.username}"

            if image_ in item_.images:
                if image_.image_filename == item_.main_image:
                    item_.main_image = None
                item_.images.remove(image_)

                try:
                    os.remove(os.path.join(app.root_path, app.config['USER_IMAGES_BASE_PATH'], image_.image_filename))
                except OSError as er:
                    return False, f"Could not delete image with id {image_id} for user {user.username}"

        if item_.main_image is None:
            if len(item_.images) == 0:
                item_.main_image = None
            else:
                item_.main_image = item_.images[0].image_filename

        try:
            db.session.commit()
            return True, "Images deleted successfully"
        except SQLAlchemyError:
            db.session.rollback()
            return False, "Could not delete images"


def update_template_by_id(template_data: dict, user: User) -> (bool, str):
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

    with app.app_context():
        template_id = template_data['id']

        template_ = FieldTemplate.query.filter_by(id=template_id).filter_by(user_id=user.id).one_or_none()
        if template_ is None:
            return False, f"No template with id {template_id} found for user {user.username}"

        template_.name = template_data['name']
        template_.fields = template_data['fields']

        try:
            db.session.commit()
            return True, "Template updated successfully"
        except SQLAlchemyError:
            db.session.rollback()
            return False, "Could not update template"


def update_location_by_id(location_data: dict, user: User) -> (bool, str):
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

        location_ = Location.query.filter_by(id=location_id).filter_by(user_id=user.id)
        if location_ is None:
            msg = f"No location with id {location_id} found for user {user.username}"
            app.logger.error(msg)
            return False, msg

        location_.name = location_data['name']
        location_.description = location_data['description']

        try:
            db.session.commit()
            return True, "Location updated successfully"
        except SQLAlchemyError:
            db.session.rollback()
            msg = f"Could not update location with id {location_id} for user {user.username}"
            app.logger.error(msg)
            return False, msg



def _populate_item_fields(item_result: dict, item_data: dict, user: User):
    item_result[0].name = item_data['name']
    item_result[0].slug = f"{str(item_result[0].id)}-{slugify(item_data['name'])}"
    item_result[0].description = item_data['description']
    item_result[0].quantity = item_data['item_quantity']
    item_result[0].location_id = item_data['item_location']
    item_result[0].specific_location = item_data['item_specific_location']
    item_result[0].tags = _parse_tags(item_data['item_tags'], user)


def _parse_tags(item_tags: List[str], user: User) -> List[Tag]:
    """

    Parse Tags

    This method is responsible for parsing a list of tags and returning a list of corresponding Tag objects.

    Parameters:
    - item_tags (List[str]): The list of tags to parse.
    - user (User): The User object associated with the tags.

    Returns:
    - tags_objects (List[Tag]): The list of Tag objects corresponding to the parsed tags.

    """
    tags_objects = []
    if not isinstance(item_tags, list):
        item_tags = item_tags.strip().replace(" ", "@#$").split(",")

    for tag in item_tags:
        instance = db.session.query(Tag).filter_by(tag=tag).one_or_none()
        if not instance:
            instance = Tag(tag=tag, user_id=user.id)
        tags_objects.append(instance)

    return tags_objects


def _get_selected_item(user_id: int, item_id: int):
    select_statement = select(Item) \
            .join(User) \
            .where(User.id == user_id) \
            .where(Item.id == item_id)
    return db.session.execute(select_statement).first()


def _get_itemtype_id(item_data: dict, user: User):
    """

    Method: _get_itemtype_id

    Parameters:
    - item_data (dict): A dictionary containing data about the item.
    - user (User): An instance of the User class representing the user.

    Description:
    This method is used to get the ID of an item type based on the provided item data and user.

    Returns:
    - int: The ID of the item type. If the item type does not exist, it creates a new one and returns its ID.

    """
    if 'item_type' not in item_data:
        return None

    if item_data['item_type'] is None:
        return None

    if item_data['item_type'] == "":
        return None

    if user is None:
        return None

    if not isinstance(item_data, dict):
        return None

    select_itemtype = select(ItemType).where(ItemType.name == item_data['item_type'])
    itemtype_result = db.session.execute(select_itemtype).first()
    if itemtype_result is None:
        new_itemtype_ = ItemType(name=item_data['item_type'], user_id=user.id)
        db.session.add(new_itemtype_)
        db.session.flush()
        return new_itemtype_.id
    return itemtype_result[0].id


def update_item_by_id(item_data: dict, item_id: int, user: User) -> (bool, str):
    if item_id is None:
        return False, "Item ID cannot be None"

    if user is None:
        return False, "User cannot be None"

    with app.app_context():
        db.session.expire_on_commit = False

        item_result = _get_selected_item(user.id, item_id)
        _populate_item_fields(item_result, item_data, user)

        item_result[0].item_type = _get_itemtype_id(item_data, user)

        db.session.commit()

        return item_result[0].slug


def delete_item_images_by_item_id(item_id: int, user_id: str):
    """

    Delete Item Images by Item ID

    Removes all images associated with a given item ID. Only authenticated users are allowed to use this method.

    Parameters:
    - item_id (int): The ID of the item whose images need to be deleted.
    - user (User): The authenticated user.

    """
    with app.app_context():
        item_ = find_item(item_id=item_id, user_id=user_id)
        if item_ is not None:
            for image_ in item_.images:
                try:
                    os.remove(os.path.join(app.root_path, app.config['USER_IMAGES_BASE_PATH'], user_id,
                                           image_.image_filename))
                except OSError as er:
                    pass

            item_.images = []
            item_.main_image = None
            db.session.commit()


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
                return False, f"Error deleting image file: {image_.image_filename}"

        item_.images = []
        item_.main_image = None
        try:
            db.session.commit()
            return True, "Item images deleted successfully"
        except SQLAlchemyError:
            db.session.rollback()
            return False, "Error deleting item images"


def get_related_items(item_id: int):
    if item_id is None:
        app.logger.error("Item cannot be None")
        return []
    return Relateditems.query.filter(
        or_(Relateditems.item_id == item_id, Relateditems.related_item_id == item_id)).all()


def get_items_to_delete(user_id: int, item_ids: list):
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

    stmt = select(Item).where(user_id == Item.user_id, Item.id.in_(item_ids))
    return db.session.execute(stmt).all()


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
            item_ids = get_all_item_ids_in_inventory(user_id=user_id, inventory_id=inventory_id)
            items_to_delete = get_items_to_delete(user_id=user_id, item_ids=item_ids)
        else:
            items_to_delete = get_items_to_delete(user_id=user_id, item_ids=item_ids)

        number_items_deleted = 0

        for item_ in items_to_delete:
            item_ = item_[0]
            if item_ is not None:
                # check if this item is in multiple directories
                # if so, only remove the link to this item from the current inventory
                if inventory_id is not None:

                    for itinv in item_.inventories:
                        if itinv.id == inventory_id:
                            item_.inventories.remove(itinv)

                    try:
                        db.session.commit()
                    except SQLAlchemyError as e:
                        d = 3

                    number_items_deleted += 1

                # remove related item relationships
                related_items = get_related_items(item_.id)
                for related_item in related_items:
                    db.session.delete(related_item)

                # remove item images
                delete_item_images(item_, user_id)

                db.session.delete(item_)
                number_items_deleted += 1

        db.session.commit()
        try:
            db.session.commit()
            return number_items_deleted
        except SQLAlchemyError as e:
            db.session.rollback()

    return number_items_deleted


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

    if specific_location is None:
        return False, "Specific location cannot be None"

    with app.app_context():
        stmt = select(Item).where(Item.user_id == user.id).where(Item.id.in_(item_ids))
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
                user_default_inventory = get_user_default_inventory(user_id=user.id)
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

                new_ = add_item_to_inventory(item_name=item_.name, item_desc=item_.description,
                                             item_type=item_.item_type, item_quantity=item_.quantity,
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


def move_items(item_ids: list, user: User, inventory_id: int) -> dict:
    """
        link - just add new line in ItemInventory
        move - change inventory id in ItemInventory
        copy - duplicate item, add new line in ItemInventory
    """

    with app.app_context():

        try:
            if inventory_id == -1:
                user_default_inventory = get_user_default_inventory(user_id=user.id)
                inventory_id = user_default_inventory.id

            stmt = select(Item, InventoryItem) \
                .join(InventoryItem, InventoryItem.item_id == Item.id) \
                .join(User) \
                .where(Item.user_id == user.id) \
                .where(Item.id.in_(item_ids))
            results_ = db.session.execute(stmt).all()

            for item_, inventory_item_ in results_:
                inventory_item_.inventory_id = inventory_id

            db.session.commit()
            return {"status": "success", "count": len(results_)}

        except Exception as e:
            return {"status": "error", "count": 0}


def link_items(item_ids: list, user: User, inventory_id: int):
    with app.app_context():
        try:
            if inventory_id == -1:
                user_default_inventory = get_user_default_inventory(user_id=user.id)
                inventory_id = user_default_inventory.id

            stmt = db.session.query(Item, InventoryItem) \
                .join(InventoryItem, InventoryItem.item_id == Item.id) \
                .join(User) \
                .where(Item.user_id == user.id) \
                .where(Item.id.in_(item_ids))
            results_ = db.session.execute(stmt).all()

            for item_, inventory_item_ in results_:
                if inventory_item_.inventory_id != inventory_id:
                    new_inventory_item_ = InventoryItem(inventory_id=inventory_id, item_id=item_.id,
                                                        access_level=inventory_item_.access_level,
                                                        is_link=True)

                    db.session.add(new_inventory_item_)

            db.session.commit()

            return {"status": "success", "count": len(results_)}

        except Exception as e:
            return {"status": "error", "count": 0}


def delete_items_from_inventory(item_ids: list, inventory_id: int, user: User):
    if item_ids is None or len(item_ids) == 0:
        return 0

    with app.app_context():
        stmt = select(UserInventory, Inventory).join(Inventory).join(User).where(User.id == user.id).where(
            Inventory.id == inventory_id)
        user_inventory_, inventory_ = db.session.execute(stmt).first()

        number_items_deleted = 0

        for item_id in item_ids:
            item_ = find_item(item_id=item_id, user_id=user.id)
            if item_ is not None:
                inventory_.items.remove(item_)
                db.session.delete(item_)
                number_items_deleted += 1

        db.session.commit()

    return number_items_deleted


def update_item_inventory_by_invid(item_data: dict, inventory_id: int, user: User):
    with app.app_context():
        item_id = item_data['id']

        stmt = select(UserInventory, Inventory, Item).join(Inventory).join(User).where(User.id == user.id).where(
            Inventory.id == inventory_id).where(Item.id == item_id)
        r = db.session.execute(stmt).first()

        r[2].name = item_data['name']
        r[2].description = item_data['description']
        r[2].item_type = item_data['item_type']
        r[2].location_id = item_data['item_location']

        item_tags = item_data['item_tags']
        if not isinstance(item_tags, list):
            item_tags = item_tags.strip()
            item_tags = item_tags.replace(" ", "@#$")
            if "," in item_tags:
                item_tags_list = item_tags.split(",")
        else:
            item_tags_list = item_tags

        r[2].tags = []
        for tag in item_tags_list:
            instance = db.session.query(Tag).filter_by(tag=tag).one_or_none()
            if not instance:
                instance = Tag(tag=tag)

            r[2].tags.append(instance)

        db.session.commit()


def get_or_create_item(name_, description_, tags_):
    with app.app_context():
        instance = db.session.query(Item).filter_by(name=name_, description=description_).one_or_none()
        if not instance:
            instance = Item(name=name_, description=description_)
            db.session.add(instance)
            db.session.commit()

            for tag in tags_:
                t = get_or_create(Tag, tag=tag)[0]
                # db.session.add(t)
                instance.tags.append(t)
            try:
                db.session.add(instance)
                db.session.commit()

            except Exception as e:
                print(e)
                db.session.rollback()
                instance = db.session.query(Item).filter_by(name=name_, description=description_).one()
                return instance, False
            else:
                return instance, True


def get_or_create(model, defaults=None, **kwargs):
    with app.app_context():
        instance = db.session.query(model).filter_by(**kwargs).first()
        if instance:
            return instance, False
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


def add_item_inventory_by_invid(item: Item, inventory_id: int, user: User):
    with app.app_context():
        stmt = select(UserInventory, Inventory).join(Inventory).join(User).where(User.id == user.id).where(
            Inventory.id == inventory_id)
        r = db.session.execute(stmt).first()[1]

        r.items.append(item)
        db.session.commit()


def add_item_to_inventory2(item_name, item_desc, item_type,
                           item_tags, item_location: int,
                           inventory_id: int, user: User, item_specific_location: str = None):
    with app.app_context():

        stmt = select(Inventory).where(Inventory.id == inventory_id)
        inventory_ = db.session.execute(stmt).first()[0]

        new_item = Item(name=item_name, description=item_desc,
                        item_type=item_type, location_id=item_location,
                        specific_location=item_specific_location, user_id=user.id)

        for tag in item_tags:
            instance = db.session.query(Tag).filter_by(tag=tag).one_or_none()
            if not instance:
                instance = Tag(tag=tag)

            new_item.tags.append(instance)

        inventory_.items.append(new_item)

        db.session.flush()
        item_slug = f"{str(new_item.id)}-{slugify(item_name)}"
        new_item.slug = item_slug

        db.session.commit()


def get_user_default_item_type(user_id: int):
    with app.app_context():
        user_default_item_type = ItemType.query.filter_by(user_id=user_id, name="none").one_or_none()
        return user_default_item_type

def commit():
    db.session.commit()


def add_item_to_inventory(item_id=None, item_name=None, item_desc=None, item_type=None, item_tags=None,
                          inventory_id=None, user_id=None, item_quantity=1,
                          item_location_id=None, item_specific_location="", custom_fields=None):
    app_context = app.app_context()

    with app_context:

        try:

            if custom_fields is None:
                custom_fields = {}

            if item_type is None:
                item_type = "none"

            if item_id is not None:
                new_item = find_item(user_id=user_id, item_id=item_id)

            if item_id is None or new_item is None:
                # create the new item
                new_item = Item(name=item_name, description=item_desc, user_id=user_id, quantity=item_quantity,
                                location_id=item_location_id, specific_location=item_specific_location)
                db.session.add(new_item)
                # get new item ID and set the item slug
                db.session.flush()
                item_slug = f"{str(new_item.id)}-{slugify(item_name)}"
                new_item.slug = item_slug

            #else:
            #    new_item = find_item(user_id=user_id, item_id=item_id)

            if item_type is None:
                item_type = "None"

            # set or create the item type
            if isinstance(item_type, int):
                new_item.item_type = item_type
            else:
                item_type_ = db.session.query(ItemType).filter_by(name=item_type.lower()).filter_by(
                    user_id=user_id).one_or_none()

                if item_type_ is None:
                    item_type_ = ItemType(name=item_type, user_id=user_id)
                    db.session.add(item_type_)
                    db.session.commit()
                    db.session.flush()

                new_item.item_type = item_type_.id
                db.session.commit()

            for tag in item_tags:
                if tag != '':
                    tag = tag.strip()
                    tag = tag.replace(" ", "@#$")
                    instance = db.session.query(Tag).filter_by(tag=tag).one_or_none()
                    if not instance:
                        instance = Tag(tag=tag, user_id=user_id)

                    if instance not in new_item.tags:
                        new_item.tags.append(instance)

            if inventory_id is None or inventory_id == '':
                default_user_inventory_ = get_user_default_inventory(user_id=user_id)
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

            add_new_item_field(new_item, custom_fields, user_id=user_id, app_context=app_context)

            return_data = {
                "status": "success",
                "item": {
                    "id": new_item.id,
                    "name": new_item.name,
                    "description": new_item.description,
                    "user_id": new_item.user_id,
                }
            }
            return_data['item']['tags'] = []
            item_tags = new_item.tags
            for tag in item_tags:
                return_data['item']['tags'].append({"tag": tag.tag})

        except Exception as e:
            return_data = {
                "status": "error",
                "item": {}
            }
            # log this error

        return return_data


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
                    "status": -1,
                    "message": err_msg,
                    "id": -1,
                    "name": "",
                    "description": ""
                }
        return {
            "status": 1,
            "id": location_.id,
            "name": location_.name,
            "description": location_.description
        }


def add_new_template(name: str, fields: str, to_user: User) -> FieldTemplate:
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


def get_users_for_inventory(inventory_id: int, current_user_id: int):
    with app.app_context():
        stmt = db.session.query(User, UserInventory.access_level) \
            .join(User, UserInventory.user_id == User.id) \
            .filter(UserInventory.inventory_id == inventory_id)

        result = db.session.execute(stmt).all()

        return dict(result)


def delete_user_to_inventory(inventory_id: int, user_to_delete_id: int):
    with app.app_context():
        user_inventory_ = UserInventory.query.filter(UserInventory.inventory_id == inventory_id) \
            .filter(UserInventory.user_id == user_to_delete_id).one_or_none()

        if user_inventory_ is not None:
            if user_inventory_.access_level != __OWNER__:
                db.session.delete(user_inventory_)
                db.session.commit()
                return True
            else:
                return False
        else:
            return False


def add_user_notification(to_user_id: int, from_user_id, message: str):
    with app.app_context():
        user_ = db.session.query(User).filter(User.id == to_user_id).one()
        if user_ is not None:
            from_user_ = db.session.query(User).filter(User.id == from_user_id).one()
            if from_user_ is not None:
                notification_ = Notification(text=message, from_user=from_user_)
                user_.notifications.append(notification_)
                db.session.commit()


def add_user_to_inventory_from_token(inventory_id: int, user_to_add: User, added_user_access_level: int):
    with app.app_context():

        user_inventory_ = UserInventory.query.filter(UserInventory.inventory_id == inventory_id) \
            .filter(UserInventory.user_id == user_to_add.id).one_or_none()

        if user_inventory_ is None:

            ui = UserInventory(user_id=user_to_add.id, inventory_id=inventory_id,
                               access_level=added_user_access_level)
            db.session.add(ui)
            db.session.commit()

            inv_ = Inventory.query.filter(Inventory.id == inventory_id).one_or_none()
            if inv_ is not None:
                msg = f"User @{user_to_add.username} has been added to your inventory " \
                      f"{inv_.name} as viewer using access token"
                add_user_notification(to_user_id=inv_.owner_id, from_user_id=user_to_add.id, message=msg)

            return True

        return False




def add_user_to_inventory(inventory_id: int, current_user_id: int, user_to_add_username: str,
                          added_user_access_level: int):
    with app.app_context():
        user_inventory_ = UserInventory.query.filter(UserInventory.inventory_id == inventory_id) \
            .filter(UserInventory.user_id == current_user_id).one_or_none()

        if user_inventory_ is not None:
            if user_inventory_.access_level == __OWNER__:
                if added_user_access_level != __OWNER__:

                    user_to_add_ = find_user_by_username(username=user_to_add_username)
                    if user_to_add_ is not None:
                        if user_to_add_ is not None:

                            # check if a user_inventory exists
                            user_to_add_inventory_ = UserInventory.query.filter(
                                UserInventory.inventory_id == inventory_id) \
                                .filter(UserInventory.user_id == user_to_add_.id).one_or_none()

                            if user_to_add_inventory_ is not None:
                                user_to_add_inventory_.access_level = added_user_access_level
                                db.session.commit()

                            else:
                                ui = UserInventory(user_id=user_to_add_.id, inventory_id=inventory_id,
                                                   access_level=added_user_access_level)
                                db.session.add(ui)
                                db.session.commit()

                            add_user_notification(from_user_id=current_user_id, to_user_id=user_to_add_.id,
                                                  message=f"You have been added to the following inventory")
                            return True

                    else:  # the username does not exist
                        return False
                else:
                    return False  # don't support owner change right now
            else:  # current user was not the inventory owner
                return False
        else:  # inventory was not found
            return False


def get_user_inventory_by_id(user_id: int, inventory_id: int) -> Inventory:
    session = db.session
    stmt = select(UserInventory).where(UserInventory.user_id == user_id) \
        .where(UserInventory.inventory_id == inventory_id)
    r = session.execute(stmt).one_or_none()

    return r

def save_user_inventory_view(user_id: int, inventory_id: int, view: int):
    with app.app_context():
        user_inventory_ = get_user_inventory_by_id(user_id=user_id, inventory_id=inventory_id)
        if user_inventory_ is not None:
            user_inventory_[0].view = view
            db.session.commit()


def find_item_by_slug(item_slug: str, user_id: int) -> Item:
    item_ = Item.query.filter_by(slug=item_slug).filter_by(user_id=user_id).first()
    return item_


def get_item_by_slug(item_slug: str):
    stmt = db.session.query(Item, ItemType.name, InventoryItem) \
        .join(InventoryItem, InventoryItem.item_id == Item.id) \
        .join(ItemType, ItemType.id == Item.item_type) \
        .join(Location, Location.id == Item.location_id) \
        .where(Item.slug == item_slug)

    result = db.session.execute(stmt).first()
    return result


# def get_item_by_slug2(username: str, item_slug: str, user: User):
#     item_user_ = find_user_by_username(username=username)
#
#     stmt = select(Item, ItemType.name, InventoryItem) \
#         .join(InventoryItem, InventoryItem.item_id == Item.id) \
#         .join(ItemType, ItemType.id == Item.item_type) \
#         .join(Location, Location.id == Item.location_id) \
#         .where(Item.slug == item_slug)
#
#     result = db.session.execute(stmt).first()
#     if result is not None:
#         item_, item_type_string, inventory_item_ = db.session.execute(stmt).first()
#
#         if item_ is not None:
#             if user is not None:
#                 if user.id == item_user_.id:
#                     return {
#                         "status": "success", "message": "", "access": "owner",
#                         "item": item_, "item_type": item_type_string,
#                         "inventory_item": inventory_item_
#                     }
#             elif inventory_item_.access_level == __PUBLIC__:
#                 return {
#                     "status": "success", "message": "", "access": "public",
#                     "item": item_, "item_type": item_type_string,
#                     "inventory_item": inventory_item_
#                 }
#             else:
#                 return {
#                     "status": "error", "message": "no access", "access": "denied",
#                     "item": None, "item_type": None,
#                     "inventory_item": None
#                 }
#     else:
#         return {
#             "status": "error", "message": "no item", "access": "n/a",
#             "item": None, "item_type": None,
#             "inventory_item": None
#         }


# def get_item_by_slug2(username: str, item_slug: str, user: User):
#     session = db.session
#     user_ = find_user_by_username(username=username)
#
#     full_slug = f"{user.id}-{item_slug}"
#     item_ = find_item_by_slug(item_slug=full_slug, user_id=user_.id)
#
#     stmt = select(Item, Inventory, ItemType, Location) \
#         .join(Inventory.items) \
#         .join(InventoryItem) \
#         .join(Location, Item.location_id == Location.id) \
#         .join(UserInventory) \
#         .join(ItemType) \
#         .where(UserInventory.user_id == user_.id) \
#         .where(Item.id == item_.id)
#     r = session.execute(stmt).first()
#
#     return r


# def get_item(username: str, inventory_slug: str, item_slug: str):
#     session = db.session
#     user_ = find_user_by_username(username=username)
#     if user_ is None:
#         app.logger.error(f"No user found with username: {username}")
#         raise ValueError(f"No user found with username: {username}")
#
#     inventory_, user_inventory_ = find_inventory_by_slug(inventory_slug=inventory_slug, user_id=user_.id)
#
#     if inventory_ is None:
#         app.logger.error(f"No inventory found with slug: {inventory_slug}")
#         raise ValueError(f"No inventory found with slug: {inventory_slug}")
#
#     item_ = find_item_by_slug(item_slug=item_slug, user_id=user_.id)
#     if item_ is None:
#         app.logger.error(f"No item found with slug: {item_slug}")
#         raise ValueError(f"No item found with slug: {item_slug}")
#
#     stmt = select(Item, ItemType) \
#         .join(Inventory.items) \
#         .join(InventoryItem) \
#         .join(UserInventory) \
#         .join(ItemType) \
#         .where(InventoryItem.inventory_id == inventory_.id) \
#         .where(UserInventory.user_id == user_.id) \
#         .where(Item.id == item_.id)
#     r = session.execute(stmt).first()
#
#     return r


def get_items_for_inventory(user: User, inventory_id: int):
    session = db.session
    stmt = select(Item, ItemType, Location) \
        .join(Inventory.items) \
        .join(InventoryItem) \
        .join(UserInventory) \
        .join(Location, Item.location_id == Location.id) \
        .join(ItemType) \
        .where(InventoryItem.inventory_id == inventory_id)  # .where(UserInventory.user_id == user.id)
    items_ = session.execute(stmt).all()

    return items_


def delete_item_from_inventory(user: User, inventory_id: int, item_id: int) -> None:
    stmt = select(UserInventory, Item).join(Inventory).join(User).filter(
        and_(User.id == user.id, Inventory.id == inventory_id, Item.id == item_id))

    item = db.session.execute(stmt).first()
    if item is not None:
        item = item[1]
        db.session.delete(item)
        db.session.commit()


def edit_inventory_data(user_id: int, inventory_id: int, name: str,
                        description: str, inventory_type: int, access_level: int) -> None:
    session = db.session

    stmt = select(UserInventory, Inventory).join(Inventory) \
        .where(UserInventory.user_id == user_id) \
        .where(UserInventory.inventory_id == inventory_id)

    results_ = session.execute(stmt).one_or_none()

    if results_ is not None:
        results_[1].name = name
        results_[1].description = description
        results_[1].type = inventory_type
        results_[1].access_level = access_level
        db.session.commit()


def delete_templates_from_db(user_id: str, template_ids) -> None:
    if not isinstance(template_ids, list):
        template_ids = [template_ids]

    stmt = select(FieldTemplate).join(User) \
        .where(FieldTemplate.user_id == user_id) \
        .where(FieldTemplate.id.in_(template_ids))
    templates_ = db.session.execute(stmt).all()

    # get all the niventories that use this template

    for template_ in templates_:
        template_ = template_[0]

        inventories_ = Inventory.query.filter(Inventory.field_template == template_.id).all()
        for inventory_ in inventories_:
            inventory_.field_template = None

        db.session.commit()

        db.session.delete(template_)
        db.session.commit()


def delete_location(user_id: int, location_ids) -> dict:
    if not isinstance(location_ids, list):
        location_ids = [location_ids]

    stmt = select(Location).join(User) \
        .where(Location.user_id == user_id) \
        .where(Location.id.in_(location_ids))
    locations_ = db.session.execute(stmt).all()

    number_items_deleted = 0
    user_default_location_ = Location.query.filter_by(name="None") \
        .filter_by(user_id=user_id).one_or_none()

    for location_ in locations_:
        if location_[0] is not None:
            location_ = location_[0]

            if location_ is not None:
                location_id = location_.id
                try:
                    # find any items with this location and chnge to None
                    if user_default_location_ is not None:
                        items_ = Item.query.filter_by(location_id=location_id)\
                            .filter_by(user_id=user_id).all()
                        for row in items_:
                            row.location_id = user_default_location_.id
                        db.session.commit()

                    db.session.delete(location_)
                    db.session.commit()

                except SQLAlchemyError as err:
                    return {"success": False}
    return {"success": True}



def get_user_public_lists(for_user_id: int):
    with app.app_context():
        stmt = db.session.query(Inventory).filter(
            Inventory.owner_id == for_user_id).filter(Inventory.access_level == __PUBLIC__)
        r = db.session.execute(stmt).all()

        ret_results = []

        for inv in r:
            inv = inv[0]
            d = {
                "inventory_id": inv.id,
                "inventory_name": inv.name,
                "inventory_description": inv.description,
                "inventory_slug": inv.slug,
                "inventory_access_level": inv.access_level,
                "inventory_owner": inv.owner.username,
                "inventory_item_count": len(inv.items),
                "inventory_type": inv.type,
                "userinventory_access_level": __PRIVATE__
            }
            ret_results.append(d)

        return ret_results


def get_user_inventories(current_user_id: int, requesting_user_id: int, access_level: int = -1) -> list:
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
        raise TypeError("access_level must be an integer")

    if not isinstance(current_user_id, int) and current_user_id is not None:
        raise TypeError("current_user_id must be an integer")

    if not isinstance(requesting_user_id, int) and requesting_user_id is not None:
        raise TypeError("requesting_user_id must be an integer")

    with (((app.app_context()))):

        # stmt = db.session.query(Inventory, UserInventory).join(UserInventory).filter(UserInventory.user_id==1).all()
        stmt = db.session.query(Inventory, UserInventory).join(UserInventory)

        if current_user_id is not None and requesting_user_id is not None:
            is_current_user = (current_user_id == requesting_user_id)
        else:
            if requesting_user_id is None:
                return []
            is_current_user = False

        if is_current_user:
            if access_level == -1:
                stmt = stmt.filter(UserInventory.user_id == current_user_id)
            else:
                stmt = stmt.filter(UserInventory.user_id == current_user_id) \
                    .filter(UserInventory.access_level == access_level)
        else:
            #stmt = stmt.filter(UserInventory.user_id == requesting_user_id).filter(UserInventory.access_level != 0)
            stmt = db.session.query(Inventory, UserInventory
                                    ).join(UserInventory
                                           ).filter(Inventory.owner_id == requesting_user_id
                                                    ).filter(Inventory.access_level == 1)

        r = db.session.execute(stmt).all()

        ret_results = []

        for inv, user_inv in r:
            d = {
                "inventory_id": inv.id,
                "inventory_name": inv.name,
                "inventory_description": inv.description,
                "inventory_slug": inv.slug,
                "inventory_access_level": inv.access_level,
                "inventory_owner": inv.owner.username,
                "inventory_item_count": len(inv.items),
                "inventory_type": inv.type,
                "userinventory_access_level": user_inv.access_level
            }
            ret_results.append(d)

        return ret_results


def get_user_templates(user_id: int):
    """
    Retrieve the templates associated with a given user.

    :param user_id: The user id for which templates are to be retrieved.
    :type int: int

    :return: A list of templates associated with the user.
    :rtype: list
    """
    session = db.session
    stmt = select(FieldTemplate).join(User).where(User.id == user_id)
    r = session.execute(stmt).all()
    return r


def get_user_template_by_id(template_id: int, user_id: int):
    """
    :param template_id: The ID of the template to retrieve.
    :param user_id: The ID of the user who owns the template.
    :return: The user template with the specified ID, or None if it doesn't exist.

    This method retrieves a user template from the database based on the provided template ID and user ID. It uses SQLAlchemy to construct and execute a SQL statement to fetch the template
    *. If the template is found, it is returned; otherwise, None is returned. If an error occurs during database access, an error message is logged.
    """
    session = db.session
    stmt = select(FieldTemplate).join(User).where(FieldTemplate.id == template_id)\
        .where(FieldTemplate.user_id == user_id)
    r = None
    try:
        r = session.execute(stmt).one_or_none()
    except SQLAlchemyError as e:
        app.logger.error(f"Failed to get template by ID: {str(e)}")
    return r


def get_template_fields_by_id(template_id: int):
    session = db.session
    stmt = select(TemplateField, Field) \
        .join(FieldTemplate) \
        .join(Field)\
        .where(FieldTemplate.id == template_id)
    r = session.execute(stmt).all()
    return r


def set_template_fields_orders(field_data, template_id: int, user_id: int):
    session = db.session

    user_template_ = get_user_template_by_id(template_id=template_id, user_id=user_id)
    if user_template_ is not None:

        for field_order, field_dict in field_data.items():
            field_id = field_dict[1]

            stmt = select(TemplateField).where(FieldTemplate.id == template_id)\
                .join(FieldTemplate)\
                .where(TemplateField.field_id == field_id)
            r = session.execute(stmt).one_or_none()

            if r is not None:
                r = r[0]
                r.order = field_order

        db.session.commit()

        return


def save_inventory_fieldtemplate(inventory_id: int , inventory_template: int, user_id: int):
    """

    Save Inventory Field Template

    This method is used to save the field template for a specific inventory.

    Parameters:
    - inventory_id (int): The ID of the inventory to save the field template for.
    - inventory_template (int): The ID of the field template to assign to the inventory.
    - user_id (int): The ID of the user who owns the inventory.

    Returns:
    - bool: True if the field template is saved successfully, False otherwise.

    """
    with app.app_context():
        inventory_, user_inventory_ = find_inventory_by_id(inventory_id=inventory_id, user_id=user_id)
        if inventory_ is None or user_inventory_ is None:
            app.logger.error(f"Failed to find inventory with ID: {inventory_id}")
            return False

        if user_inventory_.access_level == 0:
            inventory_.field_template = inventory_template

            template_ = db.session.query(FieldTemplate).filter(FieldTemplate.id == inventory_template).one_or_none()
            if template_ is not None:
                temp_fields = template_.fields
                field_ids = [x.id for x in temp_fields]

                items_ = inventory_.items

                for item in items_:
                    set_field_status(item_id=item.id, field_ids=field_ids)
            else:
                app.logger.error(f"Failed to find template with ID: {inventory_template}")
                return False

        try:
            db.session.commit()
        except Exception as e:
            app.logger.error(f"Failed to save inventory field template: {str(e)}")
            db.session.rollback()
            return False

    return True


def get_user_locations(user_id: int) -> List[dict]:
    session = db.session
    stmt = select(Location).where(Location.user_id == user_id)
    r = session.execute(stmt).all()
    locations_results = []
    for row in r:
        locations_results.append(
            {
                "id": row[0].id,
                "name": row[0].name,
                "description": row[0].description,
                "user_id": row[0].user_id
            }
        )
    return locations_results


def get_number_user_locations(user_id: int):
    session = db.session
    stmt = session.query(func.count(Location.id)).where(Location.user_id == user_id)
    r = session.execute(stmt).all()
    return r[0][0]


def get_user_location_by_id(location_id: str, user_id: int):
    session = db.session
    stmt = select(Location).join(User).where(User.id == user_id).where(Location.id == location_id)
    r = session.execute(stmt).one_or_none()
    if r is not None:
        return r[0].__dict__
    return None


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


def get_all_item_fields(item_id: int):
    with app.app_context():
        stmt = select(Field.field, ItemField).join(Item).join(Field, ItemField.field_id == Field.id) \
            .filter(ItemField.item_id == item_id)
        ddd = db.session.execute(stmt).all()
        return ddd


def get_all_fields():
    with app.app_context():
        stmt = select(Field.field, Field)
        ddd = db.session.execute(stmt).all()
        return ddd

def get_all_fields_include_users(user_id: int):
    with app.app_context():
        q_ = db.session.query(Field).filter(or_(Field.user_id == user_id, Field.user_id == None))
        res_ = db.session.execute(q_).all()
        return res_

def get_all_user_fields(user_id: int):
    with app.app_context():
        q_ = db.session.query(Field).filter(Field.user_id == user_id)
        res_ = db.session.execute(q_).all()
        return res_


def delete_fields_from_db(user_id: str, field_ids) -> None:
    if not isinstance(field_ids, list):
        field_ids = [field_ids]

    stmt = select(Field).join(User) \
        .where(Field.user_id == user_id) \
        .where(Field.id.in_(field_ids))
    fields_ = db.session.execute(stmt).all()

    for field_ in fields_:
        db.session.delete(field_[0])
        db.session.commit()




def set_inventory_default_fields(inventory_id, user, default_fields):
    with app.app_context():
        if inventory_id == '':
            inventory_ = get_user_default_inventory(user_id=user.id)
        else:
            inventory_ = Inventory.query.filter_by(id=inventory_id).first()

        user_inventory_ = UserInventory.query \
            .filter_by(inventory_id=inventory_.id).filter_by(user_id=user.id).first()
        inventory_.default_fields = ",".join(default_fields)

        db.session.commit()
        return


def save_template_fields(template_name, fields, user):
    field_type = 1
    if len(fields) > 0:
        if isinstance(fields[0], int):
            field_type = 1
        else:
            field_type = 2

    with app.app_context():

        field_template_ = FieldTemplate.query.filter_by(name=template_name).filter_by(user_id=user.id).one_or_none()

        if field_template_ is None:

            field_template_ = FieldTemplate(name=template_name, user_id=user.id)
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
                    save_inventory_fieldtemplate(inventory_id=inventory.id,
                                                 inventory_template=field_template_.id, user_id=user.id)

        db.session.commit()

        # now do the sorting
        stmt = select(TemplateField).where(FieldTemplate.id == field_template_.id)
        r = db.session.execute(stmt).all()

        max_order = db.session.query(func.max(TemplateField.order)).scalar()

        for row in r:
            if row[0].order == 0:
                max_order += 1
                row[0].order = max_order

        db.session.commit()

        return field_template_.id


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



def add_field(field_name:str, field_type:str, user_id:int):
    with app.app_context():
        slug = slugify(field_name)
        return get_or_create(model=Field, field=field_name, type=field_type,
                             user_id=user_id, slug=slug)


def edit_field_by_id(field_id: int, field_name:str, field_type:str, user_id:int):
    with app.app_context():
        field_ = Field.query.filter_by(id=field_id, user_id=user_id).one_or_none()
        if field_ is not None:
            field_.field = field_name
            field_.type = field_type
            db.session.commit()
            return True

        return False

def delete_field_by_field_name(field_name:str, user_id:int) -> bool:
    with app.app_context():
        field_ = Field.query.filter_by(field=field_name, user_id=user_id).one_or_none()
        if field_ is not None:
            db.session.delete(field_)
            db.session.commit()
            return True

        return False


def add_new_item_field(item: Item, custom_fields: dict, user_id: int, app_context=None):
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

        for field_name, field_value in custom_fields.items():

            field_ = Field.query.filter_by(slug=field_name).one_or_none()
            if field_ is None:
                field_slug = slugify(field_name)
                field_ = Field(field=field_name, slug=field_slug)
                db.session.add(field_)
                db.session.flush()

            field_id = field_.id
            if item not in field_.items:
                field_.items.append(item)

            db.session.commit()

            item_field_ = ItemField.query.filter_by(field_id=field_id).filter_by(item_id=item.id).one_or_none()
            item_field_.value = field_value
            item_field_.show = True
            item_field_.user_id=user_id

            db.session.commit()


def set_field_status(item_id, field_ids, is_visible=True):
    with app.app_context():

        all_fields = get_all_fields()

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

def update_user_password_by_token(token: str, password_hash: str) -> Tuple[bool, Optional[Exception]]:
    with app.app_context():
        with app.app_context():
            user_ = find_user_by_token(token=token)
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

def update_user_password_by_user_id(user_id: int, password_hash: str) -> Tuple[bool, Optional[Exception]]:
    with app.app_context():
        user_ = find_user_by_id(user_id=user_id)
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

def update_user_token_by_email(email: str, user_token: str, token_expires: datetime):
    with app.app_context():
        user_ = find_user(username_or_email=email)
        if user_ is not None and user_.activated:
            user_.token = user_token
            user_.token_expires = token_expires
            db.session.merge(user_)
            db.session.commit()
        return
