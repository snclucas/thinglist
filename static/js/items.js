(function () {
  const V = window.ITEMS_PAGE_VARS || {};

  function headerWithCsrf() {
    const h = { 'Content-Type': 'application/json;charset=UTF-8' };
    if (V.csrf_token) h['X-CSRFToken'] = V.csrf_token;
    return h;
  }

  function safeParseJson(data) {
    try {
      return (typeof data === 'string') ? JSON.parse(data) : data;
    } catch (e) {
      return data;
    }
  }

  $(document).ready(function () {
    // Initialize small tables
    $('#item-field-table').DataTable({ searching: true, paging: true, ordering: true, info: true });
    $('#inventory-users-table').DataTable({ searching: true, paging: true, ordering: true, info: true });

    // Toggle visibility links: requires a global `table` variable from the main list script
    document.querySelectorAll('a.toggle-vis').forEach((el) => {
      el.addEventListener('click', function (e) {
        e.preventDefault();
        const columnIdx = e.target.getAttribute('data-column');
        if (typeof table !== 'undefined' && columnIdx != null) {
          const column = table.column(columnIdx);
          column.visible(!column.visible());
        }
      });
    });

    const filterItemsSpan = $('#filter-items-span');
    const urlParams = new URLSearchParams(window.location.search);
    if (urlParams.size > 0) {
      if (urlParams.size === 1) {
        if (urlParams.get('view') == null) filterItemsSpan.css('color', 'green');
      } else {
        filterItemsSpan.css('color', 'green');
      }
    } else {
      filterItemsSpan.css('color', 'black');
    }

    // Regenerate token
    $('#btn-regenerate-token').on('click', function (e) {
      e.preventDefault();
      if (!V.regenerate_token_url) return;
      $.ajax({
        type: 'POST',
        url: V.regenerate_token_url,
        contentType: 'application/json;charset=UTF-8',
        headers: headerWithCsrf(),
        data: JSON.stringify({ inventory_id: V.inventory_id }),
        success: function (data) {
          const d = safeParseJson(data);
          $('#inventory-token').text(d && d['new-token'] ? d['new-token'] : '');
        },
        error: function () { location.reload(); }
      });
    });

    // Load items button
    $('#load-items-btn').on('click', function (e) {
      e.preventDefault();
      document.getElementById('load-items-span').style.removeProperty('display');
      $('#load-items-form').submit();
    });

    // Filters: apply / clear
    $('#btn-apply-filter').on('click', function (e) {
      e.preventDefault();
      const searchParams = new URLSearchParams(window.location.search);
      const tag = $('#form_item_tags').val();
      if (tag !== '' && tag !== 'None') searchParams.set('tags', tag);
      const itemType = $('#types_autocomplete').val();
      if (itemType !== '' && itemType !== undefined) searchParams.set('type', itemType);
      const specificLocation = $('#form_item_specific_location').val();
      if (specificLocation !== '' && specificLocation !== 'None') searchParams.set('specific_location', specificLocation);
      window.location.search = searchParams.toString();
    });

    $('#btn-clear-filters').on('click', function (e) {
      e.preventDefault();
      const searchParams = new URLSearchParams(window.location.search);
      searchParams.delete('type');
      searchParams.delete('location');
      searchParams.delete('tags');
      $('#form_item_tags').val('');
      searchParams.delete('specific_location');
      $('#form_item_specific_location').val('');
      window.location.search = searchParams.toString();
    });

    // Select menus changing location
    $('#item_location_filter').on('change', function () {
      const optionValue = $('#item_location_filter').find(':selected').text();
      const searchParams = new URLSearchParams(window.location.search);
      if (optionValue === 'Any') searchParams.delete('location');
      else searchParams.set('location', optionValue);
      window.location.search = searchParams.toString();
    });

    $('#item_type_filter').on('change', function () {
      const optionValue = $('#item_type_filter').find(':selected').text();
      const searchParams = new URLSearchParams(window.location.search);
      if (optionValue === 'Any') searchParams.delete('type');
      else searchParams.set('type', optionValue);
      window.location.search = searchParams.toString();
    });

    // Inventory filter: use pre-rendered URL templates
    $('#inventory_filter').on('change', function () {
      const selection = $('#inventory_filter');
      const optionValue = selection.find(':selected').val();
      const searchParams = new URLSearchParams(window.location.search);
      if (optionValue === 'all') {
        if (V.inventory_url_all) window.location.href = V.inventory_url_all + '?' + searchParams.toString();
      } else if (optionValue === 'default') {
        if (V.inventory_url_default) window.location.href = V.inventory_url_default + '?' + searchParams.toString();
      } else {
        if (V.inventory_url_template) window.location.href = V.inventory_url_template.replace('INV', optionValue) + '?' + searchParams.toString();
      }
    });

    // Helper: checkbox-driven UI state
    function run_over_checkboxes() {
      const number_selected = (typeof checkbox_count === 'function') ? checkbox_count('selected-item-') : 0;
      const delete_collapse_btn_selector = $('#delete-items-btn-collapse');
      const delete_btn_selector = $('#delete-items-btn');
      const delete_span_selector = $('#delete-items-span');
      const move_items_btn_selector = $('#move-items-btn');
      const move_items_span_selector = $('#move-items-span');
      const bulk_edit_items_btn_selector = $('#bulk-edit-items-btn');
      const bulk_edit_items_span_selector = $('#bulk-edit-items-span');

      if (number_selected > 0) {
        delete_collapse_btn_selector.attr('href', '#collapseDeleteItems');
        delete_btn_selector.css('pointer-events', 'auto'); move_items_btn_selector.css('pointer-events', 'auto');
        bulk_edit_items_btn_selector.css('pointer-events', 'auto'); bulk_edit_items_span_selector.css('pointer-events', 'auto');
        delete_span_selector.css('color', 'red'); bulk_edit_items_span_selector.css('color', 'green'); move_items_span_selector.css('color', 'green');
        delete_btn_selector.prop('disabled', false); delete_collapse_btn_selector.prop('disabled', false); move_items_btn_selector.prop('disabled', false);
        bulk_edit_items_btn_selector.prop('disabled', false); bulk_edit_items_span_selector.prop('disabled', false);
        delete_btn_selector.attr('disabled', 'disabled'); move_items_btn_selector.attr('disabled', 'disabled');
        bulk_edit_items_btn_selector.attr('disabled', 'disabled'); bulk_edit_items_span_selector.attr('disabled', 'disabled');
      } else {
        $('#collapseDeleteItems').collapse('hide');
        delete_collapse_btn_selector.removeAttr('href');
        delete_btn_selector.css('pointer-events', 'none'); move_items_btn_selector.css('pointer-events', 'none');
        bulk_edit_items_btn_selector.css('pointer-events', 'none'); bulk_edit_items_span_selector.css('pointer-events', 'none');
        delete_span_selector.css('color', 'lightgray'); bulk_edit_items_span_selector.css('color', 'lightgray'); move_items_span_selector.css('color', 'lightgray');
        delete_btn_selector.prop('disabled', true); delete_collapse_btn_selector.prop('disabled', true); move_items_btn_selector.prop('disabled', true);
        bulk_edit_items_btn_selector.prop('disabled', true); bulk_edit_items_span_selector.prop('disabled', true);
        delete_btn_selector.removeAttr('disabled'); move_items_btn_selector.removeAttr('disabled');
        bulk_edit_items_btn_selector.removeAttr('disabled'); bulk_edit_items_span_selector.removeAttr('disabled');
      }
    }

    // Ensure initial state and simple table
    run_over_checkboxes();
    $('#invtable').DataTable(
        {
            searching: true, paging: false, ordering: true, info: true
        }
    );

    // Checkbox handlers
    $(document).on('click', 'input:checkbox[id^="selected-item-"]', function () { run_over_checkboxes(); });

    // Toggle all checkboxes
    $('#total-all-selected-items, #all-selected-items').on('click', function () {
      const is_checked = $(this).is(':checked');
      $('input:checkbox[id^="selected-item-"]').each(function () { $(this).prop('checked', is_checked); });
      run_over_checkboxes();
    });

    // Helper to collect selected ids (or [-1] for all)
    function collect_selected_item_ids() {
      const allChecked = $('#total-all-selected-items').is(':checked');
      if (allChecked) return [-1];
      const ids = [];
      $('input:checkbox[id^="selected-item-"]').each(function () {
        const $this = $(this);
        if ($this.is(':checked')) ids.push($this.attr('data-item-id'));
      });
      return ids;
    }

    // Confirm delete
    $('#confirm-delete-items-btn').on('click', function (e) {
      e.preventDefault();
      if (!V.del_items_url) return;
      const all_items_are_checked = $('#total-all-selected-items').is(':checked');
      const number_selected = collect_selected_item_ids();
      $.ajax({
        type: 'POST',
        url: V.del_items_url,
        contentType: 'application/json;charset=UTF-8',
        headers: headerWithCsrf(),
        data: JSON.stringify({
          item_ids: number_selected,
          username: V.username,
          inventory_id: V.inventory_id,
          all_items_are_checked: all_items_are_checked
        }),
        success: function () { location.reload(); },
        error: function () { location.reload(); }
      });
    });

    // Batch edit
    $('#btn_submit_edit').on('click', function (e) {
      e.preventDefault();
      if (!V.items_edit_url) return;
      const number_selected = collect_selected_item_ids();
      const location_selection_option_value = $('#items_location_edit').find(':selected').val();
      const items_specific_location_edit_value = $('#items_specific_location_edit').val();
      const item_visibility_option_value = $('#items_public_edit').find(':selected').val();

      $.ajax({
        type: 'POST',
        url: V.items_edit_url,
        contentType: 'application/json;charset=UTF-8',
        headers: headerWithCsrf(),
        data: JSON.stringify({
          item_ids: number_selected,
          username: V.username,
          inventory_slug: V.inventory_slug,
          location_id: location_selection_option_value,
          specific_location: items_specific_location_edit_value,
          item_visibility: item_visibility_option_value
        }),
        success: function () { location.reload(); },
        error: function () { location.reload(); }
      });
    });

    // Move items
    $('#btn_submit_move').on('click', function (e) {
      e.preventDefault();
      if (!V.items_move_url) return;
      const number_selected = collect_selected_item_ids();
      const optionValue = $('#destination_inventory').find(':selected').val();
      const move_type = $('#move_type').find(':selected').val();

      $.ajax({
        type: 'POST',
        url: V.items_move_url,
        contentType: 'application/json;charset=UTF-8',
        headers: headerWithCsrf(),
        data: JSON.stringify({
          item_ids: number_selected,
          username: V.username,
          to_inventory_id: optionValue,
          inventory_id: V.inventory_id,
          move_type: move_type
        }),
        success: function () { location.reload(); },
        error: function () { location.reload(); }
      });
    });

    // Export PDF
    $('#btn_export_pdf').on('click', function (e) {
      e.preventDefault();
      if (!V.items_save_pdf_url) return;
      $.ajax({
        type: 'POST',
        url: V.items_save_pdf_url,
        contentType: 'application/json;charset=UTF-8',
        headers: headerWithCsrf(),
        data: JSON.stringify({ inventory_slug: V.inventory_slug, username: V.username }),
        success: function () { location.reload(); },
        error: function () { location.reload(); }
      });
    });

    // Save default fields
    $('#save-fields-btn').on('click', function (e) {
      e.preventDefault();
      const table = $('#item-field-table').DataTable();
      table.search('').draw();
      if (!V.edit_inv_default_fields_url) return;
      const number_selected = [];
      $('input:checkbox[id^="selected-field-"]').each(function () {
        const $this = $(this);
        if ($this.is(':checked')) number_selected.push(parseInt($this.attr('data-itemfield-id')));
      });
      $.ajax({
        type: 'POST',
        url: V.edit_inv_default_fields_url,
        contentType: 'application/json;charset=UTF-8',
        headers: headerWithCsrf(),
        data: JSON.stringify({ field_ids: number_selected, inventory_id: V.inventory_id, username: V.username }),
        success: function () { location.reload(); },
        error: function () { location.reload(); }
      });
    });

    // Collapse/cancel buttons
    $('#add_item_cancel_btn').on('click', function (e) { e.preventDefault(); $('#collapseAddItem').collapse('toggle'); });
    $('#cancel-delete-items-btn').on('click', function (e) { e.preventDefault(); if (typeof deselect_all_checkboxes === 'function') deselect_all_checkboxes('selected-item-'); $('#collapseDeleteItems').collapse('hide'); run_over_checkboxes(); });
    $('#inv-users-cancel-btn').on('click', function (e) { e.preventDefault(); $('#collapseManageUserAccess').collapse('toggle'); });

    // AutoComplete instances use server endpoint from V
    if (typeof autoComplete !== 'undefined' && V.api_user_item_types_url) {
      const buildAuto = (selector, instanceVar) => new autoComplete({
        selector: selector,
        placeHolder: 'Search for types ... ',
        data: {
          src: async (query) => {
            try {
              const source = await fetch(`${V.api_user_item_types_url}?query=${encodeURIComponent(query)}`);
              return await source.json();
            } catch (error) {
              return error;
            }
          }
        },
        threshold: 0,
        autoFill: true,
        resultsList: {
          element: (list, data) => {
            if (!data.results.length) {
              const message = document.createElement('div');
              message.setAttribute('class', 'no_result');
              message.innerHTML = `<span>Save to add new type "${data.query}"</span>`;
              list.prepend(message);
            }
          },
          noResults: true,
          maxResults: undefined
        },
        resultItem: { highlight: true },
        events: {
          input: { selection: (event) => {
              const sel = event.detail.selection.value;
              instanceVar.input.value = sel;
          }
          }
        }
      });

      window.autoCompleteJS = buildAuto('#types_autocomplete', window.autoCompleteJS || {});
      window.autoCompleteJS2 = buildAuto('#types_autocomplete_add_form', window.autoCompleteJS2 || {});
    }

    // Confirm user deletion buttons
    $('[id^="confirmUserDeleteBtn-"]').on('click', function (e) {
      e.preventDefault();
      const $this = $(this);
      const user_id = $this.attr('data-user-id');
      if (!V.delete_user_url) return;
      $.ajax({
        type: 'POST',
        url: V.delete_user_url,
        contentType: 'application/json;charset=UTF-8',
        headers: headerWithCsrf(),
        data: JSON.stringify({ user_id: user_id, inventory_id: V.inventory_id }),
        success: function () { location.reload(); },
        error: function () { location.reload(); }
      });
    });

  }); // document ready
})();