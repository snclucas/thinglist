from flask import jsonify
from app import db, app


def _to_bool(value):
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).lower() in ('1', 'true', 'on', 'yes')


class PreferencesService:

    @staticmethod
    def update_preferences(data, current_user):
        public_profile = _to_bool(data.get('public_profile'))
        show_default_list = _to_bool(data.get('show_default_list'))

        try:
            # Adjust these assignments to match your user model
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
