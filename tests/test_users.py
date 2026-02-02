import unittest

from models import User
from tests.test_parent import TestAppParent

from app import db
from services.thinglist_services import UserService


class TestApp(TestAppParent):

    def setUpClass(self):
        super().setUpClass()
        self.users = {'testuser': UserService.add_user_by_details(username='testuser',email='testuser@example.com', password='password')}
        self.db = db

    def tearDown(self):
        for user in self.users.values():
            UserService.remove_user_by_id(user_id=user.id)
        super().tearDown()

    def test_user_functions(self):

        _user = find_user_by_id(user_id=self.users['testuser'].id)

        self.assertEqual(_user.username, self.users['testuser'].username)
        self.assertEqual(_user.email, self.users['testuser'].email)
        #cls.assertEqual(_user.token, cls.users['simon'].token)





        _user = UserService.get_user_by_username(username=self.users['testuser'].username)
        self.assertEqual(_user.username, self.users['testuser'].username)
        self.assertEqual(_user.email, self.users['testuser'].email)

        _user = UserService.get_user_by_email(email=self.users['testuser'].email)
        self.assertEqual(_user.username, self.users['testuser'].username)
        self.assertEqual(_user.email, self.users['testuser'].email)


        #_user = find_user_by_token(token=cls.users['simon'].token)
        #find_user(username_or_email=cls.users['simon'].username)
        #remove_user_by_id(user_id=cls.users['simon'].id)

    def test_activate_user_with_valid_id_activates_user(self):
        user = self.users['testuser']
        user.activated = False
        self.db.session.commit()

        result = activate_user(user_id=user.id)

        self.assertTrue(result)
        updated_user = self.db.session.query(User).filter(User.id == user.id).one()
        self.assertTrue(updated_user.activated)


    def test_activate_user_with_already_activated_user_returns_true(self):
        user = self.users['simon']
        user.activated = True
        self.db.session.commit()

        result = activate_user(user_id=user.id)

        self.assertTrue(result)


    def test_activate_user_with_nonexistent_user_returns_false(self):
        result = activate_user(user_id=99999)

        self.assertFalse(result)


    def test_activate_user_with_none_user_id_returns_false(self):
        result = activate_user(user_id=None)

        self.assertFalse(result)


if __name__ == '__main__':
    unittest.main()
