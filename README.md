# thing-list

Small notes for SEO config keys added by the recent changes.

Configuration (environment variables)

- SITE_NAME: Friendly site name used for default titles. Default: "ThingList".
- SITE_URL: Public base URL for the site (e.g. https://thinglist.org). Used to build canonical URLs when present.
- SITE_DESCRIPTION: Default site description used when a page doesn't provide one.
- DEFAULT_OG_IMAGE: Absolute URL to a default image used for Open Graph/Twitter cards when no page-specific image is provided.

How to set (example .env):

SITE_NAME="ThingList"
SITE_URL="https://thinglist.example"
SITE_DESCRIPTION="A list of all your things"
DEFAULT_OG_IMAGE="https://thinglist.example/static/img/thinglist-logo-50pc.png"

Notes

- Pages can construct per-route metadata by calling `site_globals.build_meta(...)` and passing the result into `render_template(..., meta=meta)`.
- The `templates/base.html` template now renders Open Graph, Twitter Cards, canonical, robots, and JSON-LD blocks based on the `meta` dict.
- The app context processor injects a default `meta` built from env/config so pages that haven't been updated still receive sensible defaults.
