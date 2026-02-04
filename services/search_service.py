from sqlalchemy import or_

from models import ItemField, Item, Location, ItemType
from services.field_service import FieldService
from services.tag_service import TagService
from app import app, db


class SearchService:

    @staticmethod
    def search_items(query: str, user_id: int):

        def _search_by_field_value(field_id: int, user_id: int, query: str):
            looking_for = '%{0}%'.format(query)
            with app.app_context():
                items_ = db.session.query(Item) \
                    .join(ItemField, ItemField.item_id == Item.id) \
                    .filter(ItemField.field_id == field_id) \
                    .filter(ItemField.user_id == user_id) \
                    .filter(ItemField.value.ilike(looking_for)).all()

                return items_

        items_arr = []
        with app.app_context():

            # see if there is a search modifier
            if ':' in query:
                search_modifier = query.split(':')[0]
                query = query.split(':')[1].strip()

                if search_modifier.lower() == 'location':
                    locations_ = Location.query \
                        .filter(Location.user_id == user_id) \
                        .filter(Location.name.ilike(query)).all()

                    for location in locations_:
                        loc_id_ = location.id
                        items_ = Item.query.filter(or_(
                            Item.location_id == loc_id_,
                            Item.specific_location == query
                        )
                        ).all()

                        if len(items_) > 0:
                            for item in items_:
                                items_arr.append(item.__dict__)

                    looking_for = '%{0}%'.format(query)
                    items_ = Item.query.filter(
                        Item.specific_location.ilike(looking_for)
                    ).all()

                    if len(items_) > 0:
                        for item in items_:
                            items_arr.append(item.__dict__)

                elif search_modifier.lower() == 'tags' or search_modifier.lower() == 'tag':
                    query = query.split(",")
                    q_ = Item.query

                    any_tags_found = False
                    for tag_ in query:
                        tag_ = tag_.strip()
                        tag_ = tag_.replace(" ", "@#$")
                        t_ = TagService.get_tag_by_str(tag_str=tag_)

                        if t_ is not None:
                            any_tags_found = True
                            q_ = q_.filter(Item.tags.contains(t_))

                    if any_tags_found:
                        items_ = q_.all()

                        if len(items_) > 0:
                            for item in items_:
                                items_arr.append(item.__dict__)

                elif search_modifier.lower() == 'type':
                    query = query.split(",")

                    types_ = ItemType.query \
                        .filter(ItemType.user_id == user_id) \
                        .filter(ItemType.name.like(query)).all()

                    type_ids = []
                    for type_ in types_:
                        type_ids.append(type_.id)

                    items_ = Item.query.filter(Item.user_id == user_id).filter(Item.item_type.in_([type_ids])).all()

                    if len(items_) > 0:
                        for item in items_:
                            items_arr.append(item.__dict__)

                else:  # we have a custom field
                    field_ = FieldService.find_field_by_name(field_name=search_modifier)
                    if field_ is not None:
                        field_id = field_.id
                        items_ = _search_by_field_value(field_id=field_id, user_id=user_id, query=query)

                        if len(items_) > 0:
                            for item in items_:
                                items_arr.append(item.__dict__)

            else:
                # search simple string
                looking_for = '%{0}%'.format(query)

                items_ = Item.query.filter(or_(
                    Item.name.ilike(looking_for),
                    Item.description.ilike(looking_for)
                )
                ).all()

                if len(items_) > 0:
                    for item in items_:
                        items_arr.append(item.__dict__)

            return items_arr

