ct_$('html').ultimateGDPR({
    popup_style: {
        position: 'bottom-panel', // bottom-left, bottom-right, bottom-panel, top-left, top-right, top-panel
        distance: '20px', // distance betwen popup and window border
        box_style: 'classic', // classic, modern
        box_shape: 'rounded', // rounded, squared
        background_color: '#fff584', // color in hex
        text_color: '#542d04', // color in hex
        button_shape: 'rounded', // squared, rounded
        button_color: '#e1e1e1', // color in hex
        button_size: 'normal', // normal, large
        box_skin: 'skin-dark-theme', // skin-default-theme, skin-dark-theme, skin-light-theme
        gear_icon_position: 'bottom-left', // top-left, top-center, top-right, center-left, center-right, bottom-left, bottom-center, bottom-right
        gear_icon_color: '#6a8ee7', //color in hex
    },
    popup_options: {
        parent_container: 'body', // append plugin html to this element selector
        always_show: false, // true, false, when true popup is displayed always even when consent is given
        gear_display: false, // true, false when true displays icon with cookie settings
        popup_title: 'Cookies Information', // title for popup
        popup_text: 'To make this site work properly, we sometimes place small data files called cookies on your device. Most websites do this.', // text for popup
        accept_button_text: 'Accept', // string, text for accept button
        reject_button_text: 'Reject', // string, text for reject button
        read_button_text: 'Read More', // string, text for read more button
        read_more_link: '', // string, link to the Read More page
        advenced_button_text: 'Change Settings', // string, text for advenced button
        grouped_popup: true, // true, false, when true cookies are grouped
        default_group: 'group_1', // string: name, select group that will be selected by default
        content_before_slider: '<h2>Privacy settings</h2><div class="ct-ultimate-gdpr-cookie-modal-desc"><p>Decide which cookies you want to allow.</p><p>You can change these settings at any time. However, this can result in some functions no longer being available. For information on deleting the cookies, please consult your browser’s help function.</p> <span>Learn more about the cookies we use.</span></div><h3>With the slider, you can enable or disable different types of cookies:</h3>',
        // string: this content will be displayed before cookies slider, html tags alowed
        accepted_text: 'This website will:',
        declined_text: "This website won't:",
        save_btn: 'Save & Close', // string, text for modal close btn
        prevent_cookies_on_document_write: false, // prevent cookies on document write when there is no agreement for cookies
        check_country: false,
        countries_prefixes: ['AT', 'BE', 'BG', 'HR', 'CY', 'CZ', 'DK', 'EE', 'FI', 'FR', 'DE', 'GR', 'HU', 'IE', 'IT', 'LV', 'LT', 'LU', 'MT', 'NL', 'PL', 'PT', 'RO', 'SK', 'SI', 'ES', 'SE', 'GB'],
        cookies_expire_time: 30, // set number of days, you can use 0 for session only or 'unlimited'
        cookies_path: '/', // sets custom path use / for global, '/your_path' for custom path or 'current' for current path
        reset_link_selector: '.ct-uGdpr-reset',
        first_party_cookies_whitelist: [],
        third_party_cookies_whitelist: [],
        cookies_groups_design: 'skin-1', // skin-1, skin-2, skin-3
        assets_path : 'assets', // absolute path to directory with assets
        video_blocked: 'This content is blocked!',
        iframe_blocked: false,
        cookie_popup_close_color:'#fff',
        close_popup_text: '', // Close popup text (If empty, button X(close) will display. If not, it will display the text)
        cookies_groups: {
            group_1: {
                name: 'Essential', // string: name
                enable: true, // true, false, you can disable this group by using false
                icon: 'fas fa-check', // string icon class from font-awesome see -> http://fontawesome.io
                list: ['Remember your cookie permission setting', 'Allow session cookies', 'Gather information you input into a contact forms, newsletter and other forms across all pages', 'Keep track of what you input in shopping cart', 'Authenticate that you are logged into your user account', 'Remember language version you selected'], // array list of options
                blocked_url: [], // array list of url blocked scripts
                local_cookies_name: [], // array, list of local cookies names
            },
            group_2: {
                name: 'Functionality', // string: name
                enable: true, // true, false, you can disable this group by using false
                icon: 'fas fa-cog', // string icon class from font-awesome see -> http://fontawesome.io
                list: ['Remember social media settings', 'Remember selected region and country',],
                blocked_url: [], // array list of url blocked scripts
                local_cookies_name: [], // array, list of local cookies names
            },
        },
    },
    age_popup_style: {
        position: 'top-panel', // bottom-left, bottom-right, bottom-panel, top-left, top-right, top-panel
        distance: '20px', // distance between popup and window border
        box_style: 'classic', // classic, modern
        box_shape: 'rounded', // rounded, squared
        background_color: '#fff584', // color in hex
        text_color: '#542d04', // color in hex
        button_shape: 'rounded', // squared, rounded
        button_color: '#e1e1e1', // color in hex
        box_skin: 'skin-dark-theme', // skin-default-theme, skin-dark-theme, skin-light-theme
    },
    age_popup_options: {
        parent_container: 'body', // append plugin html to this element selector
        always_show: false, // true, false, when true popup is displayed always even when consent is given
        popup_title: 'Age verification', // title for popup
        popup_text: 'Lorem ipsum dolor sit amet, consectetur adipisicing elit, sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, quis nostrud exercitation.', // text for popup
        age_limit: 13, // age limit to enter
        assets_path : 'assets', // absolute path to directory with assets
        disable_popup: true, // true/false, when true popup will be disabled and hidden on the website
    },
    forms: {
        prevent_forms_send: false, // true, false, when enabled forms get checkbox with info that need to be checked for form send
        prevent_forms_text: 'I consent to the storage of my data according to the Privacy Policy', // string: information for checkbox info
        prevent_forms_exclude: [], // array of selectors (classes, id), this forms will be excluded from prevent
    },
    configure_mode: {
        on: false,
        parametr: '?configure123456',
        dependencies: ['assets/css/ct-ultimate-gdpr.min.css', 'https://use.fontawesome.com/releases/v5.0.13/css/all.css'],
        debug: false, // bool: true false, debug mode on/off (showing all 3rd party cookies urls, blockes urls names of all local cookies and names of blocked local cookies )
    }
});