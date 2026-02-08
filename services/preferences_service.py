from flask import jsonify
from app import db, app
from utils import _to_bool


class PreferencesService:

    @staticmethod
    def update_preferences(data, current_user):
        public_profile = _to_bool(data.get('public_profile'))
        show_default_list = _to_bool(data.get('show_default_list'))

        try:
            current_user.preferences.public_profile = public_profile
            current_user.preferences.show_default_list = show_default_list
            db.session.commit()
        except Exception as e:
            app.logger.exception('Failed to update preferences')
            db.session.rollback()
            return jsonify(success=False, error='db_error'), 500

        return jsonify(success=True, preferences={
            'public_profile': public_profile,
            'show_default_list': show_default_list
        })
