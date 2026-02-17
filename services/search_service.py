from sqlalchemy import or_, func

import bleach

from models import ItemField, Item, Location, ItemType, Tag, ItemTag
from services.field_service import FieldService
from app import app, db

# Scoring weights (tunable via app config)


class SearchService:

    @staticmethod
    def _get_weights():
        # read from app config with sensible defaults
        return dict(
            NAME_WEIGHT=int(app.config.get('SEARCH_WEIGHT_NAME', 8)),
            TAG_WEIGHT=int(app.config.get('SEARCH_WEIGHT_TAG', 6)),
            DESCRIPTION_WEIGHT=int(app.config.get('SEARCH_WEIGHT_DESCRIPTION', 2)),
            LOCATION_WEIGHT=int(app.config.get('SEARCH_WEIGHT_LOCATION', 4)),
            TYPE_WEIGHT=int(app.config.get('SEARCH_WEIGHT_TYPE', 4)),
            FIELD_WEIGHT=int(app.config.get('SEARCH_WEIGHT_FIELD', 3)),
        )

    @staticmethod
    def _ids_from_free_text(user_id: int, qtext: str):
        """Return set of Item IDs matching free-text across name/description/tags/locations/fields."""
        ids = set()
        if not qtext:
            return ids
        looking_for = f"%{qtext}%"
        with app.app_context():
            # name/description
            try:
                rows = db.session.query(Item.id).filter(or_(
                    Item.name.ilike(looking_for),
                    Item.description.ilike(looking_for)
                )).all()
                ids.update(r[0] for r in rows)
            except Exception:
                db.session.rollback()

            # tags
            try:
                normalized = qtext.replace(" ", "@#$").lower()
                tag_rows = db.session.query(ItemTag.item_id).join(Tag, ItemTag.tag_id == Tag.id).filter(
                    or_(
                        func.lower(Tag.tag).like(f"%{qtext.lower()}%"),
                        func.lower(Tag.tag).like(f"%{normalized}%")
                    )
                ).all()
                ids.update(r[0] for r in tag_rows)
            except Exception:
                db.session.rollback()

            # locations
            try:
                loc_rows = db.session.query(Item.id).join(Location, Item.location_id == Location.id).filter(
                    Location.name.ilike(looking_for)
                ).all()
                ids.update(r[0] for r in loc_rows)

                spec_rows = db.session.query(Item.id).filter(Item.specific_location.ilike(looking_for)).all()
                ids.update(r[0] for r in spec_rows)
            except Exception:
                db.session.rollback()

            # custom fields
            try:
                if user_id is not None:
                    field_rows = db.session.query(ItemField.item_id).filter(
                        ItemField.user_id == user_id,
                        ItemField.value.ilike(looking_for)
                    ).all()
                    ids.update(r[0] for r in field_rows)
            except Exception:
                db.session.rollback()

        return ids

    @staticmethod
    def _make_item_dto(item: Item, snippet_html: str = None):
        # compact DTO used by the UI
        dto = {
            'id': item.id,
            'name': item.name,
            'slug': item.slug,
            'description': item.description,
            'url': item.url,
            'inventories': [{'name': inv.name, 'slug': inv.slug} for inv in item.inventories],
            'tags': [t.tag.replace("@#$", " ") for t in item.tags],
            'location': {'name': item.location.name if getattr(item, 'location', None) else None,
                         'specific': item.specific_location},
            'type': getattr(item, 'item_type_obj', None).name if getattr(item, 'item_type_obj', None) else None
        }
        if snippet_html:
            dto['snippet'] = snippet_html
        return dto

    @staticmethod
    def _highlight_text(text: str, terms: list):
        if not text:
            return ''
        import re
        # first, sanitize raw text to remove any tags so we don't inadvertently keep HTML
        safe_text = bleach.clean(text, tags=[], strip=True)
        # build regex to match terms case-insensitively, escape terms
        patterns = [re.escape(t) for t in sorted(set(terms), key=lambda x: -len(x)) if t]
        if not patterns:
            return bleach.clean(safe_text, tags=[], strip=True)
        regex = re.compile('(' + '|'.join(patterns) + ')', re.IGNORECASE)
        highlighted = regex.sub(r"<mark>\1</mark>", safe_text)
        # allow only <mark> tags in the resulting snippet
        return bleach.clean(highlighted, tags=['mark'], strip=True)

    @staticmethod
    def search_items(query: str, user_id: int, page: int = 1, per_page: int = 20):
        """
        Supports queries containing multiple modifiers and free text.
        Returns dict: {items: [dtos], total: int, page: int, per_page: int}
        """

        def _ids_from_free_text(qtext: str):
            ids = set()
            if not qtext:
                return ids
            looking_for = f"%{qtext}%"
            # name/description
            try:
                rows = db.session.query(Item.id).filter(or_(
                    Item.name.ilike(looking_for),
                    Item.description.ilike(looking_for)
                )).all()
                ids.update(r[0] for r in rows)
            except Exception:
                db.session.rollback()

            # tags
            try:
                normalized = qtext.replace(" ", "@#$").lower()
                tag_rows = db.session.query(ItemTag.item_id).join(Tag, ItemTag.tag_id == Tag.id).filter(
                    or_(
                        func.lower(Tag.tag).like(f"%{qtext.lower()}%"),
                        func.lower(Tag.tag).like(f"%{normalized}%")
                    )
                ).all()
                ids.update(r[0] for r in tag_rows)
            except Exception:
                db.session.rollback()

            # locations
            try:
                loc_rows = db.session.query(Item.id).join(Location, Item.location_id == Location.id).filter(
                    Location.name.ilike(looking_for)
                ).all()
                ids.update(r[0] for r in loc_rows)

                spec_rows = db.session.query(Item.id).filter(Item.specific_location.ilike(looking_for)).all()
                ids.update(r[0] for r in spec_rows)
            except Exception:
                db.session.rollback()

            # custom fields
            try:
                # only search user-specific custom fields when user_id provided
                if user_id is not None:
                    field_rows = db.session.query(ItemField.item_id).filter(
                        ItemField.user_id == user_id,
                        ItemField.value.ilike(looking_for)
                    ).all()
                    ids.update(r[0] for r in field_rows)
            except Exception:
                db.session.rollback()

            return ids

        with app.app_context():
            app.logger.debug(f"SearchService.search_items called: q={query!r} user_id={user_id} page={page} per_page={per_page}")
            if not query or not query.strip():
                app.logger.debug("SearchService: empty query, returning no results")
                return {'items': [], 'total': 0, 'page': page, 'per_page': per_page}

            import shlex
            tokens = []
            try:
                tokens = shlex.split(query)
            except Exception:
                tokens = query.split()

            app.logger.debug(f"Parsed tokens: {tokens}")

            # parse tokens into modifiers and free text
            modifiers = {
                'tags': [],
                'locations': [],
                'types': [],
                'fields': []
            }
            free_terms = []

            for tok in tokens:
                if ':' in tok:
                    key, val = tok.split(':', 1)
                    key_l = key.lower()
                    if key_l in ('tag', 'tags'):
                        vals = [v.strip() for v in val.split(',') if v.strip()]
                        modifiers['tags'].extend(vals)
                    elif key_l in ('location', 'locations'):
                        vals = [v.strip() for v in val.split(',') if v.strip()]
                        modifiers['locations'].extend(vals)
                    elif key_l in ('type', 'types'):
                        vals = [v.strip() for v in val.split(',') if v.strip()]
                        modifiers['types'].extend(vals)
                    else:
                        modifiers['fields'].append((key, val))
                else:
                    free_terms.append(tok)

            # collect highlight terms (used for snippet highlighting)
            highlight_terms = []
            highlight_terms.extend(free_terms)
            for t in modifiers['tags']:
                highlight_terms.append(t)
            for l in modifiers['locations']:
                highlight_terms.append(l)
            for ty in modifiers['types']:
                highlight_terms.append(ty)
            for (fn, fv) in modifiers['fields']:
                highlight_terms.append(fv)

            # Compute ID sets per constraint
            all_sets = []

            # Tags: AND semantics among tags
            if modifiers['tags']:
                normalized_tags = [t.replace(' ', '@#$').lower() for t in modifiers['tags']]
                try:
                    tag_rows = db.session.query(Tag.id).filter(func.lower(Tag.tag).in_(normalized_tags)).all()
                    tag_ids = {r[0] for r in tag_rows}
                except Exception:
                    db.session.rollback()
                    tag_ids = set()

                if tag_ids:
                    q_ = db.session.query(ItemTag.item_id).filter(ItemTag.tag_id.in_(tag_ids))
                    q_ = q_.group_by(ItemTag.item_id).having(func.count(func.distinct(ItemTag.tag_id)) == len(tag_ids))
                    try:
                        rows = q_.all()
                        ids = {r[0] for r in rows}
                    except Exception:
                        db.session.rollback()
                        ids = set()
                else:
                    ids = set()
                all_sets.append(ids)
                app.logger.debug(f"Tag constraint ids count: {len(ids)}")

            # Locations: OR semantics
            if modifiers['locations']:
                ids = set()
                for loc_val in modifiers['locations']:
                    try:
                        loc_rows = db.session.query(Item.id).join(Location, Item.location_id == Location.id).filter(
                            Location.name.ilike(f"%{loc_val}%")
                        ).all()
                        ids.update(r[0] for r in loc_rows)

                        spec_rows = db.session.query(Item.id).filter(Item.specific_location.ilike(f"%{loc_val}%")).all()
                        ids.update(r[0] for r in spec_rows)
                    except Exception:
                        db.session.rollback()
                all_sets.append(ids)
                app.logger.debug(f"Location constraint ids count: {len(ids)}")

            # Types: OR semantics
            if modifiers['types']:
                try:
                    lowered = [n.lower() for n in modifiers['types']]
                    type_rows = db.session.query(ItemType.id).filter(func.lower(ItemType.name).in_(lowered)).all()
                    type_ids = [r[0] for r in type_rows]
                except Exception:
                    db.session.rollback()
                    type_ids = []

                if type_ids:
                    try:
                        rows = db.session.query(Item.id).filter(Item.item_type.in_(type_ids)).all()
                        ids = {r[0] for r in rows}
                    except Exception:
                        db.session.rollback()
                        ids = set()
                else:
                    ids = set()
                all_sets.append(ids)
                app.logger.debug(f"Type constraint ids count: {len(ids)}")

            # Fields: each must be satisfied
            for (field_name, field_val) in modifiers['fields']:
                field_obj = FieldService.find_field_by_name(field_name)
                if field_obj is None:
                    all_sets.append(set())
                else:
                    try:
                        rows = db.session.query(ItemField.item_id).filter(
                            ItemField.field_id == field_obj.id,
                            ItemField.user_id == user_id,
                            ItemField.value.ilike(f"%{field_val}%")
                        ).all()
                        ids = {r[0] for r in rows}
                    except Exception:
                        db.session.rollback()
                        ids = set()
                    all_sets.append(ids)
                    app.logger.debug(f"Field constraint ids count for {field_name}: {len(ids)}")

            # Free text
            free_text = ' '.join(free_terms).strip()
            if free_text:
                ids_ft = SearchService._ids_from_free_text(user_id, free_text)
                all_sets.append(ids_ft)
                app.logger.debug(f"Free-text ids count: {len(ids_ft)} for '{free_text}'")

            # If no constraints => empty
            if not all_sets:
                app.logger.debug("No constraint sets -> returning empty")
                return {'items': [], 'total': 0, 'page': page, 'per_page': per_page}

            # intersect
            result_ids = None
            for s in all_sets:
                if result_ids is None:
                    result_ids = set(s)
                else:
                    result_ids &= s

            app.logger.debug(f"Intersected result_ids count: {len(result_ids) if result_ids is not None else 0}")

            # If intersection is empty, but user supplied free text, fall back to the free-text match set
            if not result_ids:
                if free_text:
                    try:
                        fallback_ids = SearchService._ids_from_free_text(user_id, free_text)
                        if fallback_ids:
                            result_ids = set(fallback_ids)
                            app.logger.debug(f"SearchService: falling back to free-text ids for query '{free_text}' ({len(result_ids)} ids)")
                        else:
                            app.logger.debug("Fallback free-text produced no ids -> returning empty")
                            return {'items': [], 'total': 0, 'page': page, 'per_page': per_page}
                    except Exception:
                        app.logger.exception('SearchService: error during fallback free-text search')
                        return {'items': [], 'total': 0, 'page': page, 'per_page': per_page}
                else:
                    app.logger.debug("Intersection empty and no free text -> returning empty")
                    return {'items': [], 'total': 0, 'page': page, 'per_page': per_page}

            # Scoring / ranking
            try:
                # Ensure IDs are ints (DB may return strings in some adapters); coerce safely
                coerced_ids = set()
                for rid in result_ids:
                    try:
                        coerced_ids.add(int(rid))
                    except Exception:
                        app.logger.debug(f"SearchService: skipping non-int id in result_ids: {rid}")
                if not coerced_ids:
                    # nothing to query
                    return {'items': [], 'total': 0, 'page': page, 'per_page': per_page}
                # Use db.session.query to ensure the same session/context is used
                items_objs = db.session.query(Item).filter(Item.id.in_(list(coerced_ids))).all()
                app.logger.debug(f"Result ids sample: {list(result_ids)[:20]}")
                app.logger.debug(f"Retrieved {len(items_objs)} Item objects for scoring")
            except Exception:
                db.session.rollback()
                app.logger.exception('Error retrieving items by id')
                return {'items': [], 'total': 0, 'page': page, 'per_page': per_page}

            def score_item(item: Item):
                score = 0
                lname = (item.name or '').lower()
                ldesc = (item.description or '').lower()
                # free terms tokens as lower
                ftokens = [t.lower() for t in free_terms]
                weights = SearchService._get_weights()
                for tk in ftokens:
                    if tk and tk in lname:
                        score += weights['NAME_WEIGHT']
                    if tk and tk in ldesc:
                        score += weights['DESCRIPTION_WEIGHT']
                # tags
                item_tags = [t.tag.replace('@#$', ' ').lower() for t in item.tags]
                for t in modifiers['tags']:
                    if t.lower() in item_tags:
                        score += weights['TAG_WEIGHT']
                # locations
                for locv in modifiers['locations']:
                    if (item.location and locv.lower() in (item.location.name or '').lower()) or (item.specific_location and locv.lower() in (item.specific_location or '').lower()):
                        score += weights['LOCATION_WEIGHT']
                # types
                itype = getattr(item, 'item_type_obj', None)
                if itype and any(ty.lower() in (itype.name or '').lower() for ty in modifiers['types']):
                    score += weights['TYPE_WEIGHT']
                # fields
                for (fn, fv) in modifiers['fields']:
                    # try to find a matching ItemField
                    try:
                        field_obj = FieldService.find_field_by_name(fn)
                        if field_obj:
                            rows = db.session.query(ItemField).filter(ItemField.item_id == item.id, ItemField.field_id == field_obj.id, ItemField.value.ilike(f"%{fv}%")).all()
                            if rows:
                                score += weights['FIELD_WEIGHT']
                    except Exception:
                        db.session.rollback()
                return score

            scored = []
            for it in items_objs:
                scored.append((score_item(it), it))

            scored.sort(key=lambda x: (-x[0], x[1].id))

            total = len(scored)
            app.logger.debug(f"Scored total={total} items")

            # paging
            try:
                page = int(page) if page and int(page) > 0 else 1
            except Exception:
                page = 1
            try:
                per_page = int(per_page) if per_page and int(per_page) > 0 else 20
            except Exception:
                per_page = 20

            start = (page - 1) * per_page
            end = start + per_page
            page_slice = scored[start:end]

            # build snippets and DTOs
            dtos = []
            for score_val, item_obj in page_slice:
                # build snippet from description using highlight terms
                snippet = ''
                desc = item_obj.description or ''
                if desc:
                    # find first occurrence of any highlight term
                    lowdesc = desc.lower()
                    pos = None
                    for term in highlight_terms:
                        if not term:
                            continue
                        idx = lowdesc.find(term.lower())
                        if idx != -1:
                            if pos is None or idx < pos:
                                pos = idx
                    if pos is not None:
                        # extract window
                        start_pos = max(0, pos - 60)
                        end_pos = min(len(desc), pos + 60)
                        snippet_raw = desc[start_pos:end_pos]
                    else:
                        snippet_raw = desc[:120]
                    snippet = SearchService._highlight_text(snippet_raw, highlight_terms)
                # if no desc, maybe show tags
                if not snippet and item_obj.tags:
                    snippet = 'Tags: ' + ', '.join([t.tag.replace('@#$', ' ') for t in item_obj.tags[:5]])
                    snippet = bleach.clean(snippet, tags=[], strip=True)
                dtos.append(SearchService._make_item_dto(item_obj, snippet_html=snippet))

            return {'items': dtos, 'total': total, 'page': page, 'per_page': per_page}

    @staticmethod
    def inspect_query(query: str, user_id: int):
        """Return diagnostic information about how a query would be parsed and what IDs each part matches.
        This is used for debugging why searches return no results.
        """
        with app.app_context():
            import shlex
            tokens = []
            try:
                tokens = shlex.split(query or '')
            except Exception:
                tokens = (query or '').split()

            modifiers = {'tags': [], 'locations': [], 'types': [], 'fields': []}
            free_terms = []
            for tok in tokens:
                if ':' in tok:
                    key, val = tok.split(':', 1)
                    key_l = key.lower()
                    if key_l in ('tag', 'tags'):
                        vals = [v.strip() for v in val.split(',') if v.strip()]
                        modifiers['tags'].extend(vals)
                    elif key_l in ('location', 'locations'):
                        vals = [v.strip() for v in val.split(',') if v.strip()]
                        modifiers['locations'].extend(vals)
                    elif key_l in ('type', 'types'):
                        vals = [v.strip() for v in val.split(',') if v.strip()]
                        modifiers['types'].extend(vals)
                    else:
                        modifiers['fields'].append((key, val))
                else:
                    free_terms.append(tok)

            free_text = ' '.join(free_terms).strip()

            def ids_for_tags(tag_list):
                if not tag_list:
                    return set()
                normalized_tags = [t.replace(' ', '@#$').lower() for t in tag_list]
                try:
                    tag_rows = db.session.query(Tag.id).filter(func.lower(Tag.tag).in_(normalized_tags)).all()
                    tag_ids = {r[0] for r in tag_rows}
                except Exception:
                    db.session.rollback()
                    tag_ids = set()
                if not tag_ids:
                    return set()
                try:
                    q_ = db.session.query(ItemTag.item_id).filter(ItemTag.tag_id.in_(tag_ids))
                    q_ = q_.group_by(ItemTag.item_id).having(func.count(func.distinct(ItemTag.tag_id)) == len(tag_ids))
                    rows = q_.all()
                    return {r[0] for r in rows}
                except Exception:
                    db.session.rollback()
                    return set()

            def ids_for_locations(loc_list):
                ids = set()
                for loc_val in loc_list:
                    try:
                        loc_rows = db.session.query(Item.id).join(Location, Item.location_id == Location.id).filter(
                            Location.name.ilike(f"%{loc_val}%")
                        ).all()
                        ids.update(r[0] for r in loc_rows)

                        spec_rows = db.session.query(Item.id).filter(Item.specific_location.ilike(f"%{loc_val}%")).all()
                        ids.update(r[0] for r in spec_rows)
                    except Exception:
                        db.session.rollback()
                return ids

            def ids_for_types(type_list):
                if not type_list:
                    return set()
                try:
                    lowered = [n.lower() for n in type_list]
                    type_rows = db.session.query(ItemType.id).filter(func.lower(ItemType.name).in_(lowered)).all()
                    type_ids = [r[0] for r in type_rows]
                except Exception:
                    db.session.rollback()
                    type_ids = []
                if not type_ids:
                    return set()
                try:
                    rows = db.session.query(Item.id).filter(Item.item_type.in_(type_ids)).all()
                    return {r[0] for r in rows}
                except Exception:
                    db.session.rollback()
                    return set()

            def ids_for_fields(field_pairs):
                ids = None
                for (fname, fval) in field_pairs:
                    field_obj = FieldService.find_field_by_name(fname)
                    if not field_obj:
                        this_ids = set()
                    else:
                        try:
                            rows = db.session.query(ItemField.item_id).filter(
                                ItemField.field_id == field_obj.id,
                                ItemField.user_id == user_id,
                                ItemField.value.ilike(f"%{fval}%")
                            ).all()
                            this_ids = {r[0] for r in rows}
                        except Exception:
                            db.session.rollback()
                            this_ids = set()
                    if ids is None:
                        ids = set(this_ids)
                    else:
                        ids &= this_ids
                return ids or set()

            info = {
                'tokens': tokens,
                'modifiers': modifiers,
                'free_text': free_text,
                'counts': {}
            }

            info['counts']['tags'] = len(ids_for_tags(modifiers['tags']))
            info['counts']['locations'] = len(ids_for_locations(modifiers['locations']))
            info['counts']['types'] = len(ids_for_types(modifiers['types']))
            info['counts']['fields'] = len(ids_for_fields(modifiers['fields']))
            ft_ids = SearchService._ids_from_free_text(user_id, free_text) if free_text else set()
            info['counts']['free_text'] = len(ft_ids)
            # include small samples for diagnostics
            info['sample_ids'] = {
                'free_text': list(sorted(ft_ids))[:20]
            }

            # also compute intersection of all constraint sets to show what will be used by search
            sets = []
            t_ids = ids_for_tags(modifiers['tags'])
            if t_ids: sets.append(t_ids)
            l_ids = ids_for_locations(modifiers['locations'])
            if l_ids: sets.append(l_ids)
            ty_ids = ids_for_types(modifiers['types'])
            if ty_ids: sets.append(ty_ids)
            f_ids = ids_for_fields(modifiers['fields'])
            if f_ids: sets.append(f_ids)
            if ft_ids:
                sets.append(ft_ids)

            if not sets:
                intersection = set()
            else:
                intersection = set(sets[0])
                for s in sets[1:]:
                    intersection &= s

            info['intersection_count'] = len(intersection)
            info['sample_ids']['intersection'] = list(sorted(intersection))[:20]

            return info

