/**
 * Javascript for LTI Consumer Studio View.
*/
function WebWorkXBlockInitStudio(runtime, element) {

    alwaysHideList = [ 'settings_are_dirty' ];

    // Run parent function to set up studio view base JS
    StudioEditableXBlockMixin(runtime, element);

    // Define lists of fields to hide in different cases
    const hide_for_settings_from_ID  = [
        "ww_server_type",
        "ww_server_api_url",
        "ww_server_static_files_url",
        "auth_data"
    ];
    const show_for_settings_from_ID  = [
        "ww_server_id_options",
        "ww_server_id"
    ];

    // Define lists of fields to show only for standalone renderer
    const show_for_standalone_only  = [ ];

    // Define lists of fields to show only for html2xml renderer
    const show_for_html2xml_only  = [ ];

    /**
     * Query a field using the `data-field-name` attribute and hide/show it.
     *
     * params:
     *   field: string. Value of the field's `data-field-name` attribute.
     *   visible: boolean. `true` shows the container, and `false` hides it.
     */
    function setFieldVisibility(field, visible) {
        const componentQuery = '[data-field-name="'+ field + '"]';
        const fieldContainer = element.find(componentQuery);
        console.log( "Running setFieldVisibility for ", field, " asked to set to ", visible);

        if (visible) {
            fieldContainer.show();
        } else {
            fieldContainer.hide();
        }
    }
    function setDirty() {
        console.log( "Running setDirty");
        $(element).find('#xb-field-edit-settings_are_dirty').val(1);
    }

    /**
     * Can be used to modify which fields are shown,
     * depending on which server type is in use
     */
    function modifyFieldVisibility() {
        const wwSettingsTypeField = $(element).find('#xb-field-edit-settings_type');
        const selectedSettingsType = wwSettingsTypeField.children("option:selected").val();

        const wwServerTypeField = $(element).find('#xb-field-edit-ww_server_type');
        const selectedServerType = wwServerTypeField.children("option:selected").val();

        wwServerIDField = $(element).find('#xb-field-edit-ww_server_id');
        selectedServerID = wwServerIDField.children("option:selected").val();

        console.log( "Started modifyFieldVisibility... \n",
        "    selectedSettingsType = " , selectedSettingsType, "\n",
        "    selectedServerID     = " , selectedServerID,     "\n",
        "    selectedServerType   = " , selectedServerType  , "\n"
        );

        // Adjust field visibility for settings from ID vs. manual
        if (selectedSettingsType == 1) {
            console.log( "In == 1 case");
            hide_for_settings_from_ID.forEach(function (field) {
                setFieldVisibility(field, false);
            });
            show_for_settings_from_ID.forEach(function (field) {
                setFieldVisibility(field, true);
            });
            return false;
        }
        if (selectedSettingsType == 2) { // manual
            console.log( "In == 2 case");
            hide_for_settings_from_ID.forEach(function (field) {
                setFieldVisibility(field, true);
            });
            show_for_settings_from_ID.forEach(function (field) {
                setFieldVisibility(field, false);
            });

            show_for_standalone_only.forEach(function (field) {
                setFieldVisibility(
                    field,
                    selectedServerType === 'standalone'
                );
            });
            show_for_html2xml_only.forEach(function (field) {
                setFieldVisibility(
                    field,
                    selectedServerType === 'html2xml'
                );
            });
            return false;
        }
    }

    // Call once component is instanced to hide fields
    modifyFieldVisibility();
    alwaysHideList.forEach(function (field) {
        setFieldVisibility(field,false);
    });
//    toHideList.forEach(function (field) {
//        setFieldVisibility(field,false);
//    });

    // Bind to onChange method of settings_type selector
    $(element).find('#xb-field-edit-settings_type').bind('change', function() {
        console.log( "Running onChange for settings_type");
        modifyFieldVisibility();
        setDirty();
     });

    // Bind to onChange method of ww_server_id selector
    $(element).find('#xb-field-edit-ww_server_id').bind('change', function() {
        console.log( "Running onChange for ww_server_id");
        modifyFieldVisibility();
        setDirty();
     });

     // Bind to onChange method of ww_server_type selector
    $(element).find('#xb-field-edit-ww_server_type').bind('change', function() {
        console.log( "Running onChange for ww_server_type");
        modifyFieldVisibility();
        setDirty();
     });

     // Make ww_server_id_options read only
    $(element).find('#xb-field-edit-ww_server_id_options').attr('readonly', true);


}
