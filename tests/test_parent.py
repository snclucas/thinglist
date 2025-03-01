import unittest

from admin.load_intial_data import load_fields, load_words
from database.database_functions import add_user_by_details, remove_user_by_id
from site_globals import __INVENTORY__, __PRIVATE__

class TestAppParent(unittest.TestCase):

    users = {}

    @classmethod
    def setUpClass(cls):
        _fields_added = load_fields()
        print(f'Added {_fields_added} fields:')

        _reserved_words_added = load_words()
        print(f'Added {_reserved_words_added} reserved words')

        cls.users['simon'] = add_user_by_details(username='simon_test', email='simon_test@example.com',
                                                 password='password', fail_on_duplicate=False)
        cls.users['neil'] = add_user_by_details(username='neil_test', email='neil_test@example.com',
                                                password='password', fail_on_duplicate=False)
        cls.users['dave'] = add_user_by_details(username='dave_test', email='dave_test@example.com',
                                                password='password', fail_on_duplicate=False)

        cls.new_inventory_data = {
            "name": "test_list",
            "description": "test_list",
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
        }

        cls.items_to_add = [
            {"name": "item1", "description": "item1", "specific_location": "box 34",
             "type": "computer", "tags": ["tag1", "tag2"], "quantity": 10, "url": "", },
            {"name": "item2", "description": "item2", "specific_location": "box 224",
             "type": "printer", "tags": ["tag3", "tag4"], "quantity": 100, "url": "", }
        ]


    @classmethod
    def tearDownClass(cls):
        for user_name, user in cls.users.items():
            _ret = remove_user_by_id(user_id = user.id)


if __name__ == '__main__':
    unittest.main()
