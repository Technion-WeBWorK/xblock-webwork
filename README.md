Technion Math XBlock
====================
An edX XBlock that uses WeBWorK's PG as its backend.

Overview
========

Administration
--------------
* Select a problem, specified by path
* Set grade weight (e.g. a unit with 3 problems, one 40 percent the other two 30)
* "Staff View" of problem (as certian student) shows all past attempts and scores

Problem Setup
-------------
* Manage random seeds
* Verify release dates and deadlines, as well as per-student times
* Limit attempts
* "Show Answer" option
* __Load and Display HTML from PG__ based on seed

Problem Grading
---------------
* Serialize user response
* __Pass response to PG and receive score__
* Save user attempt
* Save grade
* Show feedback to user