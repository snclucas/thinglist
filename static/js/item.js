$(document).ready(function () {
    tinymce.init({
        selector: 'textarea#form_item_description',
        height: 300,
        //theme: 'modern',
        //theme: 'silver',
        menubar: false,
        forced_root_block: '',
        plugins: [
            'advlist lists link hr pagebreak',
            'searchreplace wordcount code',
            'nonbreaking table',
            'paste textcolor textpattern visualchars wordcount'
        ],
        toolbar1: 'bold italic | alignleft aligncenter alignright alignjustify | bullist numlist outdent indent',
        image_advtab: false
    });




    $('[id^="delete-related-"]').click(function (e) {
            e.preventDefault();

            let item1 = $(this).attr('data-item1-id');
            let item2 = $(this).attr('data-item2-id');

            $.ajax({
                type: "POST",
                url: unrelate_items_url,
                contentType: 'application/json;charset=UTF-8',
                headers: {
                    "X-CSRFToken": csrf_token,
                },
                data: JSON.stringify(
                    {
                        'item1': item1,
                        'item2': item2,
                        'inventory_slug': inventory_slug,
                        'username': username
                    }
                ),
                success: function (e) {
                    location.reload();
                },
                error: function (e) {
                    location.reload();
                }
            });
        });





    // Autofocus the first field inside the edit collapse when Edit is triggered
    $(document).on('click', '[data-bs-toggle="collapse"][href="#collapseExample"], [data-bs-toggle="collapse"][data-bs-target="#collapseExample"]', function (e) {
        try {
            const $collapse = $('#collapseExample');
            if ($collapse.length) {
                $collapse.one('shown.bs.collapse', function () {
                    try {
                        const $form = $collapse.find('form').first();
                        if ($form.length) {
                            const $focusEl = $form.find('input:not([type=hidden]):not(:disabled), select:not(:disabled), textarea:not(:disabled), button:not(:disabled)').filter(':visible').first();
                            if ($focusEl && $focusEl.length) {
                                setTimeout(function () { $focusEl.focus(); }, 10);
                            }
                        }
                    } catch (err) {
                        console.warn('focus after show failed', err);
                    }
                });

                try {
                    $collapse.collapse('show');
                } catch (err) {
                    $collapse.addClass('show').attr('aria-expanded', 'true');
                }
            }
        } catch (e) {
            console.warn('Could not auto-open/focus item edit collapse', e);
        }
    });

    // Validate URL input only when non-empty before submitting the edit form
    $(document).on('submit', 'form[action*="edit_item"]', function (e) {
        try {
            const $form = $(this);
            const $url = $form.find('.validationUrl');
            if (!$url.length) return true; // no URL field

            const val = $url.val() ? String($url.val()).trim() : '';
            // clear previous validation state
            $url.removeClass('is-invalid');

            if (val === '') {
                // empty is allowed
                return true;
            }

            // Normalize and validate using URL constructor when possible
            let valid = false;
            try {
                // If user omitted scheme, try adding http:// to validate host-only input
                let testVal = val;
                if (!/^\w+:\/\//.test(testVal)) {
                    // allow relative URLs starting with '/'
                    if (testVal.startsWith('/')) {
                        // treat as valid relative path
                        valid = true;
                    } else {
                        testVal = 'http://' + testVal;
                    }
                }

                if (!valid) {
                    const u = new URL(testVal);
                    // ensure there's a hostname for absolute URLs
                    valid = !!u.hostname;
                }
            } catch (err) {
                valid = false;
            }

            if (!valid) {
                e.preventDefault();
                e.stopPropagation();
                $url.addClass('is-invalid');
                // focus the input so the user can correct
                $url.focus();
                return false;
            }

            // otherwise allow submit
            return true;
        } catch (err) {
            console.error('URL validation error', err);
            return true; // fail open
        }
    });


});