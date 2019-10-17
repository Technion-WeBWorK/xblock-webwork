/* Javascript for WeBWorKXBlock. */
(function ($) {
    $.fn.serializeFormJSON = function () {

        var o = {};
        var a = this.serializeArray();
        $.each(a, function () {
            if (o[this.name]) {
                if (!o[this.name].push) {
                    o[this.name] = [o[this.name]];
                }
                o[this.name].push(this.value || '');
            } else {
                o[this.name] = this.value || '';
            }
        });
        return o;
    };
})(jQuery);

function WeBWorKXBlock(runtime, element) {

    var handlerUrl = runtime.handlerUrl(element, 'submit_webwork');

    function handleResopnse(result) {
        $("#edx_message").html("")
        $("#edx_webwork_result").html("")
        if (result.success){
            $("#edx_webwork_result")[0].innerHTML = result.data
            MathJax.Hub.Queue(["Typeset",MathJax.Hub]);
            if (result.scored) {
                $("#edx_message").html("You scored " + result.score + "%.")
            }
        }else{
            $("#edx_message").html(result.message)
        }
    }

    $("#edx_webwork_problem", element).on('click', '#problemMainForm input[type="submit"]',function(e) {

        e.preventDefault(); 

        form_data = $('#problemMainForm').serializeFormJSON()
        form_data["submit_type"] = this.name

        $.ajax({
            type: "POST",
            url: handlerUrl,
            data: JSON.stringify(form_data),
            success: handleResopnse,
            error: handleResopnse
        });
        return 0;
    });

    $(function ($) {
        MathJax.Hub.Queue(["Typeset",MathJax.Hub]);
    });
}
