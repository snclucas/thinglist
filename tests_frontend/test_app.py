# Import sys module for modifying Python's runtime environment
import sys
# Import os module for interacting with the operating system
import os

from flask import url_for, Flask

# Add the parent directory to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import the Flask app instance from the main app file
from app import app, db
# Import pytest for writing and running tests
import pytest


def test_home(client):
    """Test the home route."""

    # Create a test client using the Flask application configured for testing
    with app.test_client() as test_client:
        response = test_client.get('/')
        #assert response.status_code == 200


    #response = app.get('/profile')
    #assert response.status_code == 200
    #assert response.json == {"message": "Hello, Flask!"}
