import unittest

from database.database_functions import add_user_list, get_users_for_inventory, \
    add_item_to_inventory, find_items_new, delete_list_by_id, find_default_user_location, find_item_type_by_name, \
    update_item_by_id, find_all_my_items, get_user_item_count
from database.database_functions import add_user_by_details, remove_user_by_id
from site_globals import __INVENTORY__, __PRIVATE__


class TestApp(unittest.TestCase):
    users = {}

    @classmethod
    def setUpClass(cls):
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
             "type": "computer", "tags": ["tag1","tag2"], "quantity": 10, "url": "",},
            {"name": "item2", "description": "item2", "specific_location": "box 224",
             "type": "printer", "tags": ["tag3", "tag4"], "quantity": 100, "url": "", }
        ]


    @classmethod
    def tearDownClass(cls):
        for user_name, user in cls.users.items():
            _ret = 1
            _ret = remove_user_by_id(user_id=user.id)



    def test_add_items(self):
        new_inventory_data, status, msg = add_user_list(name=self.new_inventory_data['name'],
                                                        description=self.new_inventory_data['description'],
                                                        inventory_type=self.new_inventory_data['list_type'],
                                                        show_default_fields=self.new_inventory_data[
                                                            'show_default_fields'],
                                                        show_item_images=self.new_inventory_data['show_item_images'],
                                                        show_item_type=self.new_inventory_data['show_item_type'],
                                                        show_item_location=self.new_inventory_data[
                                                            'show_item_location'],
                                                        show_item_tags=self.new_inventory_data['show_item_tags'],
                                                        show_item_url=self.new_inventory_data['show_item_url'],
                                                        access_level=self.new_inventory_data['access_level'],
                                                        user_id=self.new_inventory_data['to_user_id'])

        _users_in_inventory = get_users_for_inventory(inventory_id=new_inventory_data["id"])
        self.assertEqual(1, len(_users_in_inventory))

        _user_default_location = find_default_user_location(user_id=self.new_inventory_data['to_user_id'])

        for _item in self.items_to_add:
            _ret = add_item_to_inventory(inventory_id=new_inventory_data["id"], item_name=_item["name"],
                                         item_desc=_item["description"], item_type=_item["type"],
                                         item_specific_location=_item["specific_location"],
                                         item_tags=_item["tags"],
                                         item_quantity=_item["quantity"], item_url=_item["url"],
                                         user_id=self.new_inventory_data['to_user_id'])

            _item_type = find_item_type_by_name(item_type_name=_item["type"],
                                                user_id=self.new_inventory_data['to_user_id'])
            self.assertEqual(_item_type.name, _item["type"])

            self.assertEqual("success", _ret["status"])
            _item_added = _ret["item"]
            self.assertEqual(_item["name"], _item_added["name"])
            self.assertEqual(_item["description"], _item_added["description"])

            for t in _item_added["tags"]:
                self.assertIn(t['tag'], _item["tags"])

            self.assertEqual(_item["quantity"], _item_added["quantity"])
            self.assertEqual(_item["url"], _item_added["url"])
            self.assertEqual(_user_default_location.id, _item_added["location_id"])
            self.assertEqual(_item["specific_location"], _item_added["specific_location"])


        # no user ids passed s should return empty {}
        _items = find_items_new(inventory_id=new_inventory_data["id"])
        self.assertEqual(0, len(_items))

        _items = find_items_new(inventory_id=new_inventory_data["id"], logged_in_user=self.users['simon'])
        self.assertEqual(2, len(_items))





        _item_type = find_item_type_by_name(item_type_name="printer",
                                            user_id=self.new_inventory_data['to_user_id'])


        new_item_data = {
            "name": "test_item edited",
            "description": "test_item edited",
            "item_location": _items[0][0].location_id,
            "item_specific_location": "box 134",
            "item_type": "personal computer",
            "item_tags": ["tag11", "tag21"],
            "item_quantity": 1011,
            "item_url": "",
           # "user_id": self.users['simon'].id
        }
        update_item_by_id(item_data=new_item_data, user=self.users['simon'], item_id=_items[0][0].id)


        _item_type = find_item_type_by_name(item_type_name="personal computer",
                                            user_id=self.new_inventory_data['to_user_id'])
        _query_params = {
            "item_type": _item_type.id
        }
        _items = find_items_new(inventory_id=new_inventory_data["id"], logged_in_user=self.users['simon'], query_params=_query_params)
        self.assertEqual(1, len(_items))



        self.assertEqual(_items[0][0].name, new_item_data["name"])
        self.assertEqual(_items[0][0].description, new_item_data["description"])

        #for t in new_item_data["tags"]:
        #    self.assertIn(t['tag'], _items[0][0].tags)

        self.assertEqual(_items[0][0].quantity, new_item_data["item_quantity"])
        self.assertEqual(_items[0][0].url, new_item_data["item_url"])
        self.assertEqual(_items[0][0].specific_location, new_item_data["item_specific_location"])






        status, msg = delete_list_by_id(inventory_ids=new_inventory_data["id"],
                                        user_id=self.new_inventory_data['to_user_id'])
        self.assertEqual(True, status)

        _items = find_all_my_items(logged_in_user_id=self.new_inventory_data['to_user_id'])
        self.assertEqual(2, len(_items))

        _item_count = get_user_item_count(user_id=self.new_inventory_data['to_user_id'])
        self.assertEqual(2, _item_count)




if __name__ == '__main__':
    unittest.main()
