import unittest

from database.database_functions import add_user_by_details, remove_user_by_id, find_user_by_username, find_user_by_email, \
    find_user_by_id
from tests.test_parent import TestAppParent


class TestApp(TestAppParent):

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
