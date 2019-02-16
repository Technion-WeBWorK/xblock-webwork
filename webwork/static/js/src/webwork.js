/* Javascript for WeBWorKXBlock. */
function WeBWorKXBlock(runtime, element) {

    function updateCount(result) {
        $('.count', element).text(result.count);
    }

    var handlerUrl = runtime.handlerUrl(element, 'submit_webwork');

    $('p', element).click(function(eventObject) {
        $.ajax({
            type: "POST",
            url: handlerUrl,
            data: JSON.stringify({"increase_by": 1}),
            success: updateCount
        });
    });

    $(function ($) {

    });
}
