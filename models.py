import re
import string
from random import choice
from secrets import token_urlsafe
from uuid import uuid4

from flask_login import UserMixin
from slugify import slugify
from sqlalchemy import UniqueConstraint, event, func
from sqlalchemy.orm import relationship

from app import db
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


def generate_short_id(num_of_chars: int):
    """Function to generate short_id of specified number of characters"""
    return ''.join(choice(string.ascii_letters+string.digits) for _ in range(num_of_chars))


class ReservedWords(db.Model):
    __tablename__ = "reserved_words"
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    word = db.Column(db.String(50), nullable=False, unique=True)



class User(UserMixin, db.Model):
    def __init__(self, **kwargs):
        # set up cols for user
        for k, v in kwargs.items():
            setattr(self, k, v)
        # create watchlist: watchlist and user will both get their ids
        # created at the same time when the session creating User
        # is committed, and watchlist will have the user_id key too
        self.preferences = Preferences()


    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    #ident = db.Column(db.String(36), nullable=False, unique=True, index=True, default=lambda: str(uuid4()))
    username = db.Column(db.String(50), nullable=True, unique=True)
    password = db.Column(db.String(255), nullable=False, server_default='')
    email = db.Column(db.String(255), nullable=False, unique=True)
    preferences = db.relationship("Preferences", uselist=False, backref="users", lazy='joined', passive_deletes=True)
    is_active = db.Column(db.Boolean(), default=True)
    is_banned = db.Column(db.Boolean(), default=False)
    is_suspended = db.Column(db.Boolean(), default=False)
    is_admin = db.Column(db.Boolean(), default=False)
    user_created = db.Column(db.DateTime(), default=func.now())
    email_confirmed_at = db.Column(db.DateTime(), default=None)
    inventories = db.relationship('Inventory', secondary='inventory_users',
                                  back_populates='users', cascade="all,delete", lazy='selectin', passive_deletes=True)

    notifications = db.relationship('Notification', backref='users', cascade="all,delete", lazy='selectin', passive_deletes=True)
    activated = db.Column(db.Boolean(), nullable=True, unique=False, default=False)
    token = db.Column(db.String(255), nullable=True, unique=False)
    token_expires = db.Column(db.DateTime(), default=func.now())
    profile_text = db.Column(db.String(255), nullable=True, unique=False)


