from typing import Optional, List, Union, Tuple

from sqlalchemy import select, func
from sqlalchemy.exc import SQLAlchemyError, InvalidRequestError, NoResultFound

from app import db, app
from database_utils import _commit, _to_dict
from models import Location, User, Item
from services.user_service import UserService

from site_globals import __DEFAULT__

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
    def get_number_user_locations(user_id: int) -> Optional[int]:
        if user_id is None:
            app.logger.error(f"Number of user locations failed as the user ID is None")
            return None

        with app.app_context():
            try:
                stmt = db.session.query(func.count(Location.id)).where(Location.user_id == user_id)
                r = db.session.execute(stmt).all()
                return r[0][0]
            except SQLAlchemyError as err:
                app.logger.error(f"Failed to get number of user locations: {str(err)}")
                return None

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

