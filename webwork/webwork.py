"""
XBlock that calls WeBWorK's PG problem generation / grading functionality
using either
      the Standalone renderer
        from https://github.com/drdrew42/renderer
        which is designed for efficient use without a full "regular" WeBWorK server,
        and is essentially stateless so can be run behind a load balance with some shared
        storage for all instances for generated files.
    or the WeBWorK html2xml interface from webwork - version >= 2.16
        from https://github.com/openwebwork/webwork2/
        which requires running a full "regular" WeBWorK server,
        and is not likely to handle large loads well.
(c) 2021 Technion - Israel Institute of Technology
    This code was originally developed in the Technion.

    Effort was made to credit inclusions of snippets of code from other
    open source projects where such use was made.

    The initial framework of this file and several other files in the project
    were based on the samples files from the edX XBlock SDK (https://github.com/edx/xblock-sdk)
    which is under the Apache-2.0 License,  and the documentation in the
    Open edX XBlock Tutorial (https://edx.readthedocs.io/projects/xblock-tutorial/en/latest/index.html)
    which is licensed under a Creative Commons Attribution-ShareAlike 4.0 International License.


    The project is being released under an open source license, see the
    LICENSE file in the repository.

    Later contributions to the codebase by additional contributors will belong to
    those contributors, but by being merged into this project or forks of this
    project are automatically covered by the same license.
"""
import json
import random
import datetime
import requests # Ease the contact with webwork server via HTTP/1.1
import pkg_resources # Used here to return resource name as a string
import six
import pytz # python timezone
from pytz import utc
from xblock.core import XBlock
from django.utils.translation import ugettext_lazy as _
from xblock.fields import String, Scope, Integer, List, Dict, Float, Boolean, DateTime, UNIQUE_ID
from xmodule.fields import Date
from xblock.validation import ValidationMessage
from web_fragments.fragment import Fragment
from webob.response import Response # Uses WSGI format(Web Server Gateway Interface) over HTTP to contact webwork
from xblockutils.studio_editable import StudioEditableXBlockMixin
from xblock.scorable import ScorableXBlockMixin, Score
from xblock.completable import XBlockCompletionMode
from cms.djangoapps.models.settings.course_grading import CourseGradingModel
from enum import IntFlag, unique
from xmodule.util.duedate import get_extended_due_date

# The recommended manner to format datetime for display in Studio and LMS is to use:
from common.djangoapps.util.date_utils import get_default_time_display

# Next line needed only if we decide to use the submissions API
#from .sub_api import SubmittingXBlockMixin, sub_api

# Lines to allow logging to console.
# Copied from https://gitlab.edvsz.hs-osnabrueck.de/lhannigb/showblock/-/blob/master/showblock/showblock.py

#import logging
#DEBUGLVL = logging.INFO
#logger = logging.getLogger(__name__)
#logger.setLevel(DEBUGLVL)
#ch = logging.StreamHandler()
#ch.setLevel(DEBUGLVL)
#logger.addHandler(ch)

# End lines copied from https://gitlab.edvsz.hs-osnabrueck.de/lhannigb/showblock/-/blob/master/showblock/showblock.py

# When those lines are active, we can issue log messages using logger.info("Message")

# =========================================================================================

# Prepare the dictionaries which are used to set up and to sanitize request data

EARLY_FORM_CLEANUP = {
    # from html2xml:
    "courseID": "",
    "userID": "",
    "session_key": "",
    "courseName": "",
    "course_password": "",
    "forcePortNumber": "",
    "displayMode": "",
    "outputformat": "",
    "theme": "",
    "showAnswerNumbers": "",
    "showCheckAnswersButton": "",    # The XBlock will disable buttons when they should not be used.
    "showCorrectAnswersButton": "",  # We do not hide/remove them, but prevent processing a request
    "showPreviewButton": "",         # made if the button is reenabled or the relevant type of submission
    "showCheckAnswersButton" : "",   # is made and it is not allowed. (These are html2xml options.)
    "problemSource": "",
    "showFooter": "",
    "extra_header_text": "",
    "problem-result-score": "",
    "WWcheck": "", # used by html2xml for "check" as opposed to submit. We treat all as "submit" in the XBlock
                   # and decide on when to save a grade internally.
    "clientDebug": "",
    "lis_outcome_service_url": "",
    "oauth_consumer_key": "",
    "oauth_signature_method": "",
    "lis_result_sourcedid": "",
    # from Standalone:
    "problemSource": "",
    "problemSourceURL": "",
    "baseURL": "",
    "user": "",
    "effectiveUser": "",
    "format": "",
    "includeTags": "",
    "outputFormat": "",
    "permissionLevel": "",
    "showComments": ""
}

# Form values which should always be cleared (code sets what it needs)
HTML2XML_JUST_REMOVE = {
    "send_pg_flags": "1",
    "problemSeed": "",
    "psvn": "",
# Added now
    "courseID": "",
    "userID": "",
    "session_key": "",
    "courseName": "",
    "course_password": "",
    "forcePortNumber": "",
    "theme": "",
    "showAnswerNumbers": "",
    "showCheckAnswersButton": "",    # The XBlock will disable buttons when they should not be used.
    "showCorrectAnswersButton": "",  # We do not hide/remove them, but prevent processing a request
    "showPreviewButton": "",         # made if the button is reenabled or the relevant type of submission
    "showCheckAnswersButton" : "",   # is made and it is not allowed. (These are html2xml options.)
    "problemSource": "",
    "extra_header_text": "",
    "problem-result-score": "",
    "WWcheck": "", # used by html2xml for "check" as opposed to submit. We treat all as "submit" in the XBlock
               # and decide on when to save a grade internally.
    "clientDebug": "",
    "lis_outcome_service_url": "",
    "oauth_consumer_key": "",
    "oauth_signature_method": "",
    "lis_result_sourcedid": ""
}

HTML2XML_PARAMETERS = {
    "language": "en", # This is intended to request that WeBWorK generate messages in the requested language
                      # and is well supported by the html2xml interface, so long as the main project translation
                      # file has a translation for the relevant string.
    "displayMode": "MathJax",
    "outputformat": "simple",
    "showFooter": "0",
    "standalone_style": "1"
}

HTML2XML_REQUEST_PARAMETERS = dict(HTML2XML_PARAMETERS, **{
    "answersSubmitted": "0"
})

HTML2XML_RESPONSE_PARAMETERS_BASE = dict(HTML2XML_PARAMETERS, **{
    "showSummary" : "1",
    "answersSubmitted": "1"
})

HTML2XML_RESPONSE_PARAMETERS_CHECK = dict(HTML2XML_RESPONSE_PARAMETERS_BASE, **{
    "WWsubmit": "Check Answers"
})

HTML2XML_RESPONSE_PARAMETERS_PREVIEW = dict(HTML2XML_RESPONSE_PARAMETERS_BASE, **{
    "preview": "Preview My Answers"
})

HTML2XML_RESPONSE_PARAMETERS_SHOWCORRECT = dict(HTML2XML_RESPONSE_PARAMETERS_BASE, **{
    "WWcorrectAns": "Show Correct Answers"
})

# Form values which should always be cleared.
# Any form provided values may be due to hidden fields set by the WeBWorK renderer in use,
# and should never be trusted. We set those we need when building a request.
# List based on the API description from the README at
#    https://github.com/drdrew42/renderer/blob/master/README.md
# The JWT releated fields are not yet documented there, but as the XBlock acts as a
# man in the middle - any JWT fields would be handled only by the XBlock without any need
# to be trusted from the end-user submission.
#   JWT fields appear in the Standalone code in
#    https://github.com/drdrew42/renderer/blob/master/lib/RenderApp/Controller/Render.pm
#    https://github.com/drdrew42/renderer/blob/master/lib/RenderApp/Controller/RenderProblem.pm
# Anything which will be cleared by the other dictionaries need not be included in this one.
STANDALONE_JUST_REMOVE = {
    "problemSourceURL": "",
    "problemSource": "",
    "sourceFilePath": "",
    "problemSeed": "",
    "psvn": "",
    "formURL": "",
    "baseURL": "",
    "problemNumber": "",
    "numCorrect": "",
    "numIncorrect": "",
    "problemJWT": "",
    "sessionJWT": "",
    "answerJWT": "",
    "JWTanswerURL": "",
}

STANDALONE_PARAMETERS = {
    "format" : "json",
    "outputFormat": "simple",
    "displayMode": "MathJax",
    "permissionLevel": "0", # Student level permissions
    "processAnswers": "1", # Standalone enables this by default, but as we depend on it - set it on explicitly
    "showSummary": "1",
    "showComments": "0",
    "showHints": "0", # Default to off
    "showSolutions": "0", # Default to off
    "includeTags": "0",
    "language": "en", # This is intended to request that WeBWorK generate messages in the requested language and is not yet fully supported by the Standalone renderer
}

