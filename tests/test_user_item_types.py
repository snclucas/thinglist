import unittest

from database.database_functions import get_or_add_new_user_item_type, \
    get_user_item_type_count, find_item_type_by_text
from services.thinglist_services import ItemTypeService
from tests.test_parent import TestAppParent


class TestApp(TestAppParent):

    def test_add_and_delete_user_item_type(self):
        _user_item_count = get_user_item_type_count(user_id=self.users['simon'].id)
        self.assertEqual(0, _user_item_count)

        new_item_type_name = "test_item_type"

        status, msg, item_type_dict = get_or_add_new_user_item_type(name=new_item_type_name, user_id=self.users['simon'].id)
        self.assertEqual(True, status)

        _user_item_count = get_user_item_type_count(user_id=self.users['simon'].id)
        self.assertEqual(1, _user_item_count)


        _found_item_type = find_item_type_by_text(type_text=new_item_type_name)
        self.assertEqual(new_item_type_name, _found_item_type['name'])
        self.assertEqual(item_type_dict["id"], _found_item_type['id'])

        status, msg = ItemTypeService.delete_item_types_by_id(itemtype_ids=[item_type_dict["id"]], user_id=self.users['simon'].id)
        self.assertEqual(True, status)



if __name__ == '__main__':
    unittest.main()
