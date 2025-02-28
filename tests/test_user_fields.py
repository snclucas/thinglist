import unittest

from database.database_functions import add_field, get_all_user_fields, delete_fields_from_db, \
    get_all_fields_include_users
from database.database_functions import add_user_by_details, remove_user_by_id


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

    @classmethod
    def tearDownClass(cls):
        for user_name, user in cls.users.items():
            _ret = remove_user_by_id(user_id=user.id)



    def test_add_user_field(self):

        for _field in self.fields_to_add_system:
            field_name = _field["field_name"]
            field_type = _field["field_type"]
            field, success = add_field(field_name=field_name, field_type=field_type, user_id=None)
            self.assertTrue(success)


        for _field in self.fields_to_add_simon:
            field_name = _field["field_name"]
            field_type = _field["field_type"]
            field, success = add_field(field_name=field_name, field_type=field_type, user_id=self.users['simon'].id)
            self.assertTrue(success)

        for _field in self.fields_to_add_dave:
            field_name = _field["field_name"]
            field_type = _field["field_type"]
            field, success = add_field(field_name=field_name, field_type=field_type, user_id=self.users['dave'].id)
            self.assertTrue(success)

        user_fields = list(get_all_user_fields(user_id=self.users['simon'].id))
        self.assertEqual(4, len(user_fields))

        for _retrieved_field in user_fields:
            _retrieved_field = _retrieved_field
            self.assertIn(_retrieved_field.field, [field["field_name"] for field in self.fields_to_add_simon])


        # delete 2 user fields
        _status_of_delete = delete_fields_from_db(user_id=self.users['simon'].id, field_ids=[field.id for field in user_fields][0:2])
        self.assertEqual(True, _status_of_delete)

        num_user_fields = list(get_all_user_fields(user_id=self.users['simon'].id))
        self.assertEqual(2, len(num_user_fields))

        # get all fields including system, should be 6 (2 user + 4 system)
        _all_fields_and_system = get_all_fields_include_users(user_id=self.users['simon'].id)
        self.assertEqual(6, len(_all_fields_and_system))


        # clean up and delete the system fields
        #_status_of_delete = delete_fields_from_db(user_id=None, field_ids=[field.id for field in _all_fields_and_system])



if __name__ == '__main__':
    unittest.main()
