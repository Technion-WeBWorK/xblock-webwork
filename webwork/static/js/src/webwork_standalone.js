/* Javascript for WeBWorKXBlock for use with the standalone renderer */

function WeBWorKXBlockStandalone(runtime, element, initdata) {

    var handlerUrl = runtime.handlerUrl(element, 'submit_webwork_standalone');

    console.log( "I was sent rpID ", initdata.rpID );
    console.log( "handlerUrl is ",   handlerUrl );

    let problemiframe = document.getElementById( initdata.rpID );

    function handleResponse(result) {
        $("#edx_message").html("");
        $("#edx_webwork_result").html("");
        if (result.success){
	    problemiframe.srcdoc = result.renderedHTML;
/* FIXME
            $("#edx_webwork_result")[0].innerHTML = result.data;
*/

            if (result.scored) {
                $("#edx_message").html("You scored " + result.score + "%.")
            }
        } else {
            $("#edx_message").html(result.message)
        }
    }

    problemiframe.addEventListener('load', () =>{
	console.log('loaded...');
	activeButton();
	insertListener();
    })

    function activeButton() {
	let problemForm = problemiframe.contentWindow.document.getElementById('problemMainForm')
	if (!problemForm) {
	    console.log('could not find form! has a problem been rendered?');
	    return;
	}
	problemForm.querySelectorAll('.btn-primary').forEach(button=>{
	    button.addEventListener('click', () =>{
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
	problemForm.addEventListener('submit', event=>{
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
		data: JSON.stringify( formJsonData ),
		success: handleResponse,
		error: handleResponse
            });
            return 0;

	})
    }
}
