
from typing import Optional, Tuple, List

from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from app import db, app
from database_utils import _commit

from models import Inventory, User, FieldTemplate, TemplateField, Field
from services.field_service import FieldService


class FieldTemplateService:

    @staticmethod
    def delete_templates_from_db(user_id: str, template_ids) -> None:
        if not isinstance(template_ids, list):
            template_ids = [template_ids]

        with app.app_context():
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
            from services.inventory_service import InventoryService
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
    def add_new_template(name: str, fields: List[int], to_user: User) -> Optional[FieldTemplate]:
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
    def get_user_template_by_id(template_id: int, user_id: int):
        """
        :param template_id: The ID of the template to retrieve.
        :param user_id: The ID of the user who owns the template.
        :return: The user template with the specified ID, or None if it doesn't exist.

        This method retrieves a user template from the database based on the provided template ID and user ID. It uses SQLAlchemy to construct and execute a SQL statement to fetch the template
        *. If the template is found, it is returned; otherwise, None is returned. If an error occurs during database access, an error message is logged.
        """
        with app.app_context():
            stmt = select(FieldTemplate).join(User).where(FieldTemplate.id == template_id) \
                .where(FieldTemplate.user_id == user_id)
            r = None
            try:
                r = db.session.execute(stmt).one_or_none()
            except SQLAlchemyError as e:
                app.logger.error(f"Failed to get template by ID: {str(e)}")
            return r

    @staticmethod
    def get_template_fields_by_id(template_id: int):
        session = db.session
        stmt = select(TemplateField, Field) \
            .join(FieldTemplate) \
            .join(Field) \
            .where(FieldTemplate.id == template_id)
        r = session.execute(stmt).all()
        return r

    @staticmethod
    def get_user_templates_with_fields(user_id: int):
        """
        Return a list of dicts: { 'template': FieldTemplate, 'fields': [Field,...] }
        The fields list for each template is ordered by TemplateField.order.
        """
        session = db.session
        stmt = select(FieldTemplate, TemplateField, Field) \
            .join(TemplateField, TemplateField.template_id == FieldTemplate.id) \
            .join(Field, Field.id == TemplateField.field_id) \
            .where(FieldTemplate.user_id == user_id) \
            .order_by(FieldTemplate.id, TemplateField.order)

        rows = session.execute(stmt).all()

        grouped: dict[int, dict] = {}
        for ft, tf, f in rows:
            tid = ft.id
            if tid not in grouped:
                grouped[tid] = {"template": ft, "fields": []}
            grouped[tid]["fields"].append(f)

        return list(grouped.values())

    @staticmethod
    def set_template_fields_orders(field_data, template_id: int, user_id: int):
        session = db.session

        user_template_ = FieldTemplateService.get_user_template_by_id(template_id=template_id, user_id=user_id)
        if user_template_ is not None:

            #for field_order, field_dict in field_data.items():
            for ff in field_data:
                #field_id = field_dict[1]

                field_id = ff['id']
                field_order = ff['position']

                stmt = select(TemplateField).where(FieldTemplate.id == template_id) \
                    .join(FieldTemplate) \
                    .where(TemplateField.field_id == field_id)  # type: ignore
                r = session.execute(stmt).one_or_none()

                if r is not None:
                    r = r[0]
                    r.order = field_order

            db.session.commit()

            return

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
    def get_user_templates(user_id: int) -> List[FieldTemplate]:
        """
        Retrieve the templates associated with a given user.

        Validates and coerces `user_id`, returns a list of FieldTemplate objects,
        and handles SQL errors by logging and returning an empty list.
        """
        if user_id is None:
            return []

        try:
            user_id = int(user_id)
        except (TypeError, ValueError):
            app.logger.debug("get_user_templates: invalid user_id %r", user_id)
            return []

        try:
            with app.app_context():
                stmt = select(FieldTemplate).where(FieldTemplate.user_id == user_id)
                templates: List[FieldTemplate] = db.session.execute(stmt).scalars().all()
                return templates
        except SQLAlchemyError as e:
            app.logger.exception("get_user_templates DB error: %s", e)
            try:
                db.session.rollback()
            except Exception:
                pass
            return []

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


