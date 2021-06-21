/* Javascript for WeBWorKXBlock content used inside an iFrame */

function WeBWorKXBlockIframed(runtime, element, initdata) {

    var handlerUrl = runtime.handlerUrl(element, 'submit_webwork_iframed');

    console.log("I was sent rpID ", initdata.rpID);
    console.log("I was sent messDivID ", initdata.messageDivID);
    console.log("I was sent resultDivID ", initdata.resultDivID);
    console.log("All initdata = ", initdata);

    console.log("handlerUrl is ", handlerUrl);

    let problemiframe = document.getElementById(initdata.rpID);
    let messageDiv = document.getElementById(initdata.messageDivID);
    let resultDiv = document.getElementById(initdata.resultDivID);

    var hideShowAnswers = false;
    var hidePreview = false;
    var hideSubmit = false;

    function handleResponse(result) {
        messageDiv.innerHTML = "";
        resultDiv.innerHTML = "";

        if (result.success) {
            problemiframe.srcdoc = result.renderedHTML;

            if (result.scored) {
                resultDiv.innerHTML = result.score;
            }
            if (result.message) {
                messageDiv.innerHTML = result.message;
            }
        } else {
            if (result.scored) {
                resultDiv.innerHTML = result.score;
            }
            if (result.message) {
                messageDiv.innerHTML = result.message;
            }
        }
        hideShowAnswers = result.hideShowAnswers;
        hidePreview = result.hidePreview;
        hideSubmit = result.hideSubmit
        // Does it help to add these here?
        insertListener();
        hideButtons();
    }

    function hideButtons(result) {
        let problemForm = problemiframe.contentWindow.document.getElementById('problemMainForm')  // don't croak when the empty iframe is first loaded
        if (!problemForm) {
            console.log('hideButtons: could not find form! has a problem been rendered?');
            return;
        }
        console.log('hideButtons: enabling/disabling show answers');
        var my_buttons = problemiframe.contentWindow.document.getElementsByName("showCorrectAnswers") // name in standalone
        my_buttons.forEach(button => { button.disabled = hideShowAnswers; })
        my_buttons = problemiframe.contentWindow.document.getElementsByName("WWcorrectAns") // name in html2xml
        my_buttons.forEach(button => { button.disabled = hideShowAnswers; })

        console.log('hideButtons: enabling/disabling preview');
        my_buttons = problemiframe.contentWindow.document.getElementsByName("previewAnswers") // name in standalone
        my_buttons.forEach(button => { button.disabled = hidePreview; })
        my_buttons = problemiframe.contentWindow.document.getElementsByName("preview") // name in html2xml
        my_buttons.forEach(button => { button.disabled = hidePreview; })

        console.log('hideButtons: enabling/disabling submit');
        my_buttons = problemiframe.contentWindow.document.getElementsByName("submitAnswers") // name in standalone
        my_buttons.forEach(button => { button.disabled = hideSubmit; })
        my_buttons = problemiframe.contentWindow.document.getElementsByName("WWsubmit") // name in html2xml
        my_buttons.forEach(button => { button.disabled = hideSubmit; })
    }

    // The activateButton() code is based on code from
    // https://github.com/drdrew42/renderer/blob/master/public/navbar.js
    // That code is licensed under GPL 3.0

    function activeButton() {
        let problemForm = problemiframe.contentWindow.document.getElementById('problemMainForm')
        if (!problemForm) {
            console.log('could not find form! has a problem been rendered?');
            return;
        }
        problemForm.querySelectorAll('.btn-primary').forEach(
            button => {
                button.addEventListener('click', () => {
                    console.log('clicked: ', button);
                })
            })
    }

    // The insertListener() code is based on code from
    // https://github.com/drdrew42/renderer/blob/master/public/navbar.js
    // That code is licensed under GPL 3.0

    function insertListener() {
        let problemForm = problemiframe.contentWindow.document.getElementById('problemMainForm')  // don't croak when the empty iframe is first loaded
        if (!problemForm) {
            console.log('could not find form! has a problem been rendered?');
            return;
        }
        problemForm.addEventListener('submit', event => {
            event.preventDefault();

            let formData = new FormData(problemForm)

            let clickedButton = event.submitter;
            if (clickedButton == null) {
                console.log('Error could not determine which button was clicked');
                alert('Error could not determine which button was clicked');
                return 0;
            }
            formData.set(clickedButton.name, clickedButton.value);
            formData.set("submit_type", clickedButton.name);

            /* Convert it to JSON: Next few lines of code based on https://ilikekillnerds.com/2017/09/convert-formdata-json-object/ */
            const formDataEntries = formData.entries();

            let formJsonData = {};

            for (const [key, value] of formDataEntries) {
                formJsonData[key] = value;
            }
            /* End of code based on  https://ilikekillnerds.com/2017/09/convert-formdata-json-object/ */

            $.ajax({
                type: "POST",
                url: handlerUrl,
                data: JSON.stringify(formJsonData),
                success: handleResponse,
                error: handleResponse
            });
            return 0;
        })
    }

    function initialLoad() {
        let formJsonData = { "submit_type": "initialLoad" };
        $.ajax({
            type: "POST",
            url: handlerUrl,
            data: JSON.stringify(formJsonData),
            success: handleResponse,
            error: handleResponse
        });
        return 0;
    }
    // Do initial load

    // The approach using problemiframe.addEventListener is based on code from
    // https://github.com/drdrew42/renderer/blob/master/public/navbar.js
    // That code is licensed under GPL 3.0

    problemiframe.addEventListener('load', () => {
        console.log('loaded...' + initdata.rpID);
        activeButton();
        insertListener();
        hideButtons();
    })
    initialLoad();
}
