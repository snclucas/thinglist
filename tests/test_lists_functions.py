import unittest

from slugify import slugify

from database_functions import add_user_by_details, remove_user_by_id, \
    get_number_user_lists, add_user_list, find_inventory_by_id, \
    find_inventory_by_slug, delete_list_by_id, edit_inventory_data, get_users_for_inventory, add_user_to_inventory, \
    delete_user_to_inventory, find_inventory_by_access_token

from site_globals import __INVENTORY__, __PRIVATE__, __LIST__, __COLLABORATOR__, __PUBLIC__


class TestApp(unittest.TestCase):
    users = {}

    @classmethod
    def setUp(cls):
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

    @classmethod
    def tearDown(cls):
        for user_name, user in cls.users.items():
            _ret = 1
            _ret = remove_user_by_id(user_id=user.id)

    def test_add_user_to_list(self):
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

        _user_to_add = self.users['neil']
        add_user_to_inventory(inventory_id=new_inventory_data["id"], current_user_id=self.users['simon'].id,
                              user_to_add_username=_user_to_add.username, added_user_access_level=__COLLABORATOR__)

        _users_in_inventory = get_users_for_inventory(inventory_id=new_inventory_data["id"])
        for _user, _access_level in _users_in_inventory.items():
            if _user.username == _user_to_add.username:
                self.assertEqual(__COLLABORATOR__, _access_level)

        self.assertEqual(2, len(_users_in_inventory))

        # Try to delete the inventory owner - should not delete and return False
        _ret, msg = delete_user_to_inventory(inventory_id=new_inventory_data["id"], user_to_delete_id=self.users['simon'].id)
        self.assertEqual(False, _ret)
        _users_in_inventory = get_users_for_inventory(inventory_id=new_inventory_data["id"])
        self.assertEqual(2, len(_users_in_inventory))

        # Try to delete the newly added user - should delete and return True
        _ret, msg = delete_user_to_inventory(inventory_id=new_inventory_data["id"], user_to_delete_id=_user_to_add.id)
        self.assertEqual(True, _ret)
        _users_in_inventory = get_users_for_inventory(inventory_id=new_inventory_data["id"])
        self.assertEqual(1, len(_users_in_inventory))

    def test_find_list_by_slug(self):
        _num_lists = get_number_user_lists(user_id=self.users['simon'].id)
        self.assertEqual(1, _num_lists)

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

        self.assertEqual(True, status)
        self.assertEqual("success", msg)
        self.assertEqual(self.new_inventory_data['name'], new_inventory_data["name"])
        self.assertEqual(self.new_inventory_data['description'], new_inventory_data["description"])
        self.assertEqual(self.new_inventory_data['list_type'], new_inventory_data["type"])



        _found_list, _found_userlist = find_inventory_by_slug(inventory_slug=slugify(self.new_inventory_data['name']),
                                                              inventory_owner_id=self.new_inventory_data['to_user_id'],
                                                              viewing_user_id=self.new_inventory_data['to_user_id'])

        self.assertIsNotNone(_found_list)
        self.assertIsNotNone(_found_userlist)

        self.assertEqual(self.new_inventory_data['name'], _found_list.name)
        self.assertEqual(self.new_inventory_data['description'], _found_list.description)
        self.assertEqual(self.new_inventory_data['list_type'], _found_list.type)
        self.assertEqual(self.new_inventory_data['show_default_fields'], _found_list.show_default_fields)
        self.assertEqual(self.new_inventory_data['show_item_images'], _found_list.show_item_images)
        self.assertEqual(self.new_inventory_data['show_item_type'], _found_list.show_item_type)
        self.assertEqual(self.new_inventory_data['show_item_location'], _found_list.show_item_location)
        self.assertEqual(self.new_inventory_data['show_item_tags'], _found_list.show_item_tags)
        self.assertEqual(self.new_inventory_data['show_item_url'], _found_list.show_item_url)
        self.assertEqual(self.new_inventory_data['access_level'], _found_list.access_level)

        _num_lists = get_number_user_lists(user_id=self.users['simon'].id)
        self.assertEqual(2, _num_lists)






        # not logged in
        _found_list, _found_userlist = find_inventory_by_slug(inventory_slug=slugify(self.new_inventory_data['name']),
                                                              inventory_owner_id=self.new_inventory_data['to_user_id'],
                                                              viewing_user_id=None)

        self.assertIsNone(_found_list)
        self.assertIsNone(_found_userlist)


        _found_list, _found_userlist = find_inventory_by_slug(inventory_slug=slugify(self.new_inventory_data['name']),
                                                              inventory_owner_id=None,
                                                              viewing_user_id=self.new_inventory_data['to_user_id'])

        self.assertIsNone(_found_list)

        _found_list, _found_userlist = find_inventory_by_slug(inventory_slug=None, # noqa
                                                              inventory_owner_id=self.new_inventory_data['to_user_id'],
                                                              viewing_user_id=self.new_inventory_data['to_user_id'])

        self.assertIsNone(_found_list)


    def test_create_list(self):
        _num_lists = get_number_user_lists(user_id=self.users['simon'].id)
        self.assertEqual(1, _num_lists)

        new_inventory_data, status, msg = add_user_list(name=self.new_inventory_data['name'],
                                                        description=self.new_inventory_data['description'],
                                                        inventory_type=self.new_inventory_data['list_type'],
                                                        show_default_fields=self.new_inventory_data['show_default_fields'],
                                                        show_item_images=self.new_inventory_data['show_item_images'],
                                                        show_item_type=self.new_inventory_data['show_item_type'],
                                                        show_item_location=self.new_inventory_data['show_item_location'],
                                                        show_item_tags=self.new_inventory_data['show_item_tags'],
                                                        show_item_url=self.new_inventory_data['show_item_url'],
                                                        access_level=self.new_inventory_data['access_level'],
                                                        user_id=self.new_inventory_data['to_user_id'])

        self.assertEqual(True, status)
        self.assertEqual("success", msg)
        self.assertEqual(self.new_inventory_data['name'], new_inventory_data["name"])
        self.assertEqual(self.new_inventory_data['description'], new_inventory_data["description"])
        self.assertEqual(self.new_inventory_data['list_type'], new_inventory_data["type"])

        _found_list, _found_userlist = find_inventory_by_id(inventory_id=new_inventory_data["id"],
                                                            user_id=self.new_inventory_data['to_user_id'])

        self.assertIsNotNone(_found_list)
        self.assertEqual(self.new_inventory_data['name'], _found_list.name)
        self.assertEqual(self.new_inventory_data['description'], _found_list.description)
        self.assertEqual(self.new_inventory_data['list_type'], _found_list.type)
        self.assertEqual(self.new_inventory_data['show_default_fields'], _found_list.show_default_fields)
        self.assertEqual(self.new_inventory_data['show_item_images'], _found_list.show_item_images)
        self.assertEqual(self.new_inventory_data['show_item_type'], _found_list.show_item_type)
        self.assertEqual(self.new_inventory_data['show_item_location'], _found_list.show_item_location)
        self.assertEqual(self.new_inventory_data['show_item_tags'], _found_list.show_item_tags)
        self.assertEqual(self.new_inventory_data['show_item_url'], _found_list.show_item_url)
        self.assertEqual(self.new_inventory_data['access_level'], _found_list.access_level)


        _num_lists = get_number_user_lists(user_id=self.users['simon'].id)
        self.assertEqual(2, _num_lists)

        status, msg = edit_inventory_data(inventory_id=new_inventory_data["id"], inventory_type=__LIST__,
                                          user_id=self.new_inventory_data['to_user_id'], name="test_list_edited",
                                          description="test_list_edited",
                                          show_default_fields=0, show_item_images=0, show_item_type=0,
                                          show_item_location=0,
                                          show_item_tags=0, show_item_url=0, access_level=__PUBLIC__)


        _found_list, _found_userlist = find_inventory_by_slug(inventory_slug=slugify(self.new_inventory_data['name']),
                                                              inventory_owner_id=self.new_inventory_data['to_user_id'],
                                                              viewing_user_id=self.new_inventory_data['to_user_id'])

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
        self.assertEqual(__PUBLIC__, _found_list.access_level)

        _found_list = find_inventory_by_access_token(access_token=_found_list.token)

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
        self.assertEqual(__PUBLIC__, _found_list.access_level)





        status, msg = delete_list_by_id(inventory_ids=new_inventory_data["id"],
                                        user_id=self.new_inventory_data['to_user_id'])
        self.assertEqual(True, status)

        _num_lists = get_number_user_lists(user_id=self.users['simon'].id)
        self.assertEqual(1, _num_lists)


if __name__ == '__main__':
    unittest.main()
