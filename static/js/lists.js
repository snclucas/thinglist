(function () {
    'use strict';

    // read config rendered by Jinja in the page
    const cfg = (typeof window !== 'undefined' && window.INVENTORY_PAGE) ? window.INVENTORY_PAGE : {};
    const CSRF_TOKEN = String(cfg.csrfToken || '');
    const USERNAME = String(cfg.username || '');
    const DEL_URL = String(cfg.delInventoryUrl || '');

    const toInt = (v, def = null) => {
        const n = parseInt(String(v ?? ''), 10);
        return Number.isFinite(n) ? n : def;
    };

    const toBool = (v) => {
        const s = String(v ?? '').toLowerCase();
        return s === '1' || s === 'true' || s === 'yes';
    };

    const safe = (fn) => {
        try {
            return fn();
        } catch (e) {
            console.error(e);
            return undefined;
        }
    };

    $(function () {
        // initialize tooltips
        try {
            $('[data-toggle="tooltip"]').tooltip();
        } catch (e) {
            console.warn('Tooltip init failed', e);
        }

        // init datatable only if element exists
        const $table = $('#inventories-table');
        if ($table.length) {
            try {
                $table.DataTable({
                    searching: true,
                    paging: false,
                    ordering: true,
                    info: true,
                    responsive: {details: false}
                });
            } catch (e) {
                console.warn('DataTable init failed', e);
            }
        }

        // keep initial checkbox state consistent
        safe(check_checkboxes);
    });

    // Cancel delete
    $('#cancel-delete-inventories-btn').on('click', function () {
        safe(() => deselect_all_checkboxes('selected-item-'));
        $('#collapseDeleteInventories').collapse('hide');
    });

    // handle checkbox clicks (event delegation)
    $(document).on('click', 'input:checkbox[id^="selected-item-"]', function () {
        safe(check_checkboxes);
    });

    function check_checkboxes() {
        try {
            const number_selected = (typeof checkbox_count === 'function')
                ? checkbox_count('selected-item-')
                : $('input:checkbox[id^="selected-item-"]:checked').length;

            const $deleteCollapseBtn = $('#delete-inventories-btn-collapse');
            const $deleteBtn = $('#delete-inventories-btn');
            const $deleteSpan = $('#delete-inventories-span');

            if (number_selected > 0) {
                $deleteCollapseBtn.attr('href', '#collapseDeleteInventories');
                $deleteBtn.css('pointer-events', 'auto').prop('disabled', false).removeAttr('disabled');
                $deleteCollapseBtn.prop('disabled', false);
                $deleteSpan.css('color', 'red');
            } else {
                $('#collapseDeleteInventories').collapse('hide');
                $deleteCollapseBtn.removeAttr('href').prop('disabled', true);
                $deleteBtn.css('pointer-events', 'none').prop('disabled', true);
                $deleteSpan.css('color', 'lightgray');
            }
        } catch (e) {
            console.error('check_checkboxes error', e);
        }
    }

    // inventory edit: use delegated handler and dataset (safer than attr)
    $(document).on('click', '[id^=inventoryEdit]', function () {
        try {
            const el = this;
            const ds = el.dataset || {};
            const inventory_id = toInt(ds.inventoryId ?? $(el).attr('data-inventory-id'));
            const inventory_name = ds.inventoryName ?? $(el).attr('data-inventory-name') ?? '';
            const inventory_desc = ds.inventoryDescription ?? $(el).attr('data-inventory-description') ?? '';
            const inventory_type = ds.inventoryType ?? $(el).attr('data-inventory-type') ?? '';
            const inventory_public = ds.inventoryPublic ?? $(el).attr('data-inventory-public');

            // attribute typo fallback (supports both spellings)
            const inventory_show_item_images = ds.inventoryShowItemImages ?? $(el).attr('data-inventory-show-item-images');
            const inventory_show_item_type = ds.inventoryShowItemType ?? $(el).attr('data-inventory-show-item-type');
            const inventory_show_item_location = ds.inventoryShowItemLocation ?? ds.inventoryShowItemLocatio ?? $(el).attr('data-inventory-show-item-location') ?? $(el).attr('data-inventory-show-item-locatio');
            const inventory_show_item_tags = ds.inventoryShowItemTags ?? $(el).attr('data-inventory-show-item-tags');

            // write into form inputs safely
            $('#edit_form_inventory_id').val(inventory_id ? String(inventory_id) : '');
            $('#edit_form_inventory_name').val(inventory_name);
            $('#edit_form_inventory_description').val(inventory_desc);

            if (inventory_type !== '') {
                $('div.inv_type select').val(String(inventory_type));
            }

            $('#edit_form_inventory_public').prop('checked', toInt(inventory_public, -1) === 3);

            $('#edit_form_show_item_images').prop('checked', toBool(inventory_show_item_images));
            $('#edit_form_show_item_type').prop('checked', toBool(inventory_show_item_type));
            $('#edit_form_show_item_location').prop('checked', toBool(inventory_show_item_location));
            $('#edit_form_show_item_tags').prop('checked', toBool(inventory_show_item_tags));
        } catch (e) {
            console.error('inventoryEdit handler error', e);
        }
    });

    // Confirm delete: validate selection and keep user feedback
    $('#confirm-delete-inventories-btn').on('click', function (e) {
        e.preventDefault();
        const $btn = $(this);
        try {
            const getIds = (typeof get_selected_checkbox_ids === 'function')
                ? get_selected_checkbox_ids
                : function (prefix, attr) {
                    return $('input:checkbox[id^="' + prefix + '"]:checked').map(function () {
                        return $(this).attr(attr);
                    }).get();
                };

            const selected_list = getIds('selected-item-', 'data-inventory-id') || [];
            if (!Array.isArray(selected_list) || selected_list.length === 0) {
                // nothing selected
                return;
            }

            // disable button to prevent double submissions
            $btn.prop('disabled', true);

            const payload = {
                inventory_ids: selected_list,
                username: USERNAME
            };

            $.ajax({
                type: 'POST',
                url: DEL_URL,
                contentType: 'application/json;charset=UTF-8',
                headers: {
                    'X-CSRFToken': CSRF_TOKEN
                },
                data: JSON.stringify(payload),
                dataType: 'json',
                timeout: 10000
            }).done(function (response) {
                // prefer server-driven redirect or reload on success
                location.reload();
            }).fail(function (jqXHR, textStatus, errorThrown) {
                console.error('Delete request failed:', textStatus, errorThrown, jqXHR.responseText);
                // still reload to reflect server-side state, or show error UI
                location.reload();
            }).always(function () {
                $btn.prop('disabled', false);
            });

        } catch (err) {
            console.error('confirm-delete error', err);
            $btn.prop('disabled', false);
        }
    });

    document.addEventListener('DOMContentLoaded', function () {
        // find forms whose action contains "edit_inventory" (fallback: explicit collapse id)
        const forms = Array.from(document.querySelectorAll('form[action*="edit_inventory"], #collapseInventoryEdit form'));
        forms.forEach((form) => {
            // prefer a Cancel button that won't submit the form
            const cancelBtn = form.querySelector('button[type="button"][data-bs-dismiss="modal"], button[type="button"].btn-secondary, button.cancel');
            if (!cancelBtn) return;

            cancelBtn.addEventListener('click', function () {
                try {
                    // try to hide nearest .collapse
                    const collapseEl = cancelBtn.closest('.collapse');
                    if (collapseEl) {
                        if (window.bootstrap && bootstrap.Collapse) {
                            bootstrap.Collapse.getOrCreateInstance(collapseEl).hide();
                        } else if (window.jQuery && typeof jQuery(collapseEl).collapse === 'function') {
                            jQuery(collapseEl).collapse('hide');
                        } else {
                            collapseEl.classList.remove('show');
                            collapseEl.setAttribute('aria-expanded', 'false');
                        }
                    } else {
                        // fallback: hide nearest modal
                        const modalEl = cancelBtn.closest('.modal');
                        if (modalEl) {
                            if (window.bootstrap && bootstrap.Modal) {
                                bootstrap.Modal.getOrCreateInstance(modalEl).hide();
                            } else if (window.jQuery && typeof jQuery(modalEl).modal === 'function') {
                                jQuery(modalEl).modal('hide');
                            } else {
                                modalEl.classList.remove('show');
                                modalEl.style.display = 'none';
                            }
                        }
                    }
                } catch (e) {
                    console.error('collapse-on-cancel error', e);
                } finally {
                    // clear inputs and validation state
                    try {
                        form.reset();
                        // remove any client-side validation classes (Bootstrap)
                        form.classList.remove('was-validated');
                    } catch (__) {
                    }
                }
            }, {passive: true});
        });
    });

})();