STANDALONE_REQUEST_PARAMETERS = dict(STANDALONE_PARAMETERS, **{
    "answersSubmitted": "0"
})

STANDALONE_RESPONSE_PARAMETERS_BASE = dict(STANDALONE_PARAMETERS, **{
    "showSummary" : "1",
    "answersSubmitted": "1"
})

STANDALONE_RESPONSE_PARAMETERS_CHECK = dict(STANDALONE_RESPONSE_PARAMETERS_BASE, **{
    "submitAnswers": "Check Answers"
})

STANDALONE_RESPONSE_PARAMETERS_PREVIEW = dict(STANDALONE_RESPONSE_PARAMETERS_BASE, **{
    "previewAnswers": "Preview My Answers"
})

STANDALONE_RESPONSE_PARAMETERS_SHOWCORRECT = dict(STANDALONE_RESPONSE_PARAMETERS_BASE, **{
    "showCorrectAnswers": "Show Correct Answers"
})

# =========================================================================================

# Fields from the answer hash data we want to save
ANSWER_FIELDS_TO_SAVE = [
  "ans_label",
  "ans_message",
  "ans_name",
  "cmp_class",
#  "correct_ans_latex_string",
  "correct_value",
  "error_message",
  "original_student_ans",
#  "preview_latex_string",
  "score",
  "student_formula",
  "student_value",
  "type"
]

# =========================================================================================

# Fields from Standalone "form_data" we want to save - shows what was processed
STANDALONE_FORM_SETTINGS_TO_SAVE = [
  'problemSeed',
  'psvn',
  'sourceFilePath',
  'numCorrect',
  'numIncorrect'
]

HTML2XML_FORM_SETTINGS_TO_SAVE = [
  'problemSeed',
  'psvn',
  'sourceFilePath',
  'problemUUID'
]

# =========================================================================================

class WeBWorKXBlockError(RuntimeError):
    pass

@unique # decorator to enforce different integer values for each period
class PPeriods(IntFlag):
    UnKnown = 0 
    NoDue = 1 # some problem are due-dateless
    PreDue = 2 # The problem due date is in the future
    PostDue = 3
    Locked =  4 # Problem locked for submissions/watch answers etc.
    UnLocked = 5
    PostDueLocked = PostDue * Locked 
    PostDueUnLocked = PostDue * UnLocked
        
class WWProblemPeriod:
    """ Neatly define getter and setter of problem periods """
    def __init__(self, period=PPeriods.UnKnown):
        self._period = period

    @property
    def period(self): #this is the period.getter
        return self._period

    @period.setter
    def period(self, value):
        if value.name not in set(item.name for item in PPeriods):
            raise ValueError("Undefined period")
        self._period = value

    @period.deleter
    def period(self):
        self._period = PPeriods.UnKnown

