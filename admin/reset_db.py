from app import app
from database_utils import drop_then_create

with app.app_context():
    drop_then_create()
