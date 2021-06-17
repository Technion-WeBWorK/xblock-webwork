/* Javascript for WeBWorKXBlock for use with the standalone renderer */

function WeBWorKXBlockStandalone(runtime, element, initdata) {

    var handlerUrl = runtime.handlerUrl(element, 'submit_webwork_standalone');

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
        if (result.hideShowAnswers) {
            hideShowAnswers = result.hideShowAnswers;
        }
        if (result.hidePreview) {
            hidePreview = result.hidePreview;
        }
        if (result.hideSubmit) {
            hideSubmit = result.hideSubmit
        }
    }
    function hideButtons(result) {
        let problemForm = problemiframe.contentWindow.document.getElementById('problemMainForm')  // don't croak when the empty iframe is first loaded
        if (!problemForm) {
            console.log('hideButtons: could not find form! has a problem been rendered?');
            return;
        }
        if (hideShowAnswers) {
            var my_buttons = problemiframe.contentWindow.document.getElementsByName("showCorrectAnswers")
            // my_button.style.visibility = "hidden"
            my_buttons.forEach( button => { button.disabled = true; })
            console.log('hideButtons: disabling show answers');
        }
        if (hidePreview) {
            var my_buttons = problemiframe.contentWindow.document.getElementsByName("previewAnswers")
            // my_button.style.visibility = "hidden"
            my_buttons.forEach( button => { button.disabled = true; })
            console.log('hideButtons: disabling preview');
        }
        if (hideSubmit) {
            var my_buttons = problemiframe.contentWindow.document.getElementsByName("submitAnswers")
            // my_button.style.visibility = "hidden"
            my_buttons.forEach( button => { button.disabled = true; })
            console.log('hideButtons: disabling submit');
        }
    }

    function activeButton() {
        let problemForm = problemiframe.contentWindow.document.getElementById('problemMainForm')
        if (!problemForm) {
            console.log('could not find form! has a problem been rendered?');
            return;
        }
        problemForm.querySelectorAll('.btn-primary').forEach(
            button => {
                button.addEventListener('click', () => {
                    button.classList.add('btn-clicked');
                    console.log('clicked: ', button);
                })
            })
    }

    function insertListener() {
        let problemForm = problemiframe.contentWindow.document.getElementById('problemMainForm')  // don't croak when the empty iframe is first loaded
        if (!problemForm) {
            console.log('could not find form! has a problem been rendered?');
            return;
        }
        problemForm.addEventListener('submit', event => {
            event.preventDefault();

            let formData = new FormData(problemForm)

            let clickedButton = problemForm.querySelector('.btn-clicked')
            formData.set(clickedButton.name, clickedButton.value);
            formData.set("submit_type", clickedButton.name);

            /* Convert it to JSON: https://ilikekillnerds.com/2017/09/convert-formdata-json-object/ */
            const formDataEntries = formData.entries();

            let formJsonData = {};

            for (const [key, value] of formDataEntries) {
                formJsonData[key] = value;
            }

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

    problemiframe.addEventListener('load', () => {
        console.log('loaded...' + initdata.rpID);
        activeButton();
        insertListener();
        hideButtons();
    })
    initialLoad();

}