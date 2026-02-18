
from admin.load_intial_data import load_fields, load_words, load_types
from app import app
from database_utils import drop_then_create


def refresh_database():
    with app.app_context():
        drop_then_create()

        _fields_added = load_fields()
        print(f'Added {_fields_added} fields:')

        _reserved_words_added = load_words()
        print(f'Added {_reserved_words_added} reserved words')

        _types_added = load_types()
        print(f'Added {_types_added} types')


if __name__ == '__main__':
    refresh_database()
    print('Database reset and initial data loaded')