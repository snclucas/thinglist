
from typing import Dict, Any, List

from sqlalchemy.exc import IntegrityError
from app import db

from models import UserInventory


class UserInventoryService:
    def add_user_to_inventory(self, user_id: int, inventory_id: int, access_level: int = 0,
                              view: int = 0) -> UserInventory:
        # return existing membership early if present
        existing = db.session.query(UserInventory).filter_by(user_id=user_id, inventory_id=inventory_id).first()
        if existing:
            return existing

        rec = UserInventory(user_id=user_id, inventory_id=inventory_id, access_level=access_level, view=view)
        db.session.add(rec)
        try:
            db.session.commit()
            return rec
        except IntegrityError:
            db.session.rollback()
            # concurrent insert may have created the membership; try to fetch and return it
            existing = db.session.query(UserInventory).filter_by(user_id=user_id, inventory_id=inventory_id).first()
            if existing:
                return existing
            raise

    def remove_user_from_inventory(self, user_id: int, inventory_id: int) -> None:
        rec = db.session.query(UserInventory).filter_by(user_id=user_id, inventory_id=inventory_id).first()
        if not rec:
            raise ValueError("membership not found")
        db.session.delete(rec)
        db.session.commit()

    def list_members(self, inventory_id: int) -> List[UserInventory]:
        return db.session.query(UserInventory).filter_by(inventory_id=inventory_id).all()

    def update_membership(self, user_id: int, inventory_id: int, data: Dict[str, Any]) -> UserInventory:
        rec = db.session.query(UserInventory).filter_by(user_id=user_id, inventory_id=inventory_id).first()
        if not rec:
            raise ValueError("membership not found")
        for k, v in data.items():
            setattr(rec, k, v)
        db.session.commit()
        return rec


