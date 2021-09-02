# WeBWorK XBlock design

## Introduction

WeBWorK is an open-source computer-aided assessment system designed to support problems in mathematics, and related disciples.

Recent versions of the WeBWorK system (the `html2xml` subsystem), and the Standalone renderer https://github.com/drdrew42/renderer provide APIs which allow WeBWorK problems to be embedded in external systems.

The WeBWorK XBlock is designed to leverage those capabilities to allow embedding WeBWorK problems in an Open edX based MOOC course.

## Architecture

The WeBWorK XBlock is designed to function as a Man in the Middle (MiTM) system, where all end-user (student) interactions is carried out in direct communications with the Open edX server, including the loading of the main problem content, and the submission of answers to be graded. The XBlock running inside the Open edX server will manage all user state information (student identity, scores, parameters related to the problem assigned, answers submitted) and will communicate with a back-end WeBWorK problem renderer to retrieve the problem text and data, to submit answers received from a student, and to retrieve the feedback and score for such submissions. The relevant data will be sent back to the end user's browser.

The WeBWorK problems will be enclosed in an iFrame, where the main problem text will be pushed into the iFrame via the `srcdoc` attribute using a JavaScript handler. The JavaScript code outside the XBlock will inform the `submit` buttons inside the iFrame to pass submissions to a JavaScript function running in the encapsulating web page, and that JavaScript handler will initiate an AJAX call to the relevant handler routine on the Open edX server. The internal iFrame will be retreive all additional resources required (JavaScript code, CSS styling, images, etc.) from the relevant web locations as instructed to by the HTML code of a problem. The initial problem loading will also be done via the same type of AJAX call, whereby enabling the main page structure to load quickly, and deferring the calls to the WeBWorK back-end to be handled later on during the page load process.

The XBlock users the XBlock Fields API, and in particular fields with Scope.user_state to manage and persist data related to an individual students use of a problem, including the (best) score earned, the number of graded submissions processed, etc.

## Learner privacy and security aspects

The XBlock running on the Open edX server will not provide any personal identification information (name, email, user ID, etc.) to the WeBWorK problem renderer being called.

However, as certain types of WeBWorK problems can depend on a `psvn` parameter, which is typically fixed for a given student within the framework of a "problem set", a feature which allows sequences of problems to share a common seed for randomization, that parameter can be used to some extent to identify (group) learners. Both to allow additional flexibility in terms of the use of `psvn` dependent problems and to allow somewhat mitigating the "fingerprint" created by the `psvn` parameter, the XBlock allows a user to have several indexed `psvn` values, and different problems/problem groups can request a different `psvn` value be used.

## Core capabilities

* The settings for the back-end problem renderer are typically configured using the "Other course settings" JSON object, so main settings can be edited at the course level.
  * The capability to provide such settings for individual problems exists, but use of that capability is not recommended.

* The `studio_view` method allows the course author to edit the relevant settings (of type Scope.settings), and does validation of the fields for which reasonable local validation is possible.
  * Settings whose validation requires contact with the remote WeBWorK server are not validated.
    * This includes authentication data, the `problem` name (the path to the problem file used on the backend), ???
  * The language in which back-end generated strings (from outside the problem code) such as score messages should be generated. That setting effects the back-end behavior and depends on there being a suitable `.po` file on the backend. (Setting `ww_language`) The standalone renderer does not yet support this.
  * Main settings:
    * `problem` = path to problem file on the back-end.
    * `max_allowed_score` = total number of points the problem can earn.
    * `ww_language` = language used for "system" messages by the back-end system.
    * `max_attempts` = maximum number of for-credit submissions allowed. (0 for unlimited)
    * `weight` = the weight of the problem (when different problem grades are merged by Open edX for a section grade)
    * `psvn_key` = which `psvn` to use from the set of such values for each given user.
      * Allows some problems to use a `psvn` of key 1, others to use one of key 2, etc.
    * Settings related to controlling which back-end server is contacted.
    * Settings which control when and whether correct answers, hints, and solutions are made available.
    * Several technical settings related to the display / processing of the problem.

* The XBlock permits problems to have a deadline or not.
  * When there is a deadline:
    * For credit submission are allowed until the deadline + the standard grace period allowed.
    * Submission to the problem will be locked for a configurable number of hours after the grace period, after which submissions are again allowed, receive full feedback, but the recorded score is not updated.
    * Viewing the correct answers is only allowed in the "post deadline" period.
  * When there is no deadline:
    * For credit submission are allowed until the permitted attempt limit is exceeded.
    * After that, submissions are allowed, receive full feedback, but the recorded score is not updated.
    * Viewing the correct answers is allowed after all graded submissions are made, or after suitable many attempts are made.
  * The handling of the different cases in handled using the `PPeriods` and `WWProblemPeriod` classes.
  
