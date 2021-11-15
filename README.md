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
     - The critical API fields for the Standalone renderer are now all be provided inside an encrypted JWT called `problemJWT` to make them resistant to tampering.
  2. the XMLRPC (`html2xml`) interface of a "daemon course" on a standard WeBWorK server
     - https://github.com/openwebwork/webwork2
     - The code in this repository depends on a modification which allows that subsystem to provide output which is compatible with that of the standalone renderer. The patch is currently a draft pull request at https://github.com/openwebwork/webwork2/pull/1426 .
     - Use of `html2xml` of a daemon course makes use of a username/password which is used to authenticate requests to the remote server.

The necessary settings for a server should be set provided using the course's "Other course settings" JSON object, so it is available to all problems in a course, and can be centrally modified for them all.
  - The code also supports providing the server configuration/authentication data in each problems, but doing so is highly discouraged.

## Installation

For installation instructions in an edX devstack on the "lilac" named release see: https://github.com/Technion-WeBWorK/xblock-webwork/blob/master/install-docs/setup-devstack-named-release-with-webwork-xblock.md . Those settings were tested on July 30, 2021 and were used to bring up a new test system.

Older instructions for installing in the "master" branch of devstack are in the directory https://github.com/Technion-WeBWorK/xblock-webwork/blob/master/install-docs/ but are not fully updated. In particular, they are missing instructions on enabling the "Other course settings" option and using it to configure the XBlock course-wide settings.

The XBlock has also been used with the Ginkgo release of edX:
  - Ginkgo is a Python 2.7 version of open-edX, and supporting it required quite a few changes to the code. The version of the code which works for Ginkgo is in a separate branch: `ginkgo-fixes`.
  - That branch/version does **not** respect the `graceperiod` setting (as we were unable to get a needed edx-platform dependency to work in  Ginkgo).
  - Ginkgo does not include the "Other course settings" feature which is needed for the XBlock to function. It must be added to edx-platform in a manner similar to what appears in https://github.com/Technion-WeBWorK/edx-platform/commit/311989429ef1daa4eb9421fa8db4190dd0ebf597 which is based on https://github.com/open-craft/edx-platform/pull/118.

**Warning:** The "master" branch of devstack also is making a transition from the "old" LMS system to new services, and that apparently may cause some problems with the instructions, which worked before those changes.

## Installation - changes needed in edx-platform + settings to enable the submission history features

The XBlock can only save the submission history and enable staff accounts to view that history if suitable small changes are made to edx-platform,
and a suitable setting is added to the LMS settings.

Changes needed to edx-platform:
  - https://github.com/edx-olive/edx-platform/pull/68/files (changes being used on a some Ginkgo systems)
  - or https://github.com/Technion-WeBWorK/edx-platform/commit/4ca75014531e0d21ecc17add3499aa6fa11771ec and https://github.com/Technion-WeBWorK/edx-platform/commit/57b75df2536afcccf7cc89efb1c19d3784f8a696
  - Note that there was a need to modify `lms/envs/aws.py` in order for the setting to take effect on an AWS deployment of Ginkgo.
  - It seems that the change made to `lms/envs/aws.py` for Ginkgo (on AWS) belongs in `lms/envs/production.py` for some later versions of edX.

For Ginkgo, the setting change is made in `lms.env.json` by adding a line:
```
HISTORY_SAVING_TYPES = [ "problem", "webwork" ]
```

For later versions of edX, which use `etc/lms.yml` the additional line to add is:
```
HISTORY_SAVING_TYPES: ['problem','webwork']
```



## Feature overview

### Course level configuration
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
  * The XBlock stores a dictionary of possible values, and retrieves the relevant one based on a problem setting (`psvn_key` which defaults to 1).
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
  * At present, this requires making 2 very small modifications to the core edx-platform code to make access to the relevant features available to a configurable list of XBlocks and not just to `problem`.
  * Without the additional configuration, only the most recent data for each XBlock instance is stored.
* The remote back-end WeBWorK systems are not sent personal identification information from the edX student data about the students.
  * Requests send only the necessary data to render/grade a problem to the back-end.
  * For grading of answers, this includes whatever data a student typed into the input boxes of a WeBWorK question.

Additional information on the design can be found in https://github.com/Technion-WeBWorK/xblock-webwork/blob/master/doc/Design.md

