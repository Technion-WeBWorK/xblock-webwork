WeBWorK-PG XBlock
=================
An edX XBlock that uses WeBWorK's PG as its backend.
LMS functionality usually handled by WeBWorK's webwork2 LMS code will be handled inside the XBlock.
A "thin" web service based on WeBWorK's XMLRPC code will provide the API with which the XBlock communicates.

Overview
========

Administration
--------------
* Select a problem, specified by path
* Setting related dates and enforcing them: deadlines, release, etc.
* Set grade weight (e.g. a unit with 3 problems, one 40 percent the other two 30)
* "Staff View" of problem (as a certain student) shows the student's customized version, all past submissions, scores, and feedback messages

Problem Setup
-------------
* Manage random seeds
* Verify release dates and deadlines, as well as per-student times
* Count and limit attempts
* "Show Answer" option
* __Load HTML from PG__ based on seed. 
* Display HTML, setting up MathJax and any custom CSS/JS

Problem Grading
---------------
* Serialize user response
* __Pass response to PG and receive score and feedback messages__
* Save submitted answers, scores, and feedback
* Show feedback / update problem HTML to user
