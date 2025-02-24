import unittest

from database_functions import add_user_by_details, remove_user_by_id, \
    get_or_add_new_location, get_all_user_locations, get_user_location_by_id, delete_locations, update_location_by_id

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

    def test_add_location(self):
        _num_inventories = len(get_all_user_locations(user_id=self.users['simon'].id))
        self.assertEqual(1, _num_inventories)

        _new_location_name = "simon_test_location"
        _new_location_description = "simon_test_location"
        _ret = get_or_add_new_location(location_name=_new_location_name, location_description=_new_location_description, to_user_id=self.users['simon'].id)
        self.assertEqual(True, _ret["status"])

        _num_inventories = len(get_all_user_locations(user_id=self.users['simon'].id))

        _new_location_id = _ret["id"]
        _new_location = get_user_location_by_id(location_id=_new_location_id, user_id=self.users['simon'].id)
        self.assertEqual(_new_location_name, _new_location["name"])
        self.assertEqual(_new_location_description, _new_location["description"])

        delete_locations(user_id=self.users['simon'].id, location_ids=[_new_location_id])
        _new_location = get_user_location_by_id(location_id=_new_location_id, user_id=self.users['simon'].id)
        self.assertIsNone(_new_location)

    def test_remove_location_when_user_removed(self):
        _temp_user = add_user_by_details(username='_temp_user', email='_temp_user@example.com',
                                                 password='password', fail_on_duplicate=False)
        _new_location_name = "_temp_user_location"
        _new_location_description = "_temp_user_location"
        _ret = get_or_add_new_location(location_name=_new_location_name, location_description=_new_location_description,
                                       to_user_id=_temp_user.id)
        self.assertEqual(True, _ret["status"])
        _new_location_id = _ret["id"]
        _new_location = get_user_location_by_id(location_id=_new_location_id, user_id=_temp_user.id)
        self.assertIsNotNone(_new_location)

        _ret = remove_user_by_id(user_id=_temp_user.id)
        _new_location = get_user_location_by_id(location_id=_new_location_id, user_id=_temp_user.id)
        self.assertIsNone(_new_location)


    def test_edit_location(self):
        _location_name = "simon_test_location"
        _location_description = "simon_test_location"
        _ret = get_or_add_new_location(location_name=_location_name, location_description=_location_description,
                                       to_user_id=self.users['simon'].id)
        self.assertEqual(True, _ret["status"])
        self.assertEqual(_location_name, _ret["name"])
        self.assertEqual(_location_description, _ret["description"])


        _new_location_id = _ret["id"]

        _new_location_name = "simon_test_location edited"
        _new_location_description = "simon_test_locationv edited"
        _new_location_data = {
            "id": _new_location_id,
            "name": _new_location_name,
            "description": _new_location_description
        }
        _ret = update_location_by_id(location_data=_new_location_data, user=self.users['simon'])

        _new_location = get_user_location_by_id(location_id=_new_location_id, user_id=self.users['simon'].id)
        self.assertIsNotNone(_new_location)
        self.assertEqual(_new_location_name, _new_location["name"])
        self.assertEqual(_new_location_description, _new_location["description"])


        delete_locations(user_id=self.users['simon'].id, location_ids=[_new_location_id])
        _new_location = get_user_location_by_id(location_id=_new_location_id, user_id=self.users['simon'].id)
        self.assertIsNone(_new_location)







if __name__ == '__main__':

    unittest.main()
