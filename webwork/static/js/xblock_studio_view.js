/**
 * Javascript for LTI Consumer Studio View.
*/
function WebWorkXBlockInitStudio(runtime, element) {
    // Run parent function to set up studio view base JS
    StudioEditableXBlockMixin(runtime, element);

    // Define WeBWorK config fields - for standalone renderer
    const webworkStandaloneFieldList = [
    ];

    const webworkHtml2xmlFieldList = [
        "ww_course",
        "ww_username",
        "ww_password"
    ];

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

        if (visible) {
            fieldContainer.show();
        } else {
            fieldContainer.hide();
        }
    }

    /**
     * Can be used to modify which fields are shown,
     * depending on which server type is in use
     */
    function toggleWwFields() {
        const wwServerTypeField = $(element).find('#xb-field-edit-ww_server_type');
        const selectedServerType = wwServerTypeField.children("option:selected").val();

        // If ServerType field isn't present, then default to standalone
        if (selectedServerType === undefined) {
            webworkStandaloneFieldList.forEach(function (field) {
                setFieldVisibility(field, true);
            });

            return false;
        }

        webworkStandaloneFieldList.forEach(function (field) {
            setFieldVisibility(
                field,
                selectedServerType === "standalone"
            );
        });

        webworkHtml2xmlFieldList.forEach(function (field) {
            setFieldVisibility(
                field,
                selectedServerType === "html2xml"
            );
        });
    }

    // Call once component is instanced to hide fields
    toggleWwFields();

    // Bind to onChange method of lti_version selector
    $(element).find('#xb-field-edit-ww_server_type').bind('change', function() {
        toggleWwFields();
     });

}
