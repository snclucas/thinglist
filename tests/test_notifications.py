import unittest

from database.database_functions import get_all_user_notifications, add_user_notification, \
    get_number_of_user_notifications, delete_notification_by_id
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

    @classmethod
    def tearDownClass(cls):
        for user_name, user in cls.users.items():
            _ret = 1
            _ret = remove_user_by_id(user_id=user.id)

    def test_create_notification(self):
        _user_notifications = get_all_user_notifications(user_id=self.users['simon'].id)
        self.assertEqual(0, len(_user_notifications))

        _num_notifications = get_number_of_user_notifications(user_id=self.users['simon'].id)
        self.assertEqual(0, _num_notifications)

        # invalid input
        _new_notification_id, msh = add_user_notification(to_user_id=None, # noqa
                                                          from_user_id=self.users['dave'].id,
                                                          message="test notification")

        self.assertIsNone(_new_notification_id)

        _new_notification_id, msh = add_user_notification(to_user_id=self.users['simon'].id,
                                                          from_user_id=self.users['dave'].id,
                                                          message=None) # noqa

        self.assertIsNone(_new_notification_id)

        _new_notification_id, msh = add_user_notification(to_user_id=self.users['simon'].id,
                                                          from_user_id=self.users['dave'].id,
                                                          message="test notification")

        _user_notifications = get_all_user_notifications(user_id=self.users['simon'].id)
        self.assertEqual(1, len(_user_notifications))

        _num_notifications = get_number_of_user_notifications(user_id=self.users['simon'].id)
        self.assertEqual(1, _num_notifications)

        _ret = delete_notification_by_id(notification_id=_new_notification_id, user=self.users['simon'])

    def test_delete_notification(self):
        _user_notifications = get_all_user_notifications(user_id=self.users['simon'].id)
        self.assertEqual(0, len(_user_notifications))

        _num_notifications = get_number_of_user_notifications(user_id=self.users['simon'].id)
        self.assertEqual(0, _num_notifications)

        _new_notification_id, msh = add_user_notification(to_user_id=self.users['simon'].id,
                                                          from_user_id=self.users['dave'].id,
                                                          message="test notification")

        self.assertIsNotNone(_new_notification_id)

        _num_notifications = get_number_of_user_notifications(user_id=self.users['simon'].id)
        self.assertEqual(1, _num_notifications)

        _ret = delete_notification_by_id(notification_id=_new_notification_id, user=self.users['simon'])

        _num_notifications = get_number_of_user_notifications(user_id=self.users['simon'].id)
        self.assertEqual(0, _num_notifications)


if __name__ == '__main__':
    unittest.main()
