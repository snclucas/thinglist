$(document).ready(function () {
    tinymce.init({
        selector: 'textarea#form_item_description',
        height: 300,
        theme: 'modern',
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





});