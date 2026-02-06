import unittest

from admin.load_intial_data import load_fields, load_words, load_types
from database_utils import drop_then_create
from services.thinglist_services import UserService, InventoryService
from site_globals import __INVENTORY__, __PRIVATE__


class TestAppParent(unittest.TestCase):
    users = {}

    @classmethod
    def setUp(cls):
        drop_then_create()
        _fields_added = load_fields()
        print(f'Added {_fields_added} fields:')

        _reserved_words_added = load_words()
        print(f'Added {_reserved_words_added} reserved words')

        _types_added = load_types()
        print(f'Added {_types_added} types')

        cls.users['simon'] = UserService.add_user_by_details(username='simon_test', email='simon_test@example.com',
                                                 password='password', fail_on_duplicate=False)
        cls.users['neil'] = UserService.add_user_by_details(username='neil_test', email='neil_test@example.com',
                                                password='password', fail_on_duplicate=False)
        cls.users['dave'] = UserService.add_user_by_details(username='dave_test', email='dave_test@example.com',
                                                password='password', fail_on_duplicate=False)

        cls.new_inventory_data = {
            cls.users['simon']: {
                "name": "simon_test_list1",
                "description": "simon_test_list1",
                "list_type": __INVENTORY__,
                "to_user": cls.users['simon'],
                "show_default_fields": 1,
                "show_item_images": 1,
                "show_item_type": 1,
                "show_item_location": 1,
                "show_item_tags": 1,
                "show_item_url": 1,
                "access_level": __PRIVATE__,
                "to_user_id": cls.users['simon'].id
            },
            cls.users['neil']: {
                "name": "neil_test_list1",
                "description": "neil_test_list1",
                "list_type": __INVENTORY__,
                "to_user": cls.users['neil'],
                "show_default_fields": 1,
                "show_item_images": 1,
                "show_item_type": 1,
                "show_item_location": 1,
                "show_item_tags": 1,
                "show_item_url": 1,
                "access_level": __PRIVATE__,
                "to_user_id": cls.users['neil'].id
            },
            cls.users['dave']: {
                "name": "dave_test_list1",
                "description": "dave_test_list1",
                "list_type": __INVENTORY__,
                "to_user": cls.users['dave'],
                "show_default_fields": 1,
                "show_item_images": 1,
                "show_item_type": 1,
                "show_item_location": 1,
                "show_item_tags": 1,
                "show_item_url": 1,
                "access_level": __PRIVATE__,
                "to_user_id": cls.users['dave'].id
            }
        }

        cls.items_to_add = {
            cls.users['simon'].id: [
                {"name": "item1", "description": "item1", "specific_location": "box 34",
                 "type": "my user computer", "tags": ["tag1", "tag2"], "quantity": 10, "url": "",
                 "user_id": cls.users['simon'].id},
                {"name": "item2", "description": "item2", "specific_location": "box 224",
                 "type": "printer", "tags": ["tag3", "tag4"], "quantity": 100, "url": "",
                 "user_id": cls.users['simon'].id},
                {"name": "item3", "description": "item3", "specific_location": "box 2124",
                 "type": "printer", "tags": ["tag31", "tag41"], "quantity": 100, "url": "",
                 "user_id": cls.users['simon'].id}
            ]
            ,
            cls.users['neil'].id: [
                {"name": "item4", "description": "item5", "specific_location": "box 224",
                 "type": "my user computer", "tags": ["tag32", "tag42"], "quantity": 100, "url": "",
                 "user_id": cls.users['neil'].id},
                {"name": "item6", "description": "item7", "specific_location": "box 224",
                 "type": "printer", "tags": ["tag31", "tag41"], "quantity": 100, "url": "",
                 "user_id": cls.users['neil'].id}
            ]
            ,
            cls.users['dave'].id: [
                {"name": "item8", "description": "item9", "specific_location": "box 224",
                 "type": "my user computer", "tags": ["tag32", "tag42"], "quantity": 100, "url": "",
                 "user_id": cls.users['dave'].id},
                {"name": "item10", "description": "item11", "specific_location": "box 224",
                 "type": "printer", "tags": ["tag31", "tag41"], "quantity": 100, "url": "",
                 "user_id": cls.users['dave'].id}
            ]

        }

        cls.fields_to_add_system = [
            {"field_name": "systemfield1", "field_type": "text"},
            {"field_name": "systemfield2", "field_type": "textarea"},
            {"field_name": "systemfield3", "field_type": "bool"},
            {"field_name": "systemfield4", "field_type": "url"}
        ]

        cls.fields_to_add_simon = [
            {"field_name": "simonfield1", "field_type": "text"},
            {"field_name": "simonfield2", "field_type": "textarea"},
            {"field_name": "simonfield3", "field_type": "bool"},
            {"field_name": "simonfield4", "field_type": "url"}
        ]

        cls.fields_to_add_dave = [
            {"field_name": "davefield1", "field_type": "text"},
            {"field_name": "davefield2", "field_type": "textarea"},
            {"field_name": "davefield3", "field_type": "bool"},
            {"field_name": "davefield4", "field_type": "url"}
        ]

    def add_list_for_user(self, list_data: dict):
        return InventoryService.add_user_list(name=list_data['name'],
                             description=list_data['description'],
                             inventory_type=list_data['list_type'],
                             show_default_fields=list_data[
                                 'show_default_fields'],
                             show_item_images=list_data['show_item_images'],
                             show_item_type=list_data['show_item_type'],
                             show_item_location=list_data[
                                 'show_item_location'],
                             show_item_tags=list_data['show_item_tags'],
                             show_item_url=list_data['show_item_url'],
                             access_level=list_data['access_level'],
                             user_id=list_data['to_user_id'])

    @classmethod
    def tearDown(cls):
        for user_name, user in cls.users.items():
            _ret = remove_user_by_id(user_id=user.id)


if __name__ == '__main__':
    unittest.main()
