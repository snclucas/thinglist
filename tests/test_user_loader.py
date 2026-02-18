import os
import pytest

# Ensure test DB is configured before importing app so startup validations pass
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
os.environ['DEBUG'] = '1'

from app import app, db
from models import User


@pytest.fixture(scope='function')
def test_app():
    app.config['TESTING'] = True
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ['DATABASE_URL']

    # Rebind DB to use in-memory SQLite for this test
    with app.app_context():
        db.engine.dispose()
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


def test_load_user_valid_and_invalid(test_app):
    with test_app.app_context():
        # Create an active user
        user = User(username='testuser', email='test@example.com', password='hashed', is_active=True)
        db.session.add(user)
        db.session.commit()

        # user.id should be set
        uid = user.id
        # Import the load_user function by referencing the login manager
        # routes.auth_routes imports email_utils which in turn imports app.mail; to avoid import-time side-effects
        # insert a small stub for email_utils to satisfy imports during this unit test
        import sys, types
        if 'email_utils' not in sys.modules:
            sys.modules['email_utils'] = types.SimpleNamespace(send_email=lambda *a, **k: None)
        from routes.auth_routes import load_user

        # Valid id (int)
        loaded = load_user(str(uid))
        assert loaded is not None
        assert loaded.id == uid

        # Invalid id: non-numeric
        assert load_user('not-an-int') is None

        # Invalid id: nonexistent
        assert load_user('99999') is None