class Preferences(db.Model):
    __tablename__ = "preferences"
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    default_public = db.Column(db.Boolean(), default=False)
    public_profile = db.Column(db.Boolean(), default=False)
    show_default_list = db.Column(db.Boolean(), default=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'))

class Notification(db.Model):
    __tablename__ = "notifications"
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    date = db.Column(db.DateTime(), default=func.now())
    text = db.Column(db.String(255), nullable=True, unique=False)
    from_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    from_user_username = db.Column(db.String(255), nullable=True, unique=False)


class FieldTemplate(db.Model):
    __tablename__ = "field_templates"
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    ident = db.Column(db.String(36), nullable=False, unique=True, index=True, default=lambda: str(uuid4()))
    name = db.Column(db.String(50))
    fields = db.relationship('Field', secondary='fieldtemplate_fields',
                             back_populates='field_templates', lazy='subquery')
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'))


@event.listens_for(FieldTemplate, 'before_insert')
def create_item_short_code(mapper, connect, target):
    target.ident = generate_short_id(num_of_chars=32)


class TemplateField(db.Model):
    __tablename__ = "fieldtemplate_fields"
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    field_id = db.Column(db.Integer, db.ForeignKey('fields.id', ondelete='CASCADE'))
    template_id = db.Column(db.Integer, db.ForeignKey('field_templates.id', ondelete='CASCADE'))
    order = db.Column(db.Integer, nullable=False, default=0)


class Field(db.Model):
    __tablename__ = "fields"
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    field = db.Column(db.String(255), nullable=True, unique=False)
    slug = db.Column(db.String(255), nullable=True, unique=True)
    type = db.Column(db.String(255), nullable=True, unique=False)
    data = db.Column(db.String(255), nullable=True, unique=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'))
    items = db.relationship('Item', secondary='item_fields', back_populates='fields')
    field_templates = db.relationship('FieldTemplate', secondary='fieldtemplate_fields', back_populates='fields')
    ident = db.Column(db.String(36), nullable=False, unique=True, index=True, default=lambda: str(uuid4()))


class Location(db.Model):
    __tablename__ = "locations"
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(50), nullable=True, unique=False)
    description = db.Column(db.String(50), nullable=True, unique=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'))
    ident = db.Column(db.String(36), nullable=False, unique=True, index=True, default=lambda: str(uuid4()))


class Inventory(db.Model):
    __tablename__ = "inventories"
    __searchable__ = ['name', 'description']
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(50))
    slug = db.Column(db.String(50), nullable=True, unique=True)
    ident = db.Column(db.String(36), nullable=False, unique=True, index=True, default=lambda: str(uuid4()))
    description = db.Column(db.String(255))
    owner_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    users = db.relationship('User', secondary='inventory_users', back_populates='inventories', lazy='subquery', cascade="all,delete")
    items = db.relationship('Item', secondary='inventory_items', back_populates='inventories', lazy='subquery', cascade="all,delete")
    default_fields = db.Column(db.String(1000), default="-1")
    field_template = db.Column(db.Integer, db.ForeignKey('field_templates.id'), nullable=True)
    access_level = db.Column(db.Integer, nullable=False, unique=False, default=False)
    token = db.Column(db.String(255), nullable=True, unique=False)
    short_code = db.Column(db.String(255), nullable=True, unique=True)
    type = db.Column(db.Integer, nullable=True, unique=False, default=1)
    show_default_fields = db.Column(db.Boolean(), nullable=False, unique=False, default=True)
    show_item_images = db.Column(db.Boolean(), nullable=False, unique=False, default=True)
    show_item_location = db.Column(db.Boolean(), nullable=False, unique=False, default=True)
    show_item_type = db.Column(db.Boolean(), nullable=False, unique=False, default=True)
    show_item_tags = db.Column(db.Boolean(), nullable=False, unique=False, default=True)
    show_item_url = db.Column(db.Boolean(), nullable=False, unique=False, default=True)
    is_default = db.Column(db.Boolean(), nullable=False, unique=False, default=False)
    inventory_token = db.Column(db.String(255), nullable=True, unique=True)
    invtags = db.relationship('Invtag', secondary='inventory_tags', back_populates='inventories', lazy='subquery')

    __table_args__ = (UniqueConstraint('slug', 'owner_id', name='_inventory_slug_owner_uc'),)

@event.listens_for(Inventory, 'before_insert')
def list_before_insert(mapper, connect, target):
    target.inventory_token = token_urlsafe()
    target.short_code = generate_short_id(num_of_chars=6)
    base = slugify(target.name or "")[:50]  # trim to column length if desired
    target.slug = _make_unique_slug(base, target.owner_id)

def _make_unique_slug(base_slug: str, owner_id: int):
    """
    Return a unique slug for `owner_id` by appending -N if needed.
    """
    session = db.session
    if not base_slug:
        base_slug = "inventory"
    pattern = f"{base_slug}%"
    rows = session.query(Inventory.slug).filter(
        Inventory.owner_id == owner_id,
        Inventory.slug.like(pattern)
    ).all()
    existing = [r[0] for r in rows if r[0]]
    if base_slug not in existing:
        return base_slug

    max_n = 1
    for s in existing:
        m = re.match(rf"^{re.escape(base_slug)}-(\d+)$", s)
        if m:
            n = int(m.group(1))
            if n >= max_n:
                max_n = n + 1
        elif s == base_slug:
            max_n = max(max_n, 2)

    return f"{base_slug}-{max_n}"


class Relateditems(db.Model):
    __tablename__ = "related_items"
    item_id = db.Column(db.Integer, db.ForeignKey('items.id', ondelete='CASCADE'), primary_key=True)
    related_item_id = db.Column(db.Integer, db.ForeignKey('items.id', ondelete='CASCADE'), primary_key=True)


class Item(db.Model):
    __tablename__ = "items"
    __searchable__ = ['name', 'description']

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    item_type = db.Column(db.Integer, db.ForeignKey('item_type.id'), nullable=False)
    item_type_obj = relationship("ItemType", primaryjoin="ItemType.id==Item.item_type", lazy="selectin", viewonly=True)
    name = db.Column(db.String(255), nullable=False, unique=False)
    slug = db.Column(db.String(255), nullable=True, unique=False)
    ident = db.Column(db.String(36), nullable=False, unique=True, index=True, default=lambda: str(uuid4()))
    description = db.Column(db.String(10000), nullable=True, unique=False)
    url = db.Column(db.String(100), nullable=True, unique=False)
    quantity = db.Column(db.Integer, nullable=False, unique=False, default=1)
    inventories = db.relationship('Inventory', secondary='inventory_items', back_populates='items', lazy='subquery')
    tags = db.relationship('Tag', secondary='item_tags', back_populates='items', lazy='subquery')
    location_id = db.Column(db.Integer, db.ForeignKey('locations.id'), default=None, nullable=True)
    # relationship so you can eager-load Item.location
    location = relationship("Location", primaryjoin="Location.id==Item.location_id", lazy="selectin")
    specific_location = db.Column(db.String(50), nullable=True, unique=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    images = db.relationship('Image', secondary='item_images', back_populates='items', lazy='subquery')
    main_image = db.Column(db.String(255), nullable=True, unique=False)
    fields = db.relationship('Field', secondary='item_fields', back_populates='items', lazy='subquery')
    short_code = db.Column(db.String(255), nullable=True, unique=True)
    item_token = db.Column(db.String(255), nullable=True, unique=True)

    # this relationship is used for persistence
    related_items = db.relationship("Item", secondary=Relateditems.__table__,
                                    primaryjoin=id == Relateditems.item_id,
                                    secondaryjoin=id == Relateditems.related_item_id,
                                    )


@event.listens_for(Item, 'before_insert')
def create_item_short_code(mapper, connect, target):
    # target is an instance of Table
    target.short_code = generate_short_id(num_of_chars=6)
    target.ident = generate_short_id(num_of_chars=32)



class ItemField(db.Model):
    __tablename__ = "item_fields"
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    field_id = db.Column(db.Integer, db.ForeignKey('fields.id', ondelete='CASCADE'))
    item_id = db.Column(db.Integer, db.ForeignKey('items.id', ondelete='CASCADE'))
    ident = db.Column(db.String(36), nullable=False, unique=True, index=True, default=lambda: str(uuid4()))
    value = db.Column(db.String(255), nullable=True, unique=False)
    show = db.Column(db.Boolean(), nullable=True, unique=False, default=False)
    user_id = db.Column(db.Integer, nullable=True, unique=False)
    __table_args__ = (UniqueConstraint('field_id', 'item_id', name='_item_field_uc'),
                      )

class Image(db.Model):
    __tablename__ = "images"
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    image_filename = db.Column(db.String(255), nullable=True, unique=False)
    ident = db.Column(db.String(36), nullable=False, unique=True, index=True, default=lambda: str(uuid4()))
    items = db.relationship('Item', secondary='item_images', back_populates='images',
                            cascade="all,delete", lazy='subquery')
    # AI user_id = db.Column(db.Integer, db.ForeignKey('users.id'), primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)


class ItemImage(db.Model):
    __tablename__ = "item_images"
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    image_id = db.Column(db.Integer, db.ForeignKey('images.id', ondelete='CASCADE'))
    item_id = db.Column(db.Integer, db.ForeignKey('items.id', ondelete='CASCADE'))


class UserInventory(db.Model):
    __tablename__ = "inventory_users"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    inventory_id = db.Column(db.Integer, db.ForeignKey('inventories.id'))
    access_level = db.Column(db.Integer, default=0)
    view = db.Column(db.Integer, default=0)
    __table_args__ = (UniqueConstraint('user_id', 'inventory_id', name='_user_id_inventory_id_uc'),)


class InventoryItem(db.Model):
    __tablename__ = "inventory_items"
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    inventory_id = db.Column(db.Integer, db.ForeignKey('inventories.id'))
    item_id = db.Column(db.Integer, db.ForeignKey('items.id', ondelete='CASCADE'))
    access_level = db.Column(db.Integer, default=0)
    is_link = db.Column(db.Boolean(), default=False)
    __table_args__ = (UniqueConstraint('item_id', 'inventory_id', name='_item_id_inventory_id_uc'),)


class ItemType(db.Model):
    __tablename__ = "item_type"
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(255), nullable=True, unique=False)
    slug = db.Column(db.String(255), nullable=True, unique=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=True)
    #ident = db.Column(db.String(36), nullable=False, unique=True, index=True, default=lambda: str(uuid4()))
    __table_args__ = (UniqueConstraint('slug', 'user_id', name='_name_userid_uc'),)

@event.listens_for(ItemType, 'before_insert')
def create_item_type_slug(mapper, connect, target):
    # Guard against None or non-string names which can cause slugify to raise
    name_val = target.name if target.name is not None else ""
    try:
        target.slug = slugify(name_val)
    except Exception:
        # Fallback: coerce to str and retry; if that fails use a safe default
        try:
            target.slug = slugify(str(name_val))
        except Exception:
            target.slug = "none"


class Tag(db.Model):
    __tablename__ = "tags"
    __searchable__ = ['tag']
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    tag = db.Column(db.String(50), nullable=True, unique=True)
    ident = db.Column(db.String(36), nullable=False, unique=True, index=True, default=lambda: str(uuid4()))
    items = db.relationship('Item', secondary='item_tags', back_populates='tags', cascade="all,delete")
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=True)


