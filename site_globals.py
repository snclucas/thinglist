__NONE__ = "None"
__none__ = "none"
__DEFAULT__ = "default"
__ALL__ = "all"

__PRIVATE__ = 0
__OWNER__ = 0
__VIEWER__ = 1
__COLLABORATOR__ = 2
__PUBLIC__ = 3

__INVENTORY__ = 1
__LIST__ = 2
__LIST_ALL__ = 3
__URL_LIST__ = 4

_MOVE_ = 0
_COPY_ = 1
_LINK_ = 2

__READ_ONLY__ = 2

__OK__ = 200
__BAD_REQUEST__ = 400
__UNAUTHORIZED__ = 401
__FORBIDDEN__ = 403
__NOT_FOUND__ = 404
__METHOD_NOT_ALLOWED__ = 405
__CONFLICT__ = 409
__GONE__ = 410
__INTERNAL_SERVER_ERROR__ = 500
__NOT_IMPLEMENTED__ = 501
__SERVICE_UNAVAILABLE__ = 503

__ERROR__ = "error"


# SEO defaults and helper
from typing import Any, Dict


def _ensure_str(val: Any) -> str:
    if val is None:
        return ""
    return str(val)


def build_meta(**overrides) -> Dict[str, Any]:
    """Build a metadata dictionary for templates.

    Merges sane site defaults with per-route overrides. Intended keys:
      - title, description, canonical, robots, default_image
      - og (dict), twitter (dict), structured_data (dict)

    This function imports Flask request/current_app at call time to avoid circular imports.
    """
    try:
        # import here to avoid circular imports at module import time
        from flask import request, current_app, url_for
    except Exception:
        # Not in Flask context; return overrides as-is
        meta = {**overrides}
        meta.setdefault('og', overrides.get('og', {}))
        meta.setdefault('twitter', overrides.get('twitter', {}))
        meta.setdefault('structured_data', overrides.get('structured_data'))
        return meta

    site_name = current_app.config.get('SITE_NAME', 'ThingList')
    site_description = current_app.config.get('SITE_DESCRIPTION', 'A list of all your things')
    site_url = current_app.config.get('SITE_URL', '')
    default_image = current_app.config.get('DEFAULT_OG_IMAGE')

    if not default_image:
        # fallback to a static asset path; templates can call url_for if needed
        default_image = url_for('static', filename='img/thinglist-logo-50pc.png')

    # Base defaults
    defaults: Dict[str, Any] = {
        'site_name': site_name,
        'title': site_name,
        'description': site_description,
        'canonical': (site_url.rstrip('/') + request.path) if site_url else request.url,
        'robots': 'index,follow',
        'default_image': default_image,
        'og': {
            'type': 'website',
        },
        'twitter': {
            'card': 'summary_large_image',
        },
        'structured_data': None,
    }

    # shallow merge
    meta: Dict[str, Any] = {**defaults}

    # handle nested dicts
    og_over = overrides.get('og') or {}
    twitter_over = overrides.get('twitter') or {}

    meta['og'] = {**defaults.get('og', {}), **og_over}
    meta['twitter'] = {**defaults.get('twitter', {}), **twitter_over}

    # copy simple overrides
    for k, v in overrides.items():
        if k in ('og', 'twitter'):
            continue
        meta[k] = v

    # sensible fallbacks
    if not meta.get('og').get('title'):
        meta['og']['title'] = meta.get('title')
    if not meta.get('og').get('description'):
        meta['og']['description'] = _ensure_str(meta.get('description'))
    if not meta.get('og').get('url'):
        meta['og']['url'] = meta.get('canonical')
    if not meta.get('twitter').get('title'):
        meta['twitter']['title'] = meta.get('title')
    if not meta.get('twitter').get('description'):
        meta['twitter']['description'] = _ensure_str(meta.get('description'))
    if not meta.get('twitter').get('image'):
        meta['twitter']['image'] = meta.get('og').get('image') or meta.get('default_image')
    if not meta.get('og').get('image'):
        meta['og']['image'] = meta.get('default_image')

    return meta