* Problems can limit the number of graded submissions permitted or not.
  * Graded attempts are counted by the XBlock using both a simple counter, and a pair of counters similar to the data expected by the back-end systems.

* The most critical method is `submit_webwork_iframed` which handles all the AJAX calls from the client side.
  * It contains the logic to determine what actions are permitted and to carry them out by making a suitable call the the external WeBWorK problem renderer.
  * It managed parsing the reply from the back-end server and preparing the reply to send to the end user's browser.
  * This code is quite detailed to cover all the deadline/attempts state conditions which determine when a given action request is permitted.
  * Other than initial setup, the code handles both possible back-end server types at once.

* Messages are generated to display the current and recorded best score, the number of attempts allowed and used so far, etc.

* The XBlock will provide information to the AJAX calls about which submission buttons should be active and which should be disabled.
  * In any case, the code also verifies and prevents use of capabilities which are not currently intended to be available to the end user. (For example, a "Show Correct Answers" submission will not be processed when it is not permitted and will instead trigger a suitable message to be diplayed to the end user.

* Data on submitted answers will be stored using the extended `CSMH` in a similar manner to standard Open edX problems.
  * The XBlock code attempts to carefully select which answer related data provided by the WeBWorK server is persisted, and uses Python dictionaries to collect the names of keys to be saved.
  * At present it is necessary to make 2 very small modifications to enable the WeBWorK XBlock to use that facility, one to enable storing the data, and one to automatically enable course staff to view the submissions using the same preexisting facilty used by `problem`.
  * A small change to make configuring which XBlocks can use those feature via the system configuration files was developed.
     * We intend to submit a pull request with those small changes to the core project.
  * Some experimentation was done with persisting the submissions using the `submissions` API, and commented out code to use that alternative was left in the code for possible use in the future.

* The `student_view` method and the main `html` fragment file and `js` file are quite small, as problem loading is done via an AJAX call similar to that used to submit answers, etc.
  * There is a capability to display some debugging information collected into a JSON object in this method, and commented out sample code.

## Additional technical details

### Basic sanitization of submitted data
* AJAX calls are sanitized to remove potential form keys which have an operation meaning in the WeBWorK renderer backends, so that only settings intentionally set by the XBlock will be sent to the back-end WeBWorK problem renderer.
  * Ongoing maintenance of the list of keys to be cleared is necessary as new keys may be added to the rendering servers.

### `show_in_read_only_mode`
`show_in_read_only_mode` is enabled, so staff can see the version of a problem assigned to a given student.

### `unique_id`

A `unique_id` of score `Scope.user_state` is used to identify HTML elements belonging to a given problem, so the JavaScript methods used when processing the reply to an AJAX call can modify the data in the correct locations on the page (that belonging to the correct problem).

### Calls to the backend servers are routed via
  * `request_webwork_standalone` (uses HTTP `POST`) and initial work to send the critical settings via an encrypted JWT was implemented. More work is needed on this.
  * `request_webwork_html2xml`(uses HTTP `GET`)
These are the only 2 methods via which calls to the back-end renderers can be made.

They are called via `request_webwork` which adds some final settings to the request before one of those options is called.
  * This prevents the need to make those settings in multiple locations elsewhere in the code.

### Problem processing on the edX side
* Extraction and processing of the HTML data is handled by `_problem_from_json`
  * For the `html2xml` option relative URLS are modified based on the `server_static_files_url` setting to convert them to full URLS, so the resource will be loaded properly.
* Extraction and processing of responses to AJAX calls, and in particular the collection of data to persist, is handled by
  * `_result_from_json_standalone`
  * `_result_from_json_html2xml`
* These methods remain distinct as the `standalone_style` output of `html2xml` has some key differences from the JSON output format of the Standalone renderer.

### ScorableXBlockMixin

The XBlock implements several methods required by the `ScorableXBlockMixin`.

### Internationalization
* Initial work on internationalization so that the XBlock can prepare messages to the end users in different languages is being implemented.
  * This being done in the manner recommended by the Open edX project using `.po` and `.mo` files, but in the initial phase in an ad-hoc manner.
  * The initial version will support English and Hebrew.

## Primary web resources from the WeBWorK project

* https://openwebwork.org/
* https://webwork.maa.org/
* https://webwork.maa.org/wiki/WeBWorK_Main_Page
* https://github.com/openwebwork
