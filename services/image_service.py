import os
from typing import Tuple, List, Optional

from sqlalchemy.exc import SQLAlchemyError

from app import app, db
from models import Image, ItemImage, User


class ImageService:

    @staticmethod
    def set_item_main_image(main_image_url: str, item_id: int, user_id: int) -> bool:
        """
        Sets the main image URL for an item.

        Parameters:
        - main_image_url (str): The URL of the main image for the item.
        - item_id (int): The ID of the item.
        - user_id (int): The user id associated with the item.

        Returns:
        - bool: Returns True if the main image URL is successfully set for the item, False otherwise.
        """
        if main_image_url is None or main_image_url == "":
            return False
        if item_id is None:
            return False
        if user_id is None:
            return False

        with app.app_context():
            from services.item_service import ItemService
            item_ = ItemService.get_item_by_id(item_id=item_id, user_id=user_id)

            if item_ is None:
                app.logger.error(f'No item with id {item_id} found for user id {user_id}')
                return False

            item_.main_image = main_image_url

            try:
                db.session.commit()
                return True
            except SQLAlchemyError as ex:
                app.logger.error(f"Could not set main image for item with id {item_id}: {ex}")
                db.session.rollback()
                return False

    @staticmethod
    def get_all_images(user_id: int = None) -> Tuple[Image, ItemImage]:
        with app.app_context():
            images_ = Image.query.all()
            itemimages_ = ItemImage.query.all()
            return images_, itemimages_

    @staticmethod
    def add_images_to_item(item_id: int, filenames: list[str], user: User) -> Tuple[bool, str]:
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
            from services.item_service import ItemService
            item_ = ItemService.get_item_by_id(item_id=item_id, user_id=None)
            if item_ is None:
                return False, f"No item with id {item_id} found for user {user.username}"

            for file in filenames:
                new_image = Image(image_filename=file, user_id=user.id)
                item_.images.append(new_image)

            item_.main_image = item_.images[0].image_filename

            try:
                db.session.commit()
                return True, ""
            except SQLAlchemyError as ex:
                app.logger.error(f"Could not add images to item with id {item_id}: {ex}")
                db.session.rollback()
                return False, f"Could not add images to item with id {item_id}: {ex}"

    @staticmethod
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

    @staticmethod
    def delete_images_from_item(item_id: int, image_ids: List[str], user: User) -> Tuple[bool, str]:
        """
        Deletes images from an item.

        Args:
            item_id (int): ID of the item.
            image_ids (List[str]): List of image IDs to be deleted.
            user (User): User object representing the owner of the images.

        Returns:
            tuple: A tuple containing a boolean value indicating the success of the operation and a string message providing information about the result. The boolean value is True if the images
        * were successfully deleted, and False otherwise. The string message contains additional details about the result.

        Example:
            delete_images_from_item(1, ['image1.jpg', 'image2.jpg'], user_obj)
        """
        if item_id is None:
            return False, "Item ID cannot be None"

        if image_ids is None or len(image_ids) == 0:
            return False, "No image IDs provided"

        with app.app_context():
            from services.item_service import ItemService
            item_ = ItemService.get_item_by_id(item_id=item_id, user_id=None)
            if item_ is None:
                return False, f"No item with id {item_id} found for user {user.username}"

            for image_id in image_ids:
                image_ = ImageService.find_image_by_filename(image_filename=image_id, user=user)
                if image_ is None:
                    return False, f"No image with id {image_id} found for user {user.username}"

                if image_ in item_.images:
                    if image_.image_filename == item_.main_image:
                        item_.main_image = None
                    item_.images.remove(image_)

                    try:
                        os.remove(os.path.join(app.root_path,
                                               app.config['USER_IMAGES_BASE_PATH'],
                                               str(user.id),
                                               image_.image_filename))
                    except OSError as er:
                        err_msg = f"Could not delete image with id {image_id} for user {user.username}: {er}"
                        app.logger.error(err_msg)
                        return False, err_msg

            if item_.main_image is None:
                if len(item_.images) == 0:
                    item_.main_image = None
                else:
                    item_.main_image = item_.images[0].image_filename

            try:
                db.session.commit()
                return True, "Images deleted successfully"
            except SQLAlchemyError as ex:
                err_msg = f"Could not delete images: {ex}"
                app.logger.error(err_msg)
                db.session.rollback()
                return False, err_msg
