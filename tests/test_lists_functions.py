import unittest

from slugify import slugify

from database_functions import add_user_by_details, remove_user_by_id, \
    get_number_user_lists, add_user_list, find_inventory_by_id, \
    find_inventory_by_slug, delete_list_by_id, edit_inventory_data

from site_globals import __INVENTORY__, __PRIVATE__, __LIST__

class TestApp(unittest.TestCase):

    users = {}

    @classmethod
    def setUpClass(cls):
        cls.users['simon'] = add_user_by_details(username='simon_test', email='simon_test@example.com', password='password', fail_on_duplicate=False)
        cls.users['neil'] = add_user_by_details(username='neil_test', email='neil_test@example.com', password='password', fail_on_duplicate=False)
        cls.users['dave'] = add_user_by_details(username='dave_test', email='dave_test@example.com', password='password', fail_on_duplicate=False)

    @classmethod
    def tearDownClass(cls):
        for user_name, user in cls.users.items():
            _ret = 1
            _ret = remove_user_by_id(user_id = user.id)
            print(_ret)







    def test_create_list(self):

        _num_lists = get_number_user_lists(user_id=self.users['simon'].id)
        self.assertEqual(1, _num_lists)

        name = "test_list"
        description = "test_list"
        list_type = __INVENTORY__
        to_user = self.users['simon']
        show_default_fields = 1
        show_item_images = 1
        show_item_type = 1
        show_item_location = 1
        show_item_tags = 1
        show_item_url = 1
        access_level = __PRIVATE__

        new_inventory_data, status, msg = add_user_list(name=name,
                                                        description=description,
                                                        inventory_type=list_type,
                                                        show_default_fields=show_default_fields,
                                                        show_item_images=show_item_images,
                                                        show_item_type=show_item_type,
                                                        show_item_location=show_item_location,
                                                        show_item_tags=show_item_tags,
                                                        show_item_url=show_item_url,
                                                        access_level=access_level,
                                                        user_id=to_user.id)

        self.assertEqual(True, status)
        self.assertEqual("success", msg)
        self.assertEqual(name, new_inventory_data["name"])
        self.assertEqual(description, new_inventory_data["description"])
        self.assertEqual(list_type, new_inventory_data["type"])


        _found_list, _found_userlist = find_inventory_by_id(inventory_id=new_inventory_data["id"], user_id=to_user.id)

        self.assertIsNotNone(_found_list)
        self.assertEqual(name, _found_list.name)
        self.assertEqual(description, _found_list.description)
        self.assertEqual(list_type, _found_list.type)
        self.assertEqual(show_default_fields, _found_list.show_default_fields)
        self.assertEqual(show_item_images, _found_list.show_item_images)
        self.assertEqual(show_item_type, _found_list.show_item_type)
        self.assertEqual(show_item_location, _found_list.show_item_location)
        self.assertEqual(show_item_tags, _found_list.show_item_tags)
        self.assertEqual(show_item_url, _found_list.show_item_url)
        self.assertEqual(access_level, _found_list.access_level)



        _found_list, _found_userlist = find_inventory_by_slug(inventory_slug=slugify(name), inventory_owner_id=to_user.id, viewing_user_id=to_user.id)

        self.assertIsNotNone(_found_list)
        self.assertEqual(name, _found_list.name)
        self.assertEqual(description, _found_list.description)
        self.assertEqual(list_type, _found_list.type)
        self.assertEqual(show_default_fields, _found_list.show_default_fields)
        self.assertEqual(show_item_images, _found_list.show_item_images)
        self.assertEqual(show_item_type, _found_list.show_item_type)
        self.assertEqual(show_item_location, _found_list.show_item_location)
        self.assertEqual(show_item_tags, _found_list.show_item_tags)
        self.assertEqual(show_item_url, _found_list.show_item_url)
        self.assertEqual(access_level, _found_list.access_level)


        _num_lists = get_number_user_lists(user_id=self.users['simon'].id)
        self.assertEqual(2, _num_lists)

        status, msg = edit_inventory_data(inventory_id=new_inventory_data["id"], inventory_type=__LIST__,
                            user_id=to_user.id, name="test_list_edited", description="test_list_edited",
                            show_default_fields=0, show_item_images=0, show_item_type=0, show_item_location=0,
                            show_item_tags=0, show_item_url=0, access_level=3)

        _found_list, _found_userlist = find_inventory_by_slug(inventory_slug=slugify(name),
                                                              inventory_owner_id=to_user.id, viewing_user_id=to_user.id)

        self.assertEqual(True, status)
        self.assertEqual("test_list_edited", _found_list.name)
        self.assertEqual("test_list_edited", _found_list.description)
        self.assertEqual(__LIST__, _found_list.type)
        self.assertEqual(0, _found_list.show_default_fields)
        self.assertEqual(0, _found_list.show_item_images)
        self.assertEqual(0, _found_list.show_item_type)
        self.assertEqual(0, _found_list.show_item_location)
        self.assertEqual(0, _found_list.show_item_tags)
        self.assertEqual(0, _found_list.show_item_url)
        self.assertEqual(3, _found_list.access_level)


        status, msg = delete_list_by_id(inventory_ids=new_inventory_data["id"], user_id=to_user.id)
        self.assertEqual(True, status)

        _num_lists = get_number_user_lists(user_id=self.users['simon'].id)
        self.assertEqual(1, _num_lists)









if __name__ == '__main__':

    unittest.main()
