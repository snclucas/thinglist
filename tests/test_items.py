import unittest

from database_functions import add_user_by_details, remove_user_by_id


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







if __name__ == '__main__':
    unittest.main()
