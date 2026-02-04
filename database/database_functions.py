from typing import Tuple

from sqlalchemy import ClauseElement

from app import db, app

def _commit() -> Tuple[bool, str]:
    try:
        db.session.commit()
        return True, "success"
    except Exception as error:  # noqa
        app.logger.error(f"Could not commit changes: {str(error)}")
        db.session.rollback()
        return False, "Could not edit list"


def _to_dict(object_: db.Model) -> dict:
    if isinstance(object_, dict):
        return object_
    _dict = object_.__dict__
    _dict.pop('_sa_instance_state', None)
    return _dict


def drop_then_create():
    try:
        db.drop_all()
        db.create_all()
        db.session.commit()
    except Exception as e:
        print(e)


def confirm_inventory_invite_():
    pass

def get_or_create(model, defaults=None, **kwargs):
    with app.app_context():
        instance = db.session.query(model).filter_by(**kwargs).first()
        if instance:
            return instance, True
        else:
            params = {k: v for k, v in kwargs.items() if not isinstance(v, ClauseElement)}
            params.update(defaults or {})
            instance = model(**params)
            try:
                db.session.add(instance)
                db.session.commit()

            except Exception as e:
                print(e)
                db.session.rollback()
                instance = db.session.query(model).filter_by(**kwargs).one()
                return instance, False
            else:
                return instance, True
