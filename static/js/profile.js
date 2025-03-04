let page_vars = $('#page-vars').data();

$(document).ready(function () {

    $('#user-notifications-table').DataTable({
        "searching": true,
        paging: true,
        ordering: true,
        info: true
    });

});

$("#import-items-btn").click(function () {
    // disable button
    $(this).prop("disabled", true);
    // add spinner to button
    $(this).html(
        `<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Loading...`
    );
    $("#manage-items-form").submit();
});

$('[id^=confirmNotificationDeleteBtn]').on("click", function (e) {
    e.preventDefault();

    let notification_id = $(this).attr('data-notification-id');

    $.ajax({
        type: "POST",
        url: page_vars['del_notification_url'],
        contentType: 'application/json;charset=UTF-8',
        headers: {
            "X-CSRFToken": page_vars['csrf'],
        },
        data: JSON.stringify(
            {
                'notification_id': notification_id,
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