let page_vars = $('#page-vars').data();
$(document).ready(function () {

    check_checkboxes()

    $('#my-fields-table').DataTable({
        "searching": true,
        paging: false,
        rowReorder: true,
        info: true
    });
});

$('[id^=fieldEdit]').click(function () {
    let field_id = $(this).attr('data-field-id');
    let field_name = $(this).attr('data-field-name');
    let field_type = $(this).attr('data-field-type');

    $('#edit_form_field_id').val(field_id)
    $('#edit_form_field_name').val(field_name)

    $("div.field_type select").val(field_type);


});

$('input:checkbox[id^="selected-item-"]').on("click", function (e) {
    check_checkboxes();
});

$("#cancel-delete-templates-btn").on("click", function (e) {
    deselect_all_checkboxes("selected-item-")
    $("#collapseDeleteFields").collapse("hide");
});

function check_checkboxes() {
    let number_selected = checkbox_count("selected-item-")

    let delete_collapse_btn_selector = $('#delete-fields-btn-collapse');
    let delete_btn_selector = $('#delete-fields-btn');
    let delete_span_selector = $('#delete-fields-span');

    if (number_selected > 0) {
        delete_collapse_btn_selector.attr('href', '#collapseDeleteFields');
        delete_btn_selector.css("pointer-events", "auto");
        delete_span_selector.css('color', 'red');
        delete_btn_selector.prop('disabled', false);
        delete_collapse_btn_selector.prop('disabled', false);
        delete_btn_selector.attr('disabled', 'disabled');

    } else {
        delete_collapse_btn_selector.removeAttr('href');
        delete_btn_selector.css("pointer-events", "none");
        delete_span_selector.css('color', 'lightgray');
        delete_btn_selector.prop('disabled', true);
        delete_collapse_btn_selector.prop('disabled', true);
        delete_btn_selector.removeAttr('disabled');

    }
}

$("#confirm-delete-fields-btn").on("click", function (e) {
    e.preventDefault();

    let selected_list = get_selected_checkbox_ids("selected-item-", "data-field-id")

    $.ajax({
        type: "POST",
        url: page_vars['del_field_url'],
        contentType: 'application/json;charset=UTF-8',
        headers: {
            "X-CSRFToken": page_vars['csrf'],
        },
        data: JSON.stringify(
            {
                'field_ids': selected_list,
                'username': page_vars['username'],
            }
        ),
        success: function () {
            location.reload();
        },
        error: function () {
            location.reload();
        }
    });
});