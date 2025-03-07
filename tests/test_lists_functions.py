import unittest

from slugify import slugify

from database.database_functions import get_number_user_lists, find_inventory_by_id, \
    find_inventory_by_slug, delete_list_by_id, edit_inventory_data, get_users_for_inventory, add_user_to_inventory, \
    delete_user_to_inventory, find_inventory_by_access_token

from site_globals import __LIST__, __COLLABORATOR__, __PUBLIC__
from tests.test_parent import TestAppParent


class TestApp(TestAppParent):



    def test_add_user_to_list(self):
        list_data = self.new_inventory_data[self.users['simon']]
        new_inventory_data, status, msg = self.add_list_for_user(list_data)

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

        list_data = self.new_inventory_data[self.users['simon']]
        new_inventory_data, status, msg = self.add_list_for_user(list_data)

        self.assertEqual(True, status)
        self.assertEqual("success", msg)
        self.assertEqual(list_data['name'], new_inventory_data["name"])
        self.assertEqual(list_data['description'], new_inventory_data["description"])
        self.assertEqual(list_data['list_type'], new_inventory_data["type"])



        _found_list, _found_userlist = find_inventory_by_slug(inventory_slug=slugify(list_data['name']),
                                                              inventory_owner_id=list_data['to_user_id'],
                                                              viewing_user_id=list_data['to_user_id'])

        self.assertIsNotNone(_found_list)
        self.assertIsNotNone(_found_userlist)

        self.assertEqual(list_data['name'], _found_list.name)
        self.assertEqual(list_data['description'], _found_list.description)
        self.assertEqual(list_data['list_type'], _found_list.type)
        self.assertEqual(list_data['show_default_fields'], _found_list.show_default_fields)
        self.assertEqual(list_data['show_item_images'], _found_list.show_item_images)
        self.assertEqual(list_data['show_item_type'], _found_list.show_item_type)
        self.assertEqual(list_data['show_item_location'], _found_list.show_item_location)
        self.assertEqual(list_data['show_item_tags'], _found_list.show_item_tags)
        self.assertEqual(list_data['show_item_url'], _found_list.show_item_url)
        self.assertEqual(list_data['access_level'], _found_list.access_level)

        _num_lists = get_number_user_lists(user_id=self.users['simon'].id)
        self.assertEqual(2, _num_lists)






        # not logged in
        _found_list, _found_userlist = find_inventory_by_slug(inventory_slug=slugify(list_data['name']),
                                                              inventory_owner_id=list_data['to_user_id'],
                                                              viewing_user_id=None)

        self.assertIsNone(_found_list)
        self.assertIsNone(_found_userlist)


        _found_list, _found_userlist = find_inventory_by_slug(inventory_slug=slugify(list_data['name']),
                                                              inventory_owner_id=None,
                                                              viewing_user_id=list_data['to_user_id'])

        self.assertIsNone(_found_list)

        _found_list, _found_userlist = find_inventory_by_slug(inventory_slug=None, # noqa
                                                              inventory_owner_id=list_data['to_user_id'],
                                                              viewing_user_id=list_data['to_user_id'])

        self.assertIsNone(_found_list)


    def test_create_list(self):
        _num_lists = get_number_user_lists(user_id=self.users['simon'].id)
        self.assertEqual(1, _num_lists)

        list_data = self.new_inventory_data[self.users['simon']]
        new_inventory_data, status, msg = self.add_list_for_user(list_data)

        self.assertEqual(True, status)
        self.assertEqual("success", msg)
        self.assertEqual(list_data['name'], new_inventory_data["name"])
        self.assertEqual(list_data['description'], new_inventory_data["description"])
        self.assertEqual(list_data['list_type'], new_inventory_data["type"])

        _found_list, _found_userlist = find_inventory_by_id(inventory_id=new_inventory_data["id"],
                                                            user_id=list_data['to_user_id'])

        self.assertEqual(list_data['name'], _found_list.name)
        self.assertEqual(list_data['description'], _found_list.description)
        self.assertEqual(list_data['list_type'], _found_list.type)
        self.assertEqual(list_data['show_default_fields'], _found_list.show_default_fields)
        self.assertEqual(list_data['show_item_images'], _found_list.show_item_images)
        self.assertEqual(list_data['show_item_type'], _found_list.show_item_type)
        self.assertEqual(list_data['show_item_location'], _found_list.show_item_location)
        self.assertEqual(list_data['show_item_tags'], _found_list.show_item_tags)
        self.assertEqual(list_data['show_item_url'], _found_list.show_item_url)
        self.assertEqual(list_data['access_level'], _found_list.access_level)


        _num_lists = get_number_user_lists(user_id=self.users['simon'].id)
        self.assertEqual(2, _num_lists)

        status, msg = edit_inventory_data(inventory_id=new_inventory_data["id"], inventory_type=__LIST__,
                                          user_id=list_data['to_user_id'], name="test_list_edited",
                                          description="test_list_edited",
                                          show_default_fields=0, show_item_images=0, show_item_type=0,
                                          show_item_location=0,
                                          show_item_tags=0, show_item_url=0, access_level=__PUBLIC__)


        _found_list, _found_userlist = find_inventory_by_slug(inventory_slug=slugify(list_data['name']),
                                                              inventory_owner_id=list_data['to_user_id'],
                                                              viewing_user_id=list_data['to_user_id'])

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
                                        user_id=list_data['to_user_id'])
        self.assertEqual(True, status)

        _num_lists = get_number_user_lists(user_id=self.users['simon'].id)
        self.assertEqual(1, _num_lists)


if __name__ == '__main__':
    unittest.main()
