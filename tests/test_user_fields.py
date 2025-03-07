import unittest

from database.database_functions import add_field, get_all_user_fields, delete_fields_from_db, \
    get_all_user_and_system_fields, get_all_system_fields
from database.database_functions import add_user_by_details, remove_user_by_id
from tests.test_parent import TestAppParent


class TestApp(TestAppParent):

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

        num_system_fields = list(get_all_system_fields())

        # get all fields including system, should be 6 (2 user + 4 system)
        _all_fields_and_system = get_all_user_and_system_fields(user_id=self.users['simon'].id)
        self.assertEqual(2+len(num_system_fields), len(_all_fields_and_system))


        # clean up and delete the system fields
        #_status_of_delete = delete_fields_from_db(user_id=None, field_ids=[field.id for field in _all_fields_and_system])



if __name__ == '__main__':
    unittest.main()
