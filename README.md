# WeBWorK XBlock

## Overview
An edX XBlock that allows embedding WeBWorK problems in an edX course.

LMS functionality usually handled by WeBWorK's webwork2 LMS code will be handled by the edX system
where the functionality is provided by vanilla edX or by the XBlock where necessary.

Problem generation and grading is handled on a remote server which can render WeBWorK problems
(which are coded using the WeBWorK PG problem generation language) and can provide the
XBlock with the necessary JSON formatted output containing the rendered problem and
additional data.

Problems are embedded inside an iFrame, to allow the full power of WeBWorK problems, which depend on
HTML, JavaScript, CSS to function properly without interfering with the other edX content or additional
WeBWorK problems provided in the same edX unit (namely rendered inside the same HTML page).

The XBlock acts as a man-in-the-middle for the primary interactions with WeBWorK. 
Request to load a problem or to submit answers to a problems are all done by requests from the
student's web-browser to the relevant XBlock handler on the edX server. Thus, only the edX server
submits the main "problem requests" (load, grade answers, etc.) to the remote WeBWorK server.
However, all additional problem resources (Javascript files, CSS files, images, etc.) are
requested by the student's web-browser directly from the WeBWorK server.

## Suitable remote WeBWorK back-ends to render the problems

The XBlock can interface to both:
  1. the Standalone renderer
    - https://github.com/drdrew42/renderer
    - In production, access to a standalone render should be done over a SSL/TLS connection (where a proxy in front of the Standalone renderer handles the SSL/TLS).
    - A shared secret is needed which is used to generate an encrypted JWT which acts as proof of authorization to make calls to the `render-api` on the Standalone server.
    - The critical API fields for the Standalone renderer should all be provided inside an encrypted JWT called `problemJWT`. Work is in progress on doing this.
  2. the XMLRPC (`html2xml`) interface of a "daemon course" on a standard WeBWorK server
    - https://github.com/openwebwork/webwork2
    - The code in this repository depends on a modification which allows that subsystem to provide output which is compatible with that of the standalone renderer. The patch is currently a draft pull request at https://github.com/openwebwork/webwork2/pull/1426 .
    - Use of `html2xml` of a daemon course makes use of a username/password which is used to authenticate requests to the remote server.

The necessary settings for a server should be set provided using the course's "Other course settings" JSON object, so it is available to all problems in a course, and can be centerally modified for them all.
  - The code also supports providing the server configuration/authentication data in each problems, but doing so is highly discouraged.

## Feature overview

### Course level configutation
* Several main settings are provided to all the webwork XBlocks in a course via data provided using the "Other course settings" feature (available since the Ironwood release - see https://www.edunext.co/articles/discover-open-edx-ironwood)

### Problem administration/configuration
* The settings of each XBlock instance:
  * Define what problem is to be generated (specified as a path the the PG file)
  * Set the maximum number of submission attempts which can be made for credit.
  * FIXME Set grade weight (e.g. a unit with 3 problems, one 40 percent the other two 30)
  * and more FIXME
* Course staff can view the customized version of a problem assigned to any selected student.

### Release dates / grace period / deadlines 
* Release of content is handled by edX in the usual manner.
* Deadlines are set in the usual edX manner, and the XBlock will process problems differently before the deadline, during a "lockdown" period after the deadline, and after the "lockdown" period ends.
* The XBlock respects the edX `graceperiod` set for a course.

### Management of internal problem settings
* The XBlock manages the random seeds (`problemSeed` and `psvn`) used to randomize the problems.
  * `psvn` is used by WeBWorK to randomize a set of problems using the same seed for a given user.
  * The XBlock stores a dictionary of possible values, and retrives the relevant one based on a problem setting (`psvn_key` which defaults to 1).
    * This allows different sequences of problems to use a different `psvn` is necessary.
  * A given `psvn` is constant for a given user in the system (across courses) for all problems which use it, based on the manner in which the XBlock Field's API `Scope.preferences` behaves. 
    * As a result, a course can provide a `psvn_shift` in the main settings which will be used in an entire course. (It defaults to 0.)
* The XBlock handles the counting of attempts made and enforces the limits on the number of graded attempts.
* The XBlock actively regulates when the "Show Answer" option of WeBWorK is active and will reject attempts to request answers that when it is not allowed.

### Form processing and problem grading
* When answers to a WeBWorK problem are submitted, the submission is made to an XBlock handler (the man in the middle) and not directly to the back-end WeBWorK server.
* Submitted form data is processed, sanitized (to remove API/backend fields which only the XBlock should set), and organized into the serialized form expected by the back-end system.
* The necessary data is send from the edX server to the back-end for processing, and the response is then parsed to collect the score, feedback messages, and updated data to be displayed in the problem iFrame.
* The necessary data is sent back to the student's browser to provide the score, the feedback messages, and the update HTML for inside the iFrame.
* Additional messages are sent by the XBlock to be displayed above the iFrame reporting the score, data on the number of attempts made, etc.
* The XBlock handles storing submitted answers, scores, etc. in the edX databases.

### Collection of student submission data
* When the edX server is suitably configured:
  * Data on all submissions, prior scores, etc. are collected in the `courseware_studentmodulehistory` as is done for regular edX (CAPA type) problems.
  * The collected data for a student can be seen by the staff using the "Staff View" of problem (as a certain student).
  * At present, this requires making 2 very small modifications to the core edxplatform code to make access to the relevant features available to a configurable list of XBlocks and not just to `problem`.
  * Without the additional configuration, only the most recent data for each XBlock instance is stored.
* The remote back-end WeBWorK systems are not sent personal identification information from the edX student data about the students.
  * Requests send only the necessary data to render/grade a problem to the back-end.
  * For grading of answers, this includes whatever data a student typed into the input boxes of a WeBWorK question.
