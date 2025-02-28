import unittest

from database.database_functions import add_user_by_details, remove_user_by_id, find_user_by_username, find_user_by_email, \
    find_user_by_id


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
            _ret = remove_user_by_id(user_id=user.id)


    def test_user_functions(cls):

        _user = find_user_by_id(user_id=cls.users['simon'].id)

        cls.assertEqual(_user.username, cls.users['simon'].username)
        cls.assertEqual(_user.email, cls.users['simon'].email)
        #cls.assertEqual(_user.token, cls.users['simon'].token)





        _user = find_user_by_username(username=cls.users['simon'].username)
        cls.assertEqual(_user.username, cls.users['simon'].username)
        cls.assertEqual(_user.email, cls.users['simon'].email)

        _user = find_user_by_email(email=cls.users['simon'].email)
        cls.assertEqual(_user.username, cls.users['simon'].username)
        cls.assertEqual(_user.email, cls.users['simon'].email)


        #_user = find_user_by_token(token=cls.users['simon'].token)
        #find_user(username_or_email=cls.users['simon'].username)
        #remove_user_by_id(user_id=cls.users['simon'].id)


if __name__ == '__main__':
    unittest.main()
