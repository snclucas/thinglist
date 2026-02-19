import bleach
from flask import Blueprint, request, render_template, current_app, flash, redirect, url_for
from flask_login import login_required, current_user
import time

from routes.index_routes import profile
from services.field_service import FieldService
from services.field_template_service import FieldTemplateService
from services.inventory_service import InventoryService
from services.item_service import ItemService
from services.item_type_service import ItemTypeService
from services.location_service import LocationService

user_admin_routes = Blueprint('user_admin', __name__)


@user_admin_routes.route('/user-admin', methods=['GET', 'POST'])
@login_required
def admin():
    # Support GET so users may navigate to the admin page and see the wipe form.
    # Also accept POST for backward compatibility if needed (renders the same page).
    try:
        from site_globals import build_meta
        meta = build_meta(title=f"{current_user.username} — Admin", description="User admin tools")
    except Exception:
        meta = None
    return render_template(template_name_or_list='admin/admin.html', meta=meta)


@user_admin_routes.route('/user-admin/wipe', methods=['POST'])
@login_required
def wipe():
    """Wipe selected user data areas.

    Improvements made:
    - Robust boolean parsing for checkbox values (supports 'on', 'true', '1', 'yes').
    - Each selected action runs independently, so selecting only locations/templates will work.
    - Per-action try/except to ensure one failing service doesn't block others.
    - Structured logging of successes and failures for easier debugging.
    - Server-side confirmation required (enter your username) to prevent accidental wipes.
    - Simple per-user in-memory rate-limiting (configurable by WIPE_RATE_LIMIT_SECONDS) to prevent rapid repeated destructive operations.
    """
    username = current_user.username

    def _parse_bool_field(name: str) -> bool:
        """Parse checkbox-like fields reliably from request.form."""
        v = request.form.get(name)
        if v is None:
            return False
        # sanitize short textual values (defensive) and normalize
        try:
            v_clean = bleach.clean(str(v)).strip().lower()
        except Exception:
            v_clean = str(v).strip().lower()
        return v_clean in ("on", "true", "1", "yes")

    # parse selected actions
    wipe_items = _parse_bool_field('wipe_items')
    wipe_lists = _parse_bool_field('wipe_lists')
    wipe_locations = _parse_bool_field('wipe_locations')
    wipe_templates = _parse_bool_field('wipe_templates')

    # server-side confirmation: require checkbox plus typed username (case-insensitive)
    confirm_value = (request.form.get('wipe_confirmation') or '').strip()
    confirm_checkbox = _parse_bool_field('wipe_confirm_checkbox')
    if not any((wipe_items, wipe_lists, wipe_locations, wipe_templates)):
        flash('No wipe actions selected.', 'warning')
        return profile(username=username)

    # Accept case-insensitive username match, but require explicit checkbox for extra safety
    if not confirm_checkbox or confirm_value.lower() != username.lower():
        flash('To confirm a destructive wipe you must check the confirmation box and type your username (case-insensitive).', 'danger')
        return profile(username=username)

    # rate-limiting (simple in-memory per-user throttle). Configurable via WIPE_RATE_LIMIT_SECONDS (seconds).
    throttle = current_app.extensions.setdefault('wipe_throttle', {})
    try:
        limit_seconds = int(current_app.config.get('WIPE_RATE_LIMIT_SECONDS', 86400))
    except Exception:
        limit_seconds = 86400

    now = int(time.time())
    last_ts = throttle.get(current_user.id)
    if last_ts is not None and (now - int(last_ts)) < limit_seconds:
        remaining = limit_seconds - (now - int(last_ts))
        # format remaining minutes
        mins = max(1, int((remaining + 59) // 60))
        flash(f'Wipe is rate-limited. Please wait ~{mins} minute(s) before trying again.', 'danger')
        current_app.logger.warning(f"User {current_user.id} attempted wipe but is rate-limited; remaining {remaining}s")
        return profile(username=username)

    # If all are true, treat as "wipe everything" shortcut (maintain existing behavior)
    actions = []
    if wipe_items and wipe_lists and wipe_locations and wipe_templates:
        actions = [
            ("items", lambda: ItemService.delete_all_user_items(user_id=current_user.id)),
            ("lists", lambda: InventoryService.delete_all_user_lists(user_id=current_user.id)),
            ("locations", lambda: LocationService.delete_user_locations(user_id=current_user.id)),
            ("fields", lambda: FieldService.delete_all_user_fields(user_id=current_user.id)),
            ("item_types", lambda: ItemTypeService.delete_all_user_item_types(user_id=current_user.id)),
            ("templates", lambda: FieldTemplateService.delete_all_user_field_templates(user_id=current_user.id)),
        ]
    else:
        # Build the selected actions list; each callable is executed independently
        if wipe_items:
            actions.append(("items", lambda: ItemService.delete_all_user_items(user_id=current_user.id)))
        if wipe_lists:
            actions.append(("lists", lambda: InventoryService.delete_all_user_lists(user_id=current_user.id)))
        if wipe_locations:
            actions.append(("locations", lambda: LocationService.delete_user_locations(user_id=current_user.id)))
        if wipe_templates:
            # templates deletion may imply deleting fields and types depending on implementation; keep it explicit
            actions.append(("templates", lambda: FieldTemplateService.delete_all_user_field_templates(user_id=current_user.id)))

    # Execute actions and collect results
    errors = []
    any_success = False
    for name, fn in actions:
        try:
            fn()
            any_success = True
            current_app.logger.info(f"User admin wipe: successfully executed action '{name}' for user_id={current_user.id}")
        except Exception as exc:
            # log the exception but continue with remaining actions
            current_app.logger.exception(f"User admin wipe: action '{name}' failed for user_id={current_user.id}: {exc}")
            errors.append({"action": name, "error": str(exc)})

    # Only set throttle timestamp on successful wipe(s)
    if any_success:
        try:
            current_app.extensions['wipe_throttle'][current_user.id] = int(time.time())
        except Exception:
            # non-fatal; log and continue
            current_app.logger.exception("Failed to update wipe_throttle timestamp")

    if errors:
        # Log a summary and give user feedback; do not expose internals
        current_app.logger.error(f"User admin wipe completed with {len(errors)} error(s) for user_id={current_user.id}")
        flash(f'Wipe completed with {len(errors)} error(s); check server logs for details.', 'warning')
    else:
        if any_success:
            flash('Selected data areas wiped successfully.', 'success')
        else:
            flash('No actions were performed.', 'info')

    return profile(username=username)