class Invtag(db.Model):
    __tablename__ = "invtags"
    __searchable__ = ['tag']
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    tag = db.Column(db.String(50), nullable=True, unique=True)
    inventories = db.relationship('Inventory', secondary='inventory_tags', back_populates='invtags', cascade="all,delete")
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=True)




class ItemTag(db.Model):
    __tablename__ = "item_tags"
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    item_id = db.Column(db.Integer, db.ForeignKey('items.id', ondelete='CASCADE'))
    tag_id = db.Column(db.Integer, db.ForeignKey('tags.id', ondelete='CASCADE'))
    __table_args__ = (UniqueConstraint('tag_id', 'item_id', name='_item_tag_uc'),
                      )


class InventoryTag(db.Model):
    __tablename__ = "inventory_tags"
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    inventory_id = db.Column(db.Integer, db.ForeignKey('inventories.id', ondelete='CASCADE'))
    tag_id = db.Column(db.Integer, db.ForeignKey('invtags.id', ondelete='CASCADE'))


class UserLocation(db.Model):
    __tablename__ = "user_location"
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'))
    location_id = db.Column(db.Integer, db.ForeignKey('locations.id', ondelete='CASCADE'))


from sqlalchemy import Index
#
# # Inventory: common lookup by owner and slug; also owner alone
# Index('ix_inventories_owner_id', Inventory.__table__.c.owner_id)
# Index('ix_inventories_owner_slug', Inventory.__table__.c.owner_id, Inventory.__table__.c.slug)
#
# # Item: lookups by user, type, location and short_code
# Index('ix_items_user_id', Item.__table__.c.user_id)
# Index('ix_items_item_type', Item.__table__.c.item_type)
# Index('ix_items_location_id', Item.__table__.c.location_id)
#
# # Notifications: filter by sender and recent date ordering
# Index('ix_notifications_from_user_id', Notification.__table__.c.from_user_id)
# Index('ix_notifications_date', Notification.__table__.c.date)
#
# # Associations and join tables: index the FK columns used in joins/filters
# Index('ix_item_fields_field_id', ItemField.__table__.c.field_id)
# Index('ix_item_fields_item_id', ItemField.__table__.c.item_id)
#
Index('ix_inventory_items_inventory_id', InventoryItem.__table__.c.inventory_id)
Index('ix_inventory_items_item_id', InventoryItem.__table__.c.item_id)
#
Index('ix_inventory_users_user_id', UserInventory.__table__.c.user_id)
Index('ix_inventory_users_inventory_id', UserInventory.__table__.c.inventory_id)
#
# Index('ix_item_images_item_id', ItemImage.__table__.c.item_id)
# Index('ix_item_images_image_id', ItemImage.__table__.c.image_id)
#
# Index('ix_item_tags_item_id', ItemTag.__table__.c.item_id)
# Index('ix_item_tags_tag_id', ItemTag.__table__.c.tag_id)
#
# Index('ix_inventory_tags_inventory_id', InventoryTag.__table__.c.inventory_id)
# Index('ix_inventory_tags_tag_id', InventoryTag.__table__.c.tag_id)
#
# Index('ix_related_items_item_id', Relateditems.__table__.c.item_id)
# Index('ix_related_items_related_item_id', Relateditems.__table__.c.related_item_id)
#
# # Users and preferences: common lookups
# Index('ix_preferences_user_id', Preferences.__table__.c.user_id)
# Index('ix_users_email', User.__table__.c.email)  # unique already creates index; explicit for clarity
# Index('ix_users_username', User.__table__.c.username)
#
# # Fields, types, tags, locations: per-user lookups and joins
# Index('ix_fields_user_id', Field.__table__.c.user_id)
# Index('ix_field_templates_user_id', FieldTemplate.__table__.c.user_id)
# Index('ix_item_type_user_id', ItemType.__table__.c.user_id)
# Index('ix_locations_user_id', Location.__table__.c.user_id)
# Index('ix_images_user_id', Image.__table__.c.user_id)
# Index('ix_tags_user_id', Tag.__table__.c.user_id)
# Index('ix_invtags_user_id', Invtag.__table__.c.user_id)
#
# # Searchable ordering / frequently-sorted columns
# Index('ix_inventories_ident', Inventory.__table__.c.ident)
# Index('ix_items_ident', Item.__table__.c.ident)