import unittest

from database.database_functions import get_user_location_by_id, \
    delete_locations, update_location_by_id, get_number_user_locations
from services.thinglist_services import LocationService, UserService
from tests.test_parent import TestAppParent


class TestApp(TestAppParent):

    def test_add_location(self):
        _num_inventories = len(LocationService.get_all_user_locations(user_id=self.users['simon'].id))
        self.assertEqual(1, _num_inventories)

        _new_location_name = "simon_test_location"
        _new_location_description = "simon_test_location"
        _ret = LocationService.get_or_add_new_location(location_name=_new_location_name, location_description=_new_location_description, to_user_id=self.users['simon'].id)
        self.assertEqual(True, _ret["status"])





        _num_inventories = len(LocationService.get_all_user_locations(user_id=self.users['simon'].id))
        self.assertEqual(2, _num_inventories)

        _num_inventories = get_number_user_locations(user_id=self.users['simon'].id)
        self.assertEqual(2, _num_inventories)





        _new_location_id = _ret["id"]
        _new_location = get_user_location_by_id(location_id=_new_location_id, user_id=self.users['simon'].id)
        self.assertEqual(_new_location_name, _new_location["name"])
        self.assertEqual(_new_location_description, _new_location["description"])

        delete_locations(user_id=self.users['simon'].id, location_ids=[_new_location_id])
        _new_location = get_user_location_by_id(location_id=_new_location_id, user_id=self.users['simon'].id)
        self.assertIsNone(_new_location)

    def test_remove_location_when_user_removed(self):
        _temp_user = UserService.add_user_by_details(username='_temp_user', email='_temp_user@example.com',
                                                 password='password', fail_on_duplicate=False)
        _new_location_name = "_temp_user_location"
        _new_location_description = "_temp_user_location"
        _ret = LocationService.get_or_add_new_location(location_name=_new_location_name, location_description=_new_location_description,
                                       to_user_id=_temp_user.id)
        self.assertEqual(True, _ret["status"])
        _new_location_id = _ret["id"]
        _new_location = get_user_location_by_id(location_id=_new_location_id, user_id=_temp_user.id)
        self.assertIsNotNone(_new_location)

        _ret = UserService.delete_user_by_id(user_id=_temp_user.id)
        _new_location = get_user_location_by_id(location_id=_new_location_id, user_id=_temp_user.id)
        self.assertIsNone(_new_location)


    def test_edit_location(self):
        _location_name = "simon_test_location"
        _location_description = "simon_test_location"
        _ret = LocationService.get_or_add_new_location(location_name=_location_name, location_description=_location_description,
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