@XBlock.needs("user")
class WeBWorKXBlock(
    ScorableXBlockMixin, XBlock, StudioEditableXBlockMixin,
    #SubmittingXBlockMixin,  # Needed if using the the submissions API
    ):
    """
    XBlock that calls WeBWorK's PG problem generation / grading functionality
    """
    # Makes LMS icon appear as a problem
    icon_class = 'problem'
    category = 'ww-problem'

    @property
    def course(self):
        """ Return course by course id."""
        return self.runtime.modulestore.get_course(self.runtime.course_id)

    def final_max_attempts(self):
        if self.max_attempts > 0:
            return self.max_attempts + self.student_extra_attempts
        elif self.max_attempts == 0:
            # Do not modify
            return 0
        else:
            # Should not occur, but just in case:
            return 0

    def set_due_date(self):
        self.due = get_extended_due_date(self)

    @property
    def grace_timedelta(self): #plays both as getter and setter
        try:
            graceperiod = CourseGradingModel.fetch(self.course.id).grace_period
        except AttributeError:
            graceperiod = None

        if graceperiod is not None:
            self._grace_timedelta = datetime.timedelta(
                hours = graceperiod['hours'],
                minutes = graceperiod['minutes'],
                seconds = graceperiod['seconds']
                )
        else:
            self._grace_timedelta = datetime.timedelta(
                hours=0, minutes=0, seconds=0
                )

        return self._grace_timedelta

    def set_problem_period(self):
        Now = datetime.datetime.now(datetime.timezone.utc)
        self.set_due_date()
        DueDate = self.due
        GraceDuration = self.grace_timedelta
        LockDuration = datetime.timedelta(hours = self.post_deadline_lockdown)
        if DueDate is not None and GraceDuration is not None:
            self.lock_date_begin = DueDate + GraceDuration
            self.lock_date_end = self.lock_date_begin + LockDuration

            # The formatting in the next line should be locale dependent, so we use
            # get_default_time_display()
            self.formatted_lock_date_end = get_default_time_display(self.lock_date_end)

            if Now < self.lock_date_begin:
                self.problem_period = PPeriods.PreDue
            elif Now < self.lock_date_end:
                self.problem_period = PPeriods.PostDueLocked
            else:
                self.problem_period = PPeriods.PostDueUnLocked
        elif DueDate is None:
            self.problem_period = PPeriods.NoDue
            self.lock_date_end = None
            self.formatted_lock_date_end = None
        
    def clear_problem_period(self):
        del self._problem_period

    def period_button_settings( self ):
        # At present the code disables the buttons but does not hide them.
        my_return_dict = {
            'hideShowAnswers': False,
            'hidePreview': False,
            'hideSubmit': False
        }
        if self.problem_period is PPeriods.NoDue:
            if self.final_max_attempts() > 0 and self.student_attempts < self.final_max_attempts():
                # Did not submit enough attempts to be permitted to see answers
                my_return_dict.update( {
                    'hideShowAnswers': True,
                })
            elif self.final_max_attempts() == 0 and self.student_attempts < self.no_attempt_limit_required_attempts_before_show_answers:
                # Did not submit enough attempts to be permitted to see answers
                my_return_dict.update( {
                    'hideShowAnswers': True,
                })
        elif self.problem_period is PPeriods.PreDue:
            if self.final_max_attempts() > 0:
                if self.student_attempts >= self.final_max_attempts():
                    # Used all allowed pre-deadline submission. Disable all buttons.
                    my_return_dict.update( {
                        'hideShowAnswers': True,
                        'hidePreview': True,
                        'hideSubmit': True
                    })
                else:
                    # Only prevent use of Show Answers
                    my_return_dict.update( {
                        'hideShowAnswers': True,
                    })
            elif self.final_max_attempts() == 0 and self.student_attempts < self.no_attempt_limit_required_attempts_before_show_answers:
                # Only prevent use of Show Answers
                my_return_dict.update( {
                    'hideShowAnswers': True,
                })
            else:
                # should not occur - so disable all buttons
                my_return_dict.update( {
                    'hideShowAnswers': True,
                    'hidePreview': True,
                     'hideSubmit': True
                })
        elif self.problem_period is PPeriods.PostDueLocked:
            # Lock-down period - disable all buttons
            my_return_dict.update( {
                'hideShowAnswers': True,
                'hidePreview': True,
                'hideSubmit': True
            })
        if not self.allow_show_answers:
            # When a problem is configured to prevent any use of Show Answers - disable the button
            my_return_dict.update( {
                'hideShowAnswers': True,
            })
        return( my_return_dict )

    show_in_read_only_mode = True # Allows staff to view the problem in read only mode when masquerading as a user.
    # See https://github.com/edx/edx-platform/blob/master/lms/djangoapps/courseware/masquerade.py

    main_settings = None
    def reload_main_setting(self):
        self.main_settings = self.course.other_course_settings.get('webwork_settings', {})

    def get_default_server(self):
        if self.main_settings == None:
             self.reload_main_setting()
        return self.main_settings.get('course_defaults',{}).get('default_server')

    def get_psvn_shift(self):
        if self.main_settings == None:
             self.reload_main_setting()
        return int(self.main_settings.get('course_defaults',{}).get('psvn_shift',0))

    # Current server connection related settings.
    # Make it an XBlock field to try to make sure it remains fixed per XBlock instance,
    # and does not cross between instances. Without doing this, and trying it as a
    # "plain" variable in the class - errors occurred as the value would sometimes be
    # from the "wrong" XBlock instance, which led to loading errors.
    current_server_settings = Dict(
       display_name = _("Current server settings for this block"),
       scope = Scope.user_state, # Scope.settings did not work - cannot be set by LMS
       help= ("This is the current server settings for this block."),
    )

    def clear_current_server_settings(self):
        self.current_server_settings.clear()

    def set_current_server_settings(self):
        self.clear_current_server_settings()
        if self.settings_type == 1:
            # Use the course-wide settings for the relevant ww_server_id
            self.current_server_settings.update(self.main_settings.get('server_settings',{}).get(self.ww_server_id, {}))
            # Keep auth_data outside the current_server_settings field (which gets into the DB records of user_state/submissions).
            self.current_server_settings.pop("auth_data", None)
        elif self.settings_type == 2:
            # Use the locally set values from the specific XBlock instance
            self.current_server_settings.update({  # Need str() on the first 2 to force into a final string form, and not __proxy__
                "server_type":             str(self.ww_server_type),
                "server_api_url":          str(self.ww_server_api_url)
            }) # The auth_data is not provided in this dictionary
            if self.ww_server_type == "html2ml":
                self.current_server_settings.update({
                    "server_static_files_url": str(self.ww_server_static_files_url)
                })
        myST = self.current_server_settings.get("server_type","")

        #logger.info("At end of set_current_server_settings for {UID} and see server_type as {ST}".format(UID=self.unique_id, ST = myST ))

    # The auth_data should be retrieved for use when a request is being made and
    # is not included in the current_server_settings, so it does not get logged to
    # the database as part of the user_state of the XBlock.
    def get_current_auth_data(self):
        if self.settings_type == 1:
            # Use the course-wide settings for the relevant ww_server_id
            return self.main_settings.get('server_settings',{}).get(self.ww_server_id, {}).get('auth_data',{})
        elif self.settings_type == 2:
            # Use the locally set values from the specific XBlock instance
            return self.auth_data

    def set_ww_server_id_options(self):
        """
        Set the list of course-wide ww_server_id options to display, pulled from the
        other course settings data
        """
        options_to_offer = [ ]
        my_default_server = self.get_default_server()
        if my_default_server:
            options_to_offer.append(my_default_server)
        server_list = self.main_settings.get('server_settings',{}).keys()
        if server_list:
            for sid in server_list:
                if sid != my_default_server:
                    options_to_offer.append(sid)
        if not options_to_offer:
            options_to_offer.append("None available from course settings")
        self.ww_server_id_options = json.dumps(options_to_offer,skipkeys=True)

    # ----------- External, editable fields -----------
    editable_fields = (
        # Main problem settings
        'problem', 'max_allowed_score',
        'ww_language',
        'max_attempts', 'no_attempt_limit_required_attempts_before_show_answers',
        'weight', 'psvn_key',
        # Main settings
        'settings_type',
        # For ID based server setting from course settings
        'ww_server_id_options',
        'ww_server_id',
        # For manual server setting
        'ww_server_type', 'ww_server_api_url', 'ww_server_static_files_url', 'auth_data',
        # Less important settings
        'allow_show_answers', 'allow_ww_hints', 'allow_ww_solutions_with_correct_answers',
        'problem_banner_text', 'display_name',
        'webwork_request_timeout',
        'post_deadline_lockdown',
        'custom_parameters',
        'iframe_min_height', 'iframe_max_height', 'iframe_min_width'
        )

    settings_type = Integer(
       display_name = _("Settings type"),
       scope = Scope.settings,
       values=[
            {"display_name": "Provided by course via \"Other Course Settings\"", "value": 1},
            {"display_name": "Manual settings", "value": 2},
       ],
       default = 1,
       help=_("ID of server - should have a record in the Other course settings dictionary - see the documentation"),
    )

    ww_server_id_options = String(
       display_name = _("List of course wide server ID options"),
       scope = Scope.settings,
       help=_("Options of server IDs available in the course. This is a read only list!"),
    )

    ww_server_id = String(
       display_name = _("ID of server"),
       scope = Scope.settings,
       default = None,
       help=_("ID of server - enter an option from the list in ww_server_id_options."),
    )

    ww_server_type = String(
       display_name = _("Type of server (html2xml or standalone)"),
       scope = Scope.settings,
       values=[
            {"display_name": "standalone renderer", "value": "standalone"},
            {"display_name": "html2xml interface on a regular server", "value": "html2xml"},
       ],
       default = 'standalone',
       help=_("This is the type of webwork server rendering and grading the problems (html2xml or standalone)."),
    )

    ww_server_api_url = String(
       display_name = _("WeBWorK server address with API endpoint"),
       scope = Scope.settings,
       help=_("This is the full URL of the webwork server including the path to the html2xml or render-api endpoint."),
    )

    ww_server_static_files_url = String(
       display_name = _("WeBWorK server address with path for static files"),
       scope = Scope.settings,
       help=_("This is the URL of the path to static files on the webwork server. Needed for html2xml servers."),
    )

    auth_data = Dict(
       display_name = _("Authentication settings for the server"),
       scope = Scope.settings,
       help=_("This is the authentication data needed to interface with the server. Required fields depend on the server type."),
    )

    # This is a standard Field used in many XBlocks and the value set appears in the studio view
    # in the banner line where the edit button appears. I am not certain why the standard help
    # text refers to "the horizontal navigation at the top of the page."
    # Among many places it appears in Google Drive XBlock
    # https://github.com/edx-solutions/xblock-google-drive/blob/master/google_drive/google_calendar.py
    # which is licensed under AGPL-3.0 License
    # and in an image of the studio edit for that XBlock in the sample image in the page
    # at https://edx.readthedocs.io/projects/xblock-tutorial/en/latest/overview/examples.html
    # It also appears in
    # https://github.com/edx/edx-platform/blob/a6bae4d238fdc6a60c8ee9f1b80ca3512bb085eb/common/lib/xmodule/xmodule/capa_base.py
    # https://github.com/edx/edx-platform/blob/b6ea3f4e692909f71cf251edc4a946138533fef9/common/lib/xmodule/xmodule/capa_base.py
    # and the standard help message (before the i8n support seems to date back to
    # https://github.com/edx/edx-platform/commit/b6ea3f4e692909f71cf251edc4a946138533fef9)
    # https://github.com/edx/edx-platform/blob/831f907c799917ab5fff4661111f7a52f9863be5/common/lib/xmodule/xmodule/capa_module.py
    display_name = String(
       display_name = _("Display Name"),
       default = _("WeBWorK Problem"),
       scope = Scope.settings,
       help = _("Display name which appears in the control bar above the content in Studio view.") # Where else?
       #help=_("This name appears in the horizontal navigation at the top of the page."),
    )

    problem_banner_text = String(
       display_name = _("Problem Banner Text"),
       default = _("WeBWorK Problem"),
       scope = Scope.settings,
       help=_("This text appears as an H3 header above the problem."),
    )

    problem = String(
        display_name = _("Problem"),
        default = "Library/Dartmouth/setMTWCh2S4/problem_5.pg",
        scope = Scope.settings, # settings, so a course can modify, if needed, and not only Studio
        help = _("The path to load the problem from."),
    )

    ww_language = String(
        display_name = _("WeBWorK main language"),
        default = "en",
        scope = Scope.settings, # settings, so a course can modify, if needed, and not only Studio
        help = _("The name of the language translation file to use to select the language in which standard strings should be provided.")
    )

    max_allowed_score = Float(
        display_name = _("Maximum score"),
        default = 100,
        scope = Scope.settings,
        help = _("Maximum possible score for this problem (the webwork score between 0 and 1 will be multiplied by this factor)"),
    )

    max_attempts = Integer(
        display_name = _("Allowed (for credit) submissions"),
        default = 0,
        scope = Scope.settings,
        help = _("Maximum number of allowed submissions for credit (0 = unlimited)"),
    )

    no_attempt_limit_required_attempts_before_show_answers  = Integer(
        display_name = _("No attempts limit case - attempts before Show Answers is permitted"),
        default = 10,
        scope = Scope.settings,
        help = _("When an unlimited number of submissions are permitted, this sets the number of submissions required before Show Answers is permitted"),
    )

    post_deadline_lockdown = Integer(
        display_name = _("Post deadline lockdown period (in hours) when submission is not permitted"),
        default = 24,
        scope = Scope.settings,
        help = _("How long, in hours, should the problem be locked after the deadline (and the grace period) before submission is allowed again (0 = no delay)"),
    )

    allow_show_answers = Boolean(
        display_name = _("Show Answers"),
        default = True,
        scope = Scope.settings,
        help = _("Allow students to view correct answers (after deadline or if no deadline after all attempts used / or required number of attempts used when there is no attempt limit.)?"),
    )

    allow_ww_hints = Boolean(
        display_name = _("Allow WeBWorK to provide hints"),
        default = False,
        scope = Scope.settings,
        help = _("Allow WeBWorK to provide hints, if the problem has such, based on the number of prior attempts (as sent by the XBlock using the WW style counters) and the threshold set in the problems file."),
    )

    allow_ww_solutions_with_correct_answers = Boolean(
        display_name = _("Allow WeBWorK to provide solutions"),
        default = False,
        scope = Scope.settings,
        help = _("Allow WeBWorK to provide the solution when Check Answers is used, if the problem has such."),
    )

    custom_parameters = Dict(
        # Note: This is in place for future use, and is intended to be added to the request data.
        display_name=_("Custom Parameters"),
        help=_("Add the key/value pair for any custom parameters as a JSON object. Ex. {\"setting1\":71, \"setting2\": \"white\"}"),
        scope=Scope.settings
    )

    iframe_min_height = Integer(
        display_name=_("Iframe Minimum Height"),
        help=_(
            "Enter the desired minimum pixel height of the iframe which will contain the problem. (Minimum: 380)"
        ),
        default=380,
        scope=Scope.settings
    )

    iframe_max_height = Integer(
        display_name=_("Iframe Maximum Height"),
        help=_(
            "Enter the desired maximum pixel height of the iframe which will contain the problem. (Minimum: 380)"
        ),
        default=600,
        scope=Scope.settings
    )

    iframe_min_width = Integer(
        display_name=_("Iframe Minimum Width"),
        help=_(
            "Enter the desired minimum pixel width of the iframe which will contain the problem.  (Minimum: 500)"
        ),
        default=600,
        scope=Scope.settings
    )

    webwork_request_timeout = Float(
        display_name=_("Timeout [in seconds] for Webwork Server Requests"),
        help=_(
            "Maximal number of seconds to wait for response from the webwork server. <br/>" +
            "Don't change unless you are dealing with heavy duty problem."
        ),
        default=5.0,
        scope=Scope.settings
    )
    # ----------- Internal student fields -----------
    student_answer = Dict(
        default = None,
        scope = Scope.user_state,
        help = _("The student's answer."),
    )

    student_attempts = Integer(
        default = 0,
        scope = Scope.user_state,
        help = _("Number of times the student has submitted this problem. Simple counter."),
    )

    # FIXME - we do not yet have a mechanism to edit this
    student_extra_attempts = Integer(
        default = 0,
        scope = Scope.user_state,
        help = _("Additional number of attempts granted by the staff to this user."),
    )

    ww_numCorrect = Integer(
        default = 0,
        scope = Scope.user_state,
        help = _("Number of (fully) correct submissions processed in the past (while the problem is for credit). WeBWorK uses this field in internal calculations, and the Standalone renderer accepts a value to be used in procssing."),
    )

    ww_numIncorrect = Integer(
        default = 0,
        scope = Scope.user_state,
        help = _("Number of incorrect submissions processed in the past  (while the problem is for credit). WeBWorK uses this field in internal calculations, and the Standalone renderer accepts a value to be used in procssing."),
    )

    seed = Integer(
        default = 0,
        scope = Scope.user_state,
        help = _("Random seed for this student"),
    )

    submission_data_to_save = Dict(
        default = None,
        scope = Scope.user_state,
        help = _("Data to save as part of a submission."),
    )

    student_viewed_correct_answers = Boolean(
        display_name = _("Student viewed the correct answers"),
        default = False,
        scope = Scope.user_state,
        help = _("Did the student already view the correct answers?"),
    )

    # WeBWorK uses psvn to set a seed for groups of problems which need to have the same seed.
    # In order to allow flexibility - this XBlock wants to allow the psvn value used for
    # different groups of problems to vary. For example the same group of problems might be used
    # in a "homework" assignment and later in a "review" assignment, so a different psvn would be
    # desired for each. To this end, the collection of possible psvn values is a Dictionary with
    # Scope.preferences so it has values available to all webwork problems in a course. However,
    # Scope.preferences is really fixed for "content type" at the server level. As a result, we
    # also use a course-level setting which is used to shift the values in each course.
    # Each problem stored a psvn_name (Scope.user_state) which is used as they key to retrieve the
    # desired value from the dictionary.
    # The psvn for a specific problem is selected by pulling a value from the Diction


    psvn_options = Dict(
        default = {},
        scope = Scope.preferences,
        help = _("Dictionary of options for PSVN" + " "
             + "PSVN = problem set version number, used by WeBWorK to seed multi-part problems"),
    )

    psvn_key = Integer(
        default = 1,
        scope = Scope.settings,
        help = _("Key (an integer) for the PSVN to use for this problem. Selects from psvn_options." + " "
             + "PSVN = problem set version number, used by WeBWorK to seed multi-part problems"),
    )

    def get_psvn(self):
        """
        Get the psvn for this problem. Create it if necessary.
        """
        # Note for some reason, the key as stored/retreived would not remain an integer - so force it into a string always.
        # Otherwise the code did not work in LMS.
        if str(self.psvn_key) in self.psvn_options.keys() and isinstance(self.psvn_options.get(str(self.psvn_key)),int):
            return self.get_psvn_shift() + self.psvn_options.get(str(self.psvn_key))
        else:
            newpsvn = random.randint(1,500000)
            self.psvn_options.update({str(self.psvn_key):newpsvn})
            return self.get_psvn_shift() + newpsvn

    best_student_score = Float(
        default = 0.0,
        scope = Scope.user_state,
        help = _(
            """
            The student's (best) earned score on the problem - out of max_allowed_score.
            It only records the scores from attempts which count: before the deadline and
            passing the maximum number of allowed attempts.
            """
            ),
    )

    # Required by https://openedx.atlassian.net/wiki/spaces/AC/pages/161400730/Open+edX+Runtime+XBlock+API
    # Somewhat based on sample from
    # https://github.com/edx/edx-platform/blob/e66e43c5d2d452ec3a2c609fe26dbe7b4abba565/common/lib/xmodule/xmodule/capa_module.py
    weight = Float(
        display_name=_("Problem Weight"),
        help=_("Defines the number of points the problem is worth."),
        values={"min": 0.0, "step": 0.1},
        default = 1.0,
        scope=Scope.settings
    )

    # ----------- Internal runtime fields -----------

    unique_id = String(
        display_name = _("Runtime XBlock UNIQUE_ID"),
        default = UNIQUE_ID,
        scope = Scope.user_state,
        help = _("A runtime unique ID for this instance of this XBlock."),
    )

    # ----------- Fields and code copied from capa_module.py -----------
    # https://github.com/edx/edx-platform/blob/e66e43c5d2d452ec3a2c609fe26dbe7b4abba565/common/lib/xmodule/xmodule/capa_module.py
    done = Boolean(
        help=_("Whether the student has answered the problem and had a result saved"),
        scope=Scope.user_state,
        default=False
    )

    last_submission_time = Date(
        help=_("Last submission time"),
        scope=Scope.user_state
    )

    def set_last_submission_time(self):
        """
        Set the module's last submission time (when the problem was submitted)
        """
        self.last_submission_time = datetime.datetime.now(utc)
    # ----------- End of fields and code copied from capa_module.py -----------


    def validate_field_data(self, validation, data):
        _ = self.runtime.service(self, "i18n").ugettext
        if not isinstance(data.custom_parameters, dict):
            validation.add(ValidationMessage(ValidationMessage.ERROR, str(
                _("Custom Parameters must be a JSON object (dictionary).")
            )))
        if data.max_allowed_score < 0:
            validation.add(ValidationMessage(ValidationMessage.ERROR, str(
                _("Max allowed score must be non-negative.")
            )))
        if data.max_attempts < 0:
            validation.add(ValidationMessage(ValidationMessage.ERROR, str(
                _("Max allowed attempts must be non-negative. Zero is for no limit on the number of allowed attempts.")
            )))
        if data.no_attempt_limit_required_attempts_before_show_answers < 0:
            validation.add(ValidationMessage(ValidationMessage.ERROR, str(
                _("no_attempt_limit_required_attempts_before_show_answers must be non-negative.")
            )))
        if data.post_deadline_lockdown < 0:
            validation.add(ValidationMessage(ValidationMessage.ERROR, str(
                _("Post deadline lockdown (in hours) must be non-negative. Use 0 for no lock-down period.")
            )))
        if data.iframe_min_height < 380:
            validation.add(ValidationMessage(ValidationMessage.ERROR, str(
                _("iframe_min_height must be at least 380 pixels.")
            )))
        if data.iframe_max_height < 380:
            validation.add(ValidationMessage(ValidationMessage.ERROR, str(
                _("iframe_max_height must be at least 380 pixels.")
            )))
        if data.iframe_min_width < 500:
            validation.add(ValidationMessage(ValidationMessage.ERROR, str(
                _("iframe_min_width must be at least 500 pixels.")
            )))
        if data.webwork_request_timeout < 0.5:
            validation.add(ValidationMessage(ValidationMessage.ERROR, str(
                _("webwork_request_timeout must be at least 0.5 (seconds).")
            )))
        if data.weight < 0:
            validation.add(ValidationMessage(ValidationMessage.ERROR, str(
                _("weight must be non-negative. A weight of 0 essentially removes the score on this problem from the section grade calculation.")
            )))


    # ---------- Utils --------------

    def _problem_from_json(self,response_json):
        fixed_state = 'Error' # Fallback

        myST = self.current_server_settings.get("server_type","")

        #logger.info("In _problem_from_json for {UID} and see server_type as {ST}".format(UID=self.unique_id, ST = myST ))

        if response_json is None:
            return 'Error'
        try:
            raw_state = response_json['renderedHTML']
        except KeyError:
                return 'Error'
        if myST == 'html2xml':
            try:
                # html2xml uses most URLs as relative URLs and that does not work in the
                # iFrame. Fix the relative URLs for static files using the provided
                # value.
                fix_url = self.current_server_settings.get('server_static_files_url', None)
                if fix_url:
                    fixed_state = raw_state.replace("\"/webwork2_files", "\"" + fix_url )
                else:
                    fixed_state = raw_state
            except Exception:
                return 'Error'
        elif myST == 'standalone':
            fixed_state = raw_state
        else:
            fixed_state = 'Error'

        return fixed_state

    def _result_from_json_html2xml(self,response_json):

        # Revised to use "standalone_style=1" from
        # https://github.com/openwebwork/webwork2/pull/1426 which is still a draft PR
        # but that feature/code is in operations on webwork2.technion.ac.il.

        # Kept as a seperate method - subject to future changes

        kept_answers = response_json.get('flags',{}).get('KEPT_EXTRA_ANSWERS')
        answers_submitted = {key: value for key, value in response_json.get('form_data',{}).items() if key in kept_answers}
        self.student_answer = answers_submitted
        submission_settings = {key: value for key, value in response_json.get('form_data',{}).items() if key in HTML2XML_FORM_SETTINGS_TO_SAVE }
        save_answer_results_data = dict()
        raw_answer_results = response_json.get('answers',{})
        current_submission_ww_raw_score = float(response_json.get('problem_result',{}).get('score',0.0))
        for i in raw_answer_results.keys():
            to_save = { key: value for key, value in raw_answer_results.get(i,{}).items() if key in ANSWER_FIELDS_TO_SAVE }
            save_answer_results_data.update( { i : to_save } )
        to_store = {
            'provided_settings': {
                'problemSeed': str(self.seed),
                'psvn': str(self.get_psvn()),
                'sourceFilePath': str(self.problem)
            },
            'submission_settings_processed': submission_settings,
            'answers_processed': answers_submitted,
            'problem_result': response_json.get('problem_result',{}),
            'answer_results_data': save_answer_results_data,
            'num_attempts': self.student_attempts,
            'last_submission_time': str(self.last_submission_time),
            'current_submission_ww_raw_score': current_submission_ww_raw_score,
            'current_submission_scaled_score': current_submission_ww_raw_score * self.get_max_score()
        }
        return to_store


    def _result_from_json_standalone(self,response_json):
        # Maybe also:
        #   problem_state
        #   flags
        #   debug
        kept_answers = response_json.get('flags',{}).get('KEPT_EXTRA_ANSWERS')
        answers_submitted = {key: value for key, value in response_json.get('form_data',{}).items() if key in kept_answers}
        self.student_answer = answers_submitted
        submission_settings = {key: value for key, value in response_json.get('form_data',{}).items() if key in STANDALONE_FORM_SETTINGS_TO_SAVE }
        save_answer_results_data = dict()
        raw_answer_results = response_json.get('answers',{})
        current_submission_ww_raw_score = float(response_json.get('problem_result',{}).get('score',0.0))
        for i in raw_answer_results.keys():
            to_save = { key: value for key, value in raw_answer_results.get(i,{}).items() if key in ANSWER_FIELDS_TO_SAVE }
            save_answer_results_data.update( { i : to_save } )
        to_store = {
            'provided_settings': {
                'problemSeed': str(self.seed),
                'psvn': str(self.get_psvn()),
                'sourceFilePath': str(self.problem),
                "numCorrect":   str(self.ww_numCorrect),
                "numIncorrect": str(self.ww_numIncorrect)
            },
            'submission_settings_processed': submission_settings,
            'answers_processed': answers_submitted,
            'problem_result': response_json.get('problem_result',{}),
            'answer_results_data': save_answer_results_data,
            'num_attempts': self.student_attempts,
            'last_submission_time': str(self.last_submission_time),
            'current_submission_ww_raw_score': current_submission_ww_raw_score,
            'current_submission_scaled_score': current_submission_ww_raw_score * self.get_max_score()
        }
        return to_store

    def _result_from_json(self,response_json):
        if self.current_server_settings.get("server_type") == 'standalone':
            return self._result_from_json_standalone(response_json)
        if self.current_server_settings.get("server_type") == 'html2xml':
            return self._result_from_json_html2xml(response_json)
        return {} # Fallback

    @staticmethod
    def _sanitize_request_html2xml(request):
        for action in (
            HTML2XML_JUST_REMOVE,
            HTML2XML_REQUEST_PARAMETERS, HTML2XML_RESPONSE_PARAMETERS_SHOWCORRECT,
            HTML2XML_RESPONSE_PARAMETERS_PREVIEW, HTML2XML_RESPONSE_PARAMETERS_CHECK
            ):
            for key in action:
                request.pop(key, None)

    @staticmethod
    def _sanitize_request_standalone(request):
        for action in (
            STANDALONE_JUST_REMOVE,
            STANDALONE_REQUEST_PARAMETERS, STANDALONE_RESPONSE_PARAMETERS_SHOWCORRECT,
            STANDALONE_RESPONSE_PARAMETERS_PREVIEW, STANDALONE_RESPONSE_PARAMETERS_CHECK
            ):
            for key in action:
                request.pop(key, None)

    def _sanitize_request(self, request):
        if self.current_server_settings.get("server_type") == 'standalone':
            self._sanitize_request_standalone(request)
        elif self.current_server_settings.get("server_type") == 'html2xml':
            self._sanitize_request_html2xml(request)

    @staticmethod
    def _sanitize_early_form_data(request):
        for key in EARLY_FORM_CLEANUP:
            request.pop(key, None)

    def request_webwork_html2xml(self, params):
        # html2xml uses HTTP GET
        # See https://requests.readthedocs.io/en/master/user/quickstart/#make-a-request
        my_timeout = max(self.webwork_request_timeout,0.5)
        my_url = self.current_server_settings.get("server_api_url")
        my_auth_data = self.get_current_auth_data()
        my_res = None
        if my_url:
            try:
                my_res = requests.get(my_url, params=dict(
                        params,
                        courseID=my_auth_data.get('ww_course','error'),
                        userID=my_auth_data.get('ww_username','error'),
                        course_password=my_auth_data.get('ww_password','error'),
                        problemSeed=str(self.seed),
                        psvn=str(self.get_psvn()),
                        sourceFilePath=str(self.problem)
                    ),
                    timeout = my_timeout)
            except requests.exceptions.RequestException:
                # At present we are not trying to provide any information on what
                # sort of exception occurred.
                # Details on what can be issued appear in
                # https://docs.python-requests.org/en/latest/user/quickstart/#errors-and-exceptions
                my_res = None
        if my_res:
            return my_res.json()
        return None

    def request_webwork_standalone(self, params):
        # Standalone uses HTTP POST
        # See https://requests.readthedocs.io/en/master/user/quickstart/#make-a-request
        # and outputFormat set to "simple" and format set to "json".
        # Check by examining form parameters from Rederly UI on "render" call.
        my_timeout = max(self.webwork_request_timeout,0.5)
        my_url = self.current_server_settings.get("server_api_url")
        my_res = None
        if my_url:
            try:
                my_res = requests.post(my_url,
                    params=dict(params,
                        # standalone does not have course/user/password
                        problemSeed=str(self.seed),
                        psvn=str(self.get_psvn()),
                        sourceFilePath=str(self.problem)
                    ),
                    timeout = my_timeout)
            except requests.exceptions.RequestException:
                # At present we are not trying to provide any information on what
                # sort of exception occurred.
                # Details on what can be issued appear in
                # https://docs.python-requests.org/en/latest/user/quickstart/#errors-and-exceptions
                my_res = None
        if my_res:
            return my_res.json()
        return None
            
    def request_webwork(self, params):
        params.update( { "language": str(self.ww_language) } ) # Sets the desired translation language on the WW side

        if self.current_server_settings.get("server_type") == 'standalone':
            # Providing these parameters is only supported by the Standalone renderer at present
            params.update( {
                "numCorrect":   str(self.ww_numCorrect),
                "numIncorrect": str(self.ww_numIncorrect),
            } )
            if self.allow_ww_hints:
                params.update( { "showHints": "1" } )

            return self.request_webwork_standalone(params)

        if self.current_server_settings.get("server_type") == 'html2xml':
            return self.request_webwork_html2xml(params)

    # ----------- Grading related code -----------
    """
     The parent class ScorableXBlockMixin demands to define the methods
     has_submitted_answer(), get_score(), set_score(), calculate_score()
    """
    def has_submitted_answer(self):
        """
        For scoring, has the user already submitted an answer?
        """
        return self.student_attempts > 0

    def get_score(self):
        """
        For scoring, get the score.
        Return a raw score already persisted on the XBlock.
        Should not perform new calculations.
        """
        return Score(float(self.best_student_score), float(self.get_max_score()))

    def set_score(self, score):
        """
        Persist a score to the XBlock.
        The score is a named tuple with a raw_earned attribute and a
        raw_possible attribute, reflecting the raw earned score and the maximum
        raw score the student could have earned respectively.
        Arguments:
            score: Score(raw_earned=float, raw_possible=float)
        Returns:
            None
        This method also sets WeBWorKXBlock best_student_score field.
        best_student_score is a webwork-problem database field to be saved.
        """
        assert type(score) == Score
        self.best_student_score = float(score.raw_earned)

    def calculate_score(self):
        """
        Calculate a new raw score based on the state of the problem.
        This method should not modify the state of the XBlock.
        Returns:
            Score(raw_earned=float, raw_possible=float)
        Since we do not allow "rescoring" it returns the currently saved score
        """
        return Score(float(self.best_student_score), float(self.get_max_score()))

    def allows_rescore(self):
        # This XBlock does not allow rescoring of submitted answers.
        return False

    def get_max_score(self):
        """
        Get the max score
        """
        return self.max_allowed_score

    def resource_string(self, path):
        """
        Handy helper for getting resources from our kit.
        """
        data = pkg_resources.resource_string(__name__, path)
        return data.decode("utf8")

    # ----------- View -----------
    #def student_view(self, context=None, show_detailed_errors=True):
    def student_view(self, context=None, show_detailed_errors=False):
        """
        The primary view of the XBlock, shown to students
        when viewing courses. (iFramed: standalone or html2xml)
        """

        #logger.info("Starting student view for {UID}".format(UID=self.unique_id))

        # Get updated main course settings from main course "Other course settings"
        # Do this now, as we may need updated main connection settings
        self.reload_main_setting()
        # and then
        self.set_current_server_settings()

        if not self.seed:
            self.seed = random.randint(1,2**31-1)

        loading1 = "Your problem should load soon."
        loading2 = "Please wait."
        loadingHtml = "<html><body>{loading1}<br>{loading2}</body></html>"
        mysrcdoc = loadingHtml.format(loading1 = loading1, loading2 = loading2)

        debug_data = ""
        # This is sample code to generate some debug info to display under the problem
        #debug_data1 = self.current_server_settings.copy()
        #debug_data1.update({
        #    "settings_type": self.settings_type,
        #    "psvn_options_": self.psvn_options,
        #    "psvn":self.get_psvn(),
        #    "unique_id":str(self.unique_id),
        #})
        #try:
        #    debug_data = json.dumps(debug_data1,skipkeys=True)
        #except TypeError:
        #    debug_data = "error"

        iframe_id = 'rendered-problem-' + self.unique_id;
        iframe_resize_init = \
           '<script type="text/javascript">//<![CDATA[\n iFrameResize({ ' + \
           'checkOrigin: false, scrolling: true' + \
           ', minHeight: ' + str(self.iframe_min_height) + \
           ', maxHeight: ' + str(self.iframe_max_height) + \
           ', minWidth: '  + str(self.iframe_min_width)  + \
           '}, "#' + iframe_id + '")\n //]]></script>'

        html = self.resource_string("static/html/webwork_in_iframe.html")

        messageDiv_id = 'edx_message-' + self.unique_id;
        resultDiv_id  = 'edx_webwork_result-' + self.unique_id;

        js1  = self.resource_string("static/js/src/webwork_in_iframe.js")

        frag = Fragment( html.format(
            self = self,
            srcdoc = mysrcdoc,
            unique_id = self.unique_id,
            iFrameInit = iframe_resize_init,
            debug_data = debug_data
        ))

        frag.add_javascript_url('https://cdnjs.cloudflare.com/ajax/libs/iframe-resizer/4.2.9/iframeResizer.js')

        frag.add_css(self.resource_string("static/css/webwork.css"))
        frag.add_javascript( js1 )

        my_settings = {
          'unique_id' : self.unique_id,
          'rpID' : iframe_id,
          'messageDivID' : messageDiv_id,
          'resultDivID' : resultDiv_id
        }

        frag.initialize_js('WeBWorKXBlockIframed', my_settings)

        return frag

    def create_attempts_message(self):
        """
        Message to show about attempts status
        """
        if self.student_attempts > 0:
            attempts_message1 = "So far you have made {attempts_used} graded submissions to this problem.".format(
                attempts_used = str(self.student_attempts))
        else:
            attempts_message1 = "You have not yet made a graded submission to this problem."

        if self.final_max_attempts() > 0:
            attempts_message2 = "You are allowed at most {max_attempts} graded submissions to this problem.".format(
                max_attempts = str(self.final_max_attempts()))
        elif self.final_max_attempts() == 0:
            attempts_message2 = "You are allowed an unlimited number of graded submissions to this problem."
        return "<br>" + attempts_message1 + "<br>" + attempts_message2

    def create_current_score_message(self):
        """
        Message to show for current score (on load, show correct, show preview)
        """
        my_attempts_message = self.create_attempts_message()
        if self.student_attempts == 0:
            return my_attempts_message
        else:
            return "Your recorded (best) score is {old_best} points from {max_score} points.{attempts_message}".format(
                old_best = str(self.best_student_score), max_score = str(self.get_max_score()),
                attempts_message = my_attempts_message )


    def create_score_message(self, new_score, score_saved):
        """
        Message to show for score received now.
        """
        my_attempts_message = self.create_attempts_message()

        if score_saved:
            if new_score > self.best_student_score:
                return "You score from this submission is {new_score} from {max_score} points.".format(
                    new_score = str(new_score), max_score = str(self.get_max_score()) ) + "<br>" + \
                    "The new score will replace your prior best score of {old_best} points.{attempts_message}".format(
                        old_best = str(self.best_student_score), attempts_message = my_attempts_message )
            else:
                return "You score from this submission is {new_score} from {max_score} points.".format(
                    new_score = str(new_score), max_score = str(self.get_max_score()) ) + "<br>" + \
                    "That is less than your prior best score of {old_best} points, so the prior score remains your current recorded score for the problem.{attempts_message}".format(
                        old_best = str(self.best_student_score), attempts_message = my_attempts_message )
        else:
            return "<strong>" + "This is a submission which is not for credit." + "</strong><br>" + \
                "You score from this submission is {new_score} from {max_score} points.".format(
                    new_score = str(new_score), max_score = str(self.get_max_score()) ) + "<br>" + \
                "Your recorded best score on the problem is {old_best} points.".format(
                    new_score = str(new_score), max_score = str(self.get_max_score()), old_best = str(self.best_student_score) )

    # ----------- Handler for standalone -----------
    @XBlock.handler
    def submit_webwork_iframed(self, request_original, suffix=''):
        """
        Handle the student's submission.
        """
        response = {
            'success': False, # Set ONLY when the HTML in the iFrame should be replaced
            'message': "An unexpected error occurred!",
            'score': '',
            'scored': False
        }

        #logger.info("Starting submit_webwork_iframed for {UID}".format(UID=self.unique_id))

        # Make sure server settings are up to date
        self.reload_main_setting()
        self.set_current_server_settings()

        if self.current_server_settings.get("server_type") == 'standalone':
            # Settings for standalone calls
            REQUEST_PARAMETERS              = STANDALONE_REQUEST_PARAMETERS
            RESPONSE_PARAMETERS_CHECK       = STANDALONE_RESPONSE_PARAMETERS_CHECK
            RESPONSE_PARAMETERS_PREVIEW     = STANDALONE_RESPONSE_PARAMETERS_PREVIEW
            RESPONSE_PARAMETERS_SHOWCORRECT = STANDALONE_RESPONSE_PARAMETERS_SHOWCORRECT
        elif self.current_server_settings.get("server_type") == 'html2xml':
            # Settings for standalone calls
            REQUEST_PARAMETERS              = HTML2XML_REQUEST_PARAMETERS
            RESPONSE_PARAMETERS_CHECK       = HTML2XML_RESPONSE_PARAMETERS_CHECK
            RESPONSE_PARAMETERS_PREVIEW     = HTML2XML_RESPONSE_PARAMETERS_PREVIEW
            RESPONSE_PARAMETERS_SHOWCORRECT = HTML2XML_RESPONSE_PARAMETERS_SHOWCORRECT
        else:
            # This means that the server_type is not valid
            return Response(
                    text = json.dumps(response),
                    content_type =  "application/json",
                    status = 200,
                )

        try:
            # Copy the submitted form data from the request_original.json element
            # for modification and future use.
            request = request_original.json.copy()

            if self.current_server_settings.get("server_type") == 'html2xml':
                # Normalize 'submit_type' to use the values which the Standalone renderer uses
                if request['submit_type'] == "WWsubmit":
                    request['submit_type'] = "submitAnswers"
                elif request['submit_type'] == "preview":
                    request['submit_type'] = "previewAnswers"
                elif request['submit_type'] == "WWcorrectAns":
                    request['submit_type'] = "showCorrectAnswers"

            self._sanitize_request(request)

            self.set_problem_period()
            response.update( self.period_button_settings() )

            # TODO: Consider tranform into a match-case clause
            # after upgrading to python 3.10 and above

            # For most values of submit_type We do not modify self.student_answer,
            # so no state update should occur, which would trigger a save() of the XBlock,
            # and waste space in the database.

            # Handle first by submission type to reduce code duplication
            if request['submit_type'] == "initialLoad":
                request.pop('submit_type')
                request.update(REQUEST_PARAMETERS)
                webwork_response = self.request_webwork(request)
                response['renderedHTML'] = self._problem_from_json(webwork_response)
                if response['renderedHTML'] == 'Error':
                    response['success'] = False
                    response['message'] = "An error occurred. Please try again later, and if the problem occurs again, please report the issue to the support staff."
                else:
                    response['success'] = True
                    response['message'] = self.create_current_score_message()
            elif request['submit_type'] == "submitAnswers":
                request.pop('submit_type')
                # We will only modify self.student_answer only once we are certain that a submission is
                # allowed, to avoid an unnecessary state update which would waste space in the database.
                allow_submit = False
                save_grade = False # Most cases do not save a grade / submission data
                block_reason_message = None
                message_when_allowed = None
                # FIX
                if self.problem_period is PPeriods.PostDueLocked:
                    allow_submit = False
                    part1 = "Sorry, you cannot submit answers now."
                    if self.formatted_lock_date_end:
                        part2 = "<br>" + "Additional use of the problem is not permitted until {unlock_datetime}".format(unlock_datetime = self.formatted_lock_date_end)
                    else:
                        part2 = ""
                    response['message'] = part1 + part2 + "<br>" + self.create_current_score_message()
                elif self.problem_period is PPeriods.PostDueUnLocked:
                    allow_submit = True
                    save_grade = False    
                elif self.problem_period is PPeriods.PreDue:
                    if self.final_max_attempts() == 0:
                        allow_submit = True
                        save_grade = True
                    if self.final_max_attempts() > 0:
                        if self.student_attempts >= self.final_max_attempts():
                            allow_submit = False
                            part1 = "Sorry, can't submit now since your made the maximum number of allowed submissions for credit."
                            if self.formatted_lock_date_end:
                                part2 = "<br>" + "Additional use of the problem is not permitted until {unlock_datetime}".format(unlock_datetime = self.formatted_lock_date_end)
                            else:
                                part2 = ""
                            block_reason_message = part1 + part2
                        else:
                            allow_submit = True
                            save_grade = True
                elif self.problem_period is PPeriods.NoDue:
                    if self.final_max_attempts() > 0 and self.student_attempts >= self.final_max_attempts():
                        allow_submit = True
                        save_grade = False
                        message_when_allowed = "You have exceeded the maximum number ({max_attempts}) of graded attempts allowed on this problem.".format(
                            max_attempts = str(self.final_max_attempts()) ) + "<br>" + \
                            "This and additional submissions are allowed, but your recorded grade will not be changed." + "<br>" + \
                            "You may now also use the Show Correct Answers button."
                    else:
                        allow_submit = True
                        save_grade = True
                else:
                    # Bad value
                    response['success'] = False
                    response['message'] = "An error occurred"
                    raise WeBWorKXBlockError("An error determining while processing your request. (Period error)")

                if allow_submit:
                    # This is a real submission, save the original submission data as an initial value of the submission.
                    self.student_answer = request.copy()                  # Start from the current request data and then clean it up
                    self._sanitize_early_form_data( self.student_answer ) # a bit more, in case an error occurs and this is what is saved.
                                                                          # If we get to the next "else" then elf._result_from_json(webwork_response)
                                                                          # will replace this with properly selected data.

                    request.update(RESPONSE_PARAMETERS_CHECK)
                    webwork_response = self.request_webwork(request)

                    response['renderedHTML'] = self._problem_from_json(webwork_response)

                    if response['renderedHTML'] == 'Error':
                        # If we have an error, we will not increase the attempts counter.
                        response.update( self.period_button_settings() ) # The values may have changed since the last render
                        response['success'] = False
                        response['message'] = "An error occurred. Please try again later, and if the problem occurs again, please report the issue to the support staff."
                    else:
                        response['success'] = True
                        response['message'] = '' # currently no error

                        if save_grade:
                            # We only should count attempts made when the grade will be saved (ex. before the deadline)
                            # Grading apparently succeeded, so an attempt is counted.
                            self.student_attempts += 1

                        response.update( self.period_button_settings() ) # The values may change due to the new attempt

                        self.set_last_submission_time()

                        self.submission_data_to_save = self._result_from_json(webwork_response)

                        raw_ww_score = self.submission_data_to_save.get('current_submission_ww_raw_score',0.0)
                        scaled_ww_score = self.submission_data_to_save.get('current_submission_scaled_score',0.0)

                        response['score'] = self.create_score_message(scaled_ww_score, save_grade)
                        response['scored'] = True

                        if message_when_allowed:
                            response['message'] = message_when_allowed + "<br>" + self.create_score_message(scaled_ww_score, save_grade)
                        if save_grade:

                            # If we are allowed to save a grade, then the WW style attempt counters must be update
                            if raw_ww_score == 1.0:
                                self.ww_numCorrect += 1
                            else:
                                self.ww_numIncorrect += 1

                            # Records of all submissions will be created in edxapp_csmh.coursewarehistoryextended_studentmodulehistoryextended
                            # if the appropriate changes are made so the "webwork" xblock can save to their in addition to
                            # the default "problem" block.
                            # Records are also created/updated in edxapp.courseware_studentmodule but only the latest
                            # state is stored there.

                            # Issue with data in edxapp_csmh.coursewarehistoryextended_studentmodulehistoryextended
                            # 1. If self.save() called but self._publish_grade(myscore) is not called,
                            #    then one record is added, but it does not have the "new" grade set.
                            #    It uses whatever the prior grade was. That is essentially the same as what will
                            #    happen in neither is called, as a save() will be triggered when the method ends.
                            #    Calling self.save() after the self._publish_grade(myscore) would also behave that way.
                            # 2. If we skip self.save() and call self._publish_grade(myscore):
                            #    then 2 records are created. In the first (earlier) one - the "state" saved in the
                            #    table is the OLD data from before the current submission, but has the NEW score
                            #    so is NOT correct.
                            #    The second (later) record has the NEW data and the NEW score - so is correct.
                            #    This behavior seems very confusing - as it provides OLD submission data for the new time.
                            #    The second record is triggered when this method ends, which forces the updated data to
                            #    be saved to the database.
                            # 3. If we first call self.save() and then call self._publish_grade(myscore):
                            #    then 2 records are created. In the first (earlier) one - the "state" saved in the
                            #    table is the new data from the current submission, but has the OLD score
                            #    so is NOT correct.
                            #    The second (later) record has the NEW data and the NEW score - so is correct.
                            #    This behavior is still confusing but less so - as the first record does have the
                            #    correct "state" data, just not an updated grade value.

                            # This code should be done when the score should be saved (deadline/attempt limits)
                            # Use ScorableXBlockMixin required functions now:

                            if scaled_ww_score > self.best_student_score or not self.done:
                                self.done = True
                                self.best_student_score = scaled_ww_score
                                myscore = self.calculate_score()
                                #self.set_score(myscore) # would just set self.best_student_score again

                                # We need to force a save so the call to "_publish_grade" has the current state data.
                                self.save()

                                # An XBlock which sets a score needs to publish it.
                                # We only want scores to change if they are increasing (keep the largest score)
                                # so we would have liked to use "only_if_higher=True" below
                                self._publish_grade(myscore)
                                # but using
                                #    self._publish_grade(myscore, only_if_higher=True)
                                # gave errors apparently when there was no saved grade.
                                # So handle the decision on that in our code

                                # Submissions API was designed for ORA and more complex grading needs.
                                # When the sub_api is used mysql records are created in:
                                #     edxapp.submissions_score
                                #     edxapp.submissions_scoresummary
                                #     edxapp.submissions_submission
                                #     edxapp.submissions_studentitem
                                # It is NOT needed for the "Submission History" we are showing
                                # So it does not seem necessary for webwork.

                            #if sub_api:
                            #    submission = sub_api.create_submission(self.student_item_key, self.submission_data_to_save)
                            #    sub_api.set_score(submission["uuid"], myscore.raw_earned, myscore.raw_possible)

                            # Note: Records are created/updated in edxapp.courseware_studentmodule even without
                            #     sub_api.create_submission  AND without calls to self.runtime.publish()
                            # but that is just the store of the state of the XBlock "student" fields of Scope.user_state.
                            # It does not provide access to older data, so does not suffice.
                else:
                    # Give message
                    response['success'] = False
                    if block_reason_message:
                        response['message'] = block_reason_message + \
                            "<br>" + self.create_current_score_message()
            elif request['submit_type'] == "previewAnswers":
                request.pop('submit_type')
                # We do not modify self.student_answer, so no state update should occur,
                # which would trigger a save() of the XBlock, and waste space in the database.
                if self.problem_period is PPeriods.PostDueLocked or (
                        self.problem_period is PPeriods.PreDue and
                        self.final_max_attempts() > 0 and
                        self.student_attempts >= self.final_max_attempts() ):
                    part1 = "Sorry, you cannot preview answers now."
                    if self.formatted_lock_date_end:
                        part2 = "<br>" + "Additional use of the problem is not permitted until {unlock_datetime}".format(unlock_datetime = self.formatted_lock_date_end)
                    else:
                        part2 = ""
                    response['message'] = part1 + part2 + "<br>" + self.create_current_score_message()
                elif self.problem_period is PPeriods.NoDue or self.problem_period is PPeriods.PreDue or self.problem_period is PPeriods.PostDueUnLocked:
                    # If PPeriods.PreDue and attempt limit hit - handled above
                    request.update(RESPONSE_PARAMETERS_PREVIEW)
                    webwork_response = self.request_webwork(request)
                    response['renderedHTML'] = self._problem_from_json(webwork_response)
                    # On preview we do not need to save result of the call, so we do not want to make any change to the XBlock state.
                    if response['renderedHTML'] == 'Error':
                        response['success'] = False
                        response['message'] = "An error occurred. Please try again later, and if the problem occurs again, please report the issue to the support staff."
                    else:
                        response['success'] = True
                        response['message'] = "A preview of how the system understands your answers should be provided in the table above the question." + \
                            "<br>" + self.create_current_score_message()
                else:
                    # Bad value
                    response['success'] = False
                    response['message'] = "An error occurred"
                    raise WeBWorKXBlockError("An error determining whether processing of this request is allowed occurred.")
            elif request['submit_type'] == "showCorrectAnswers":
                request.pop('submit_type')
                allow_show_correct = False;
                # We usually do not modify self.student_answer, so no state update should occur,
                # which would trigger a save() of the XBlock, and waste space in the database.

                # Note: self.allow_show_answer is a main XBlock level setting
                #       allow_show_correct is the locally calculated value used to determine whether the action is permitted.
                if not self.allow_show_answers:
                    response['message'] = "Sorry, this problem is set to forbid access to the correct answers." + \
                        "<br>" + self.create_current_score_message()
                elif self.problem_period is PPeriods.PreDue or self.problem_period is PPeriods.PostDueLocked:
                    part1 = "Sorry, you cannot request to see the correct answers now."
                    if self.formatted_lock_date_end:
                        part2 = "<br>" + "Answers will become available at {unlock_datetime}".format(unlock_datetime = self.formatted_lock_date_end)
                    else:
                        part2 = ""
                    response['message'] = part1 + part2 + "<br>" + self.create_current_score_message()
                elif self.problem_period is PPeriods.PostDueUnLocked or self.problem_period is PPeriods.NoDue:
                    # Conditionally allowed. NoDue requires an additional condition to be tested
                    allow_show_correct = False;
                    if self.problem_period is PPeriods.PostDueUnLocked:
                        allow_show_correct = True
                    if self.problem_period is PPeriods.NoDue:
                        end_of_message = ""
                        required_to_show = 500 # fallback if max_attempts is negative
                        if self.final_max_attempts() == 0:
                            required_to_show = self.no_attempt_limit_required_attempts_before_show_answers
                        if self.final_max_attempts() > 0:
                            required_to_show = self.final_max_attempts()
                        if self.final_max_attempts() >= 0:
                            end_of_message = "<br>" + "Answers will become available after you make at {required_to_show} submissions.".format(required_to_show = required_to_show)
                        if self.student_attempts >= required_to_show:
                            allow_show_correct = True
                        else:
                            response['message'] = \
                                "Correct answers for this problem will become available after you submit at least {required_to_show} answers.".format(
                                    required_to_show = str(required_to_show) ) + " <br>" + \
                                "You have already submitted {attempts} answers to be graded.".format( attempts = str(self.student_attempts) ) + \
                                end_of_message + \
                                "<br>" + self.create_current_score_message()
                else:
                    # Bad value
                    response['success'] = False
                    response['message'] = "An error occurred"
                    raise WeBWorKXBlockError("An error determining whether processing of this request is allowed occurred.")
                if allow_show_correct:
                    request.update(RESPONSE_PARAMETERS_SHOWCORRECT)
                    if self.allow_ww_solutions_with_correct_answers:
                        request.update( { "showSolutions": "1" } )
                    webwork_response = self.request_webwork(request)
                    response['renderedHTML'] = self._problem_from_json(webwork_response)
                    if response['renderedHTML'] == 'Error':
                        response['success'] = False
                        response['message'] = "An error occurred. Please try again later, and if the problem occurs again, please report the issue to the support staff."
                    else:
                        # On show correct we do not need to save result of the call, or the student_answer data,
                        # so we clear the relevant fields, and on the first use only, just save a record showing that show answers was used.
                        # Use self.submission_data_to_save to show that a "show correct answers" action was taken, but ONLY the first time.
                        if not self.student_viewed_correct_answers:
                            self.set_last_submission_time()
                            self.student_answer.clear()
                            self.submission_data_to_save = {
                                "action" : "show correct answers - called for the first time when permitted",
                                'last_submission_time': str(self.last_submission_time)
                            }
                        self.student_viewed_correct_answers = True
                        response['success'] = True
                        response['message'] = "Correct answers should be provided in the table above the question." + \
                            "<br>" + self.create_current_score_message()
            else:
                response['success'] = False
                response['message'] = "An error occurred - invalid submission type"
                raise WeBWorKXBlockError("Unknown submit button used")

        except WeBWorKXBlockError as e:
            response['message'] = "fixme" # e.message

        return Response(
                text = json.dumps(response),
                content_type =  "application/json",
                status = 200,
            )


    def studio_view(self, context):
        """
        Get Studio View fragment
        """

        # Get updated main course settings from main course "Other course settings"
        # Do this now, before presenting the options, etc.
        self.reload_main_setting()

        # The set the list of server_id_options to be displayed
        self.set_ww_server_id_options()

        # When relevant - set a default value for ww_server_id
        if not self.ww_server_id and self.settings_type == 1:
            # No setting currently set, but in server_id mode - so set the default
            default_server = self.get_default_server()
            if default_server:
                self.ww_server_id = default_server


        # Initialize the choices
        fragment = super().studio_view(context)

        fragment.add_javascript(self.resource_string("static/js/xblock_studio_view.js"))

        fragment.initialize_js('WebWorkXBlockInitStudio')

        return fragment
        