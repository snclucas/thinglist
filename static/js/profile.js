let page_vars = $('#page-vars').data();

$(document).ready(function () {

    $('#user-notifications-table').DataTable({
        "searching": true,
        paging: true,
        ordering: true,
        info: true
    });

    // Toast helper
    function showToast(message, type = 'success', delay = 3000) {
        try {
            const $container = $('#toast-container');
            if (!$container.length) return;
            const toastId = 'toast-' + Date.now();
            const bgClass = (type === 'success') ? 'bg-success text-white' : 'bg-danger text-white';
            const $toast = $(
                `<div id="${toastId}" class="toast ${bgClass}" role="alert" aria-live="assertive" aria-atomic="true">
                    <div class="d-flex">
                        <div class="toast-body">${message}</div>
                        <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button>
                    </div>
                </div>`
            );
            $container.append($toast);
            const toastEl = document.getElementById(toastId);
            const bsToast = new bootstrap.Toast(toastEl, { delay: delay });
            bsToast.show();
            // remove after hidden
            toastEl.addEventListener('hidden.bs.toast', function () { $toast.remove(); });

            // write into ARIA live region for screen readers
            try {
                const $live = $('#toast-live-region');
                if ($live.length) {
                    $live.text(message);
                }
            } catch (e) { console.warn('live region update failed', e); }
        } catch (e) {
            console.warn('showToast error', e);
            alert(message);
        }
    }

    // Helper to disable/enable form buttons and show spinner
    function setFormLoading($form, loading) {
        const $btn = $form.find('button[type=submit]');
        if (loading) {
            $btn.prop('disabled', true);
            $btn.data('orig-text', $btn.html());
            $btn.html(`<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Saving...`);
        } else {
            $btn.prop('disabled', false);
            if ($btn.data('orig-text')) $btn.html($btn.data('orig-text'));
        }
    }

    // AJAX submit handler for add-item and add-list forms inside profile collapses
    $(document).on('submit', '#collapseProfileAddItem form, #collapseProfileAddList form', function (e) {
        e.preventDefault();
        const $form = $(this);
        const $collapse = $form.closest('.collapse');
        const url = $form.attr('action');
        const method = ($form.attr('method') || 'POST').toUpperCase();

        setFormLoading($form, true);

        const fd = new FormData(this);

        // include CSRF header as additional protection
        const headers = {};
        if (page_vars && page_vars['csrf']) headers['X-CSRFToken'] = page_vars['csrf'];

        fetch(url, {
            method: method,
            credentials: 'same-origin',
            headers: headers,
            body: fd
        }).then(async (res) => {
            const contentType = res.headers.get('content-type') || '';
            let data = null;
            if (contentType.includes('application/json')) {
                data = await res.json();
            } else {
                // try text
                try { data = await res.text(); } catch (e) { data = null; }
            }

            if (res.ok) {
                // consider success
                const msg = (data && data.message) ? data.message : 'Saved successfully';
                showToast(msg, 'success');
                // hide collapse
                try { $collapse.collapse('hide'); } catch (e) { $collapse.removeClass('show'); }
                // reset form fields
                try { $form[0].reset(); } catch (e) {}
                // refresh profile summary fragment to update counts
                try {
                    fetch(window.location.href, { credentials: 'same-origin' })
                        .then(resp => resp.text())
                        .then(html => {
                            try {
                                const tmp = document.createElement('div');
                                tmp.innerHTML = html;
                                const newSummary = tmp.querySelector('#profile-summary');
                                const $cur = $('#profile-summary');
                                if (newSummary && $cur.length) {
                                    $cur.replaceWith(newSummary);
                                }
                            } catch (e) { console.warn('profile fragment replace failed', e); }
                        }).catch(e => console.warn('fetch profile failed', e));
                } catch (e) { console.warn('refresh profile-summary failed', e); }
                 // optionally refresh part of page or reload to show new item/list
                 // If response provides redirect instruction, follow it
                 if (res.redirected) window.location = res.url;
             } else {
                const errMsg = (data && data.message) ? data.message : 'Failed to save — server returned an error';
                showToast(errMsg, 'danger');
            }
        }).catch((err) => {
            console.error('Submit error', err);
            showToast('Network error, please try again', 'danger');
        }).finally(() => {
            setFormLoading($form, false);
        });

        return false;
    });

});

// existing handlers below

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