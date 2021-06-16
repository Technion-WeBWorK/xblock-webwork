"""
XBlock that uses WeBWorK's PG grader.
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

# Next line needed only if we decide to use the submissions API
#from .sub_api import SubmittingXBlockMixin, sub_api

# Lines to allow logging to console.
# Taken from https://gitlab.edvsz.hs-osnabrueck.de/lhannigb/showblock/-/blob/master/showblock/showblock.py
#import logging
#DEBUGLVL = logging.INFO
#logger = logging.getLogger(__name__)
#logger.setLevel(DEBUGLVL)
#ch = logging.StreamHandler()
#ch.setLevel(DEBUGLVL)
#ogger.addHandler(ch)
# End lines taken from https://gitlab.edvsz.hs-osnabrueck.de/lhannigb/showblock/-/blob/master/showblock/showblock.py

WWSERVERAPILIST = {
    'TechnionFullWW':'https://webwork2.technion.ac.il/webwork2/html2xml',
    'LocalStandAloneWW':'http://WWStandAlone:3000/render-api',
}

WWSERVERFILESLIST = {
    'TechnionFullWW':'https://webwork2.technion.ac.il/webwork2_files',
    'LocalStandAloneWW':'error',
}

# SERVER = 'TechnionFullWW'
SERVER = 'LocalStandAloneWW'

# SERVERTYPE = 'html2xml'
SERVERTYPE = 'standalone'

HTML2XML_PARAMETERS = {
    "language": "en",
    "displayMode": "MathJax",
    "outputformat": "json",
}

# FIXME  - allow update of answersSubmitted according to user history
HTML2XML_REQUEST_PARAMETERS = dict(HTML2XML_PARAMETERS, **{
    "answersSubmitted": "0"
})

# FIXME  - Increase by 1 from current answersSubmitted
HTML2XML_RESPONSE_PARAMETERS_BASE = dict(HTML2XML_PARAMETERS, **{
    #"psvn" : "54321",  # Does not seem to belong here
    "showSummary" : "1",
    "answersSubmitted": "1"
})

HTML2XML_RESPONSE_PARAMETERS_CHECK = dict(HTML2XML_RESPONSE_PARAMETERS_BASE, **{
    "WWsubmit": "Check Answers"
})

HTML2XML_RESPONSE_PARAMETERS_PREVIEW = dict(HTML2XML_RESPONSE_PARAMETERS_BASE, **{
    "preview": "Preview My Answers"
})

HTML2XML_RESPONSE_PARAMETERS_CORRECT = dict(HTML2XML_RESPONSE_PARAMETERS_BASE, **{
    "WWcorrectAns": "Show Correct Answers"
})

STANDALONE_PARAMETERS = {
    "language": "en",
    "displayMode": "MathJax",
    "format" : "json",
    "outputFormat": "simple",
    "showSummary": "1",
    "permissionLevel": "0"
}

# FIXME  - allow update of answersSubmitted according to user history
STANDALONE_REQUEST_PARAMETERS = dict(STANDALONE_PARAMETERS, **{
    "answersSubmitted": "0"
})

# FIXME  - Increase by 1 from current answersSubmitted
STANDALONE_RESPONSE_PARAMETERS_BASE = dict(STANDALONE_PARAMETERS, **{
    #"psvn" : "54321",  # Does not seem to belong here
    "showSummary" : "1",
    "answersSubmitted": "1"
})

STANDALONE_RESPONSE_PARAMETERS_CHECK = dict(STANDALONE_RESPONSE_PARAMETERS_BASE, **{
    "WWsubmit": "Check Answers"
})

STANDALONE_RESPONSE_PARAMETERS_PREVIEW = dict(STANDALONE_RESPONSE_PARAMETERS_BASE, **{
    "preview": "Preview My Answers"
})

STANDALONE_RESPONSE_PARAMETERS_CORRECT = dict(STANDALONE_RESPONSE_PARAMETERS_BASE, **{
    "WWcorrectAns": "Show Correct Answers"
})

# Fields from the answer hash data we want to save
ANSWER_FIELDS_TO_SAVE = [
  "ans_label",
  "ans_message",
  "ans_name",
  "cmp_class",
  "correct_ans_latex_string",
  "correct_value",
  "error_message",
  "original_student_ans",
  "preview_latex_string",
  "score",
  "student_formula",
  "student_value",
  "type"
]

# Fields from Standalone "form_data" we want to save - shows what was processed
STANDALONE_FORM_SETTINGS_TO_SAVE = [
  'problemSeed',
  'psvn',
  'sourceFilePath'
]

class WeBWorKXBlockError(RuntimeError):
    pass

@unique # decorator to enforce different integer values for each period
class PPeriods(IntFlag):
    UnKnown = 0 
    NoDue = 1 # some problem are due-dateless
    PreDue = 2 # The problem due date is in the future
    PostDue = 3
    Locked =  4 # Problem locked for submissions/watch answers etc'
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

# The code below is NOT being used. If it is needed - it should be in a different file.
# FIXME - this should be kept in a different file, clearly keeping the code from that
# project separate from that of this project.
class StudentViewUserStateMixin:
    """
    This class has been copy-pasted from the problem-builder xblock file mixins.py
    https://github.com/open-craft/problem-builder/blob/master/problem_builder/mixins.py
    which is licensed under the GNU AFFERO GENERAL PUBLIC LICENSE version 3
    https://github.com/open-craft/problem-builder/blob/master/LICENSE

    This code provides student_view_user_state view.

    To prevent unnecessary overloading of the build_user_state_data method,
    you may specify `USER_STATE_FIELDS` to customize build_user_state_data
    and student_view_user_state output.
    """
    NESTED_BLOCKS_KEY = "components"
    INCLUDE_SCOPES = (Scope.user_state, Scope.user_info, Scope.preferences)
    USER_STATE_FIELDS = []

    def transforms(self):
        """
        Return a dict where keys are fields to transform, and values are
        transform functions that accept a value to to transform as the
        only argument.
        """
        return {}

    def build_user_state_data(self, context=None):
        """
        Returns a dictionary of the student data of this XBlock,
        retrievable from the student_view_user_state XBlock handler.
        """

        result = {}
        transforms = self.transforms()
        for _, field in six.iteritems(self.fields):
            # Only insert fields if their scopes and field names match
            if field.scope in self.INCLUDE_SCOPES and field.name in self.USER_STATE_FIELDS:
                transformer = transforms.get(field.name, lambda value: value)
                result[field.name] = transformer(field.read_from(self))

        if getattr(self, "has_children", False):
            components = {}
            for child_id in self.children:
                child = self.runtime.get_block(child_id)
                if hasattr(child, 'build_user_state_data'):
                    components[str(child_id)] = child.build_user_state_data(context)

            result[self.NESTED_BLOCKS_KEY] = components

        return result

    @XBlock.handler
    def student_view_user_state(self, context=None, suffix=''):
        """
        Returns a JSON representation of the student data of this XBlock.
        """
        result = self.build_user_state_data(context)
        json_result = json.dumps(result, cls=DateTimeEncoder)

        return webob.response.Response(
            body=json_result.encode('utf-8'),
            content_type='application/json'
        )

@XBlock.needs("user")
class WeBWorKXBlock(
    ScorableXBlockMixin, XBlock, StudioEditableXBlockMixin,
    #SubmittingXBlockMixin,  # Needed if using the the submissions API
#    StudentViewUserStateMixin # apparently not needed - grades/state saving without it
    ):
    """
    XBlock that uses WeBWorK's PG grader.
    """
    # Makes LMS icon appear as a problem
    icon_class = 'problem'
    category = 'ww-problem'

    @property
    def course(self):
        """ Return course by course id."""
        return self.runtime.modulestore.get_course(self.runtime.course_id)

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
            if Now < self.lock_date_begin:
                self.problem_period = PPeriods.PreDue
            elif Now < self.lock_date_end:
                self.problem_period = PPeriods.PostDueLocked
            else:
                self.problem_period = PPeriods.PostDueUnLocked
        elif DueDate is None:
            self.problem_period = PPeriods.NoDue
        
    def clear_problem_period(self):
        del self._problem_period

    show_in_read_only_mode = True # Allows staff to view the problem in read only mode when masquerading as a user.
    # See https://github.com/edx/edx-platform/blob/master/lms/djangoapps/courseware/masquerade.py


# FIXME
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

    # Current server connection related settings
    current_server_settings = {}

    def clear_current_server_settings(self):
        self.current_server_settings.clear()

    def set_current_server_settings(self):
        self.clear_current_server_settings()
        if self.settings_type == 1:
            # Use the course-wide settings for the relevant ww_server_id
            self.current_server_settings.update(self.main_settings.get('server_settings',{}).get(self.ww_server_id, {}))
            self.current_server_settings.update({"server_static_files_url":None}) # Not used by standalone
        elif self.settings_type == 2:
            # Use the locally set values from the specific XBlock instance
            self.current_server_settings.update({  # Need str() on the first 2 to force into a final string form, and not __proxy__
                "server_type":             str(self.ww_server_type),
                "server_api_url":          str(self.ww_server_api_url),
                "auth_data":               self.auth_data, # But no str() here - as it is a Dict
            })
            if self.ww_server_type == "html2ml":
                self.current_server_settings.update({
                    "server_static_files_url": str(self.ww_server_static_files_url)
                })

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
        # Main settings
        'settings_type',
        # For ID based server setting from course settings
        'ww_server_id_options',
        'ww_server_id',
        # For manual server setting
        'ww_server_type', 'ww_server_api_url', 'ww_server_static_files_url', 'auth_data',
        # Main problem settings
        'problem', 'max_allowed_score', 'max_attempts', 'weight', 'psvn_key',
        # Less important settings
        'display_name',
        'show_answers',
        'display_name', 'webwork_request_timeout',
        'post_deadline_lockdown', # FIXME - probably being replaced
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
       default = _(SERVERTYPE),
       help=_("This is the type of webwork server rendering and grading the problems (html2xml or standalone)."),
    )

    ww_server_api_url = String(
       display_name = _("WeBWorK server address with API endpoint"),
       # FIXME - this should depend on a main course setting
       default = _(WWSERVERAPILIST[SERVER]),
       scope = Scope.settings,
       help=_("This is the full URL of the webwork server including the path to the html2xml or render-api endpoint."),
    )

    ww_server_static_files_url = String(
       display_name = _("WeBWorK server address with path for static files"),
       # FIXME - this should depend on a main course setting
       default = _(WWSERVERFILESLIST[SERVER]),
       scope = Scope.settings,
       help=_("This is the URL of the path to static files on the webwork server."),
    )

    auth_data = Dict(
       display_name = _("Authentication settings for the server"),
       scope = Scope.settings,
       help=_("This is the authentication data needed to interface with the server. Required fields depend on the servert type."),
    )

    display_name = String(
       display_name = _("Display Name"),
       default = _("WeBWorK Problem"),
       scope = Scope.settings,
       help=_("This name appears in the horizontal navigation at the top of the page."),
    )

    problem = String(
        display_name = _("Problem"),
        # default = "Technion/LinAlg/Matrices/en/SplitAsUpperLower.pg",
        default = "Library/Dartmouth/setMTWCh2S4/problem_5.pg",
        # Next line is for when working with full local docker webwork
        # default = "SplitAsUpperLower.pg",
        # default = "part01a.pg",
        # Next line is for when working with local docker StandAlone webwork
        # default = "Library/SUNYSB/functionComposition.pg",
        scope = Scope.settings, # settings, so a course can modify, if needed
        help = _("The path to load the problem from."),
    )

    max_allowed_score = Float(
        display_name = _("Maximum score"),
        default = 100,
        scope = Scope.settings,
        help = _("Max possible score attainable"),
    )

    max_attempts = Integer(
        display_name = _("Allowed Submissions"),
        default = 0,
        scope = Scope.settings,
        help = _("Max number of allowed submissions (0 = unlimited)"),
    )

    # FIXME - probably being replaced
    post_deadline_lockdown = Integer(
        display_name = _("Post deadline lockdown period (in hours) when submission is not permitted"),
        default = 24,
        scope = Scope.settings,
        help = _("How long, in hours, should the problem be locked after the deadline (except during the grace period) before submission is allowed again (0 = no delay)"),
    )

    show_answers = Boolean(
        display_name = _("Show Answers"),
        default = False,
        scope = Scope.settings,
        help = _("Allow students to view correct answers?"),
    )

    custom_parameters = List(
        # FIXME - for future use
        display_name=_("Custom Parameters"),
        help=_("Add the key/value pair for any custom parameters. Ex. [\"setting1=71\", \"setting2=white\"]"),
        scope=Scope.settings
    )

    iframe_min_height = Integer(
        display_name=_("Iframe Minimum Height"),
        help=_(
            "Enter the desired minimum pixel height of the iframe which will contain the problem. "
        ),
        default=50,
        scope=Scope.settings
    )

    iframe_max_height = Integer(
        display_name=_("Iframe Maximum Height"),
        help=_(
            "Enter the desired maximum pixel height of the iframe which will contain the problem. "
        ),
        default=500,
        scope=Scope.settings
    )

    iframe_min_width = Integer(
        display_name=_("Iframe Minimum Width"),
        help=_(
            "Enter the desired minimum pixel width of the iframe which will contain the problem. "
        ),
        default=500,
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
        help = _("Number of times student has submitted problem"),
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
        if not isinstance(data.custom_parameters, list):
            _ = self.runtime.service(self, "i18n").ugettext
            validation.add(ValidationMessage(ValidationMessage.ERROR, str(
                _("Custom Parameters must be a list")
            )))

    # ---------- Utils --------------

    def _problem_from_json(self,response_json):

        # Rederly standalone - need:
        #     everything between <body> and </body>
        # and then the JS loads
        #     between <!-- JS Loads --> and BEFORE <title>
        fixed_state = 'Error' # Fallback

        if response_json is None:
            return 'Error'
        # Replace source address where needed
        if self.current_server_settings.get("server_type","") == 'html2xml':
            raw_state = \
                response_json['body_part100'] + response_json['body_part300'] + \
                response_json['body_part500'] + response_json['body_part530'] + \
                response_json['body_part550'] + response_json['body_part590'] + \
                response_json['body_part700'] + response_json['body_part999'][:-16]
                # Left out
                # + \
                #response_json["head_part200"]
            # Attempt to fix relative URLs for static files
            fix_url = self.current_server_settings.get('server_static_files_url')
            if fix_url:
                fixed_state = raw_state.replace(
                     "\"/webwork2_files", "\"" + fix_url )
            else:
                fixed_state = raw_state
        elif self.current_server_settings.get("server_type","") == 'standalone':
            # raw_state = str(response_json.content)
            # fixed_state = raw_state.replace(
            #     '/webwork2_files', 'http://WWStandAlone:3000/webwork2_files')
            fixed_state = response_json['renderedHTML']
        else:
            fixed_state = 'Error'

        return fixed_state

    def _result_from_json_html2xml_split_json(self,response_json):
        if response_json is None:
            return "Error"
        return response_json['body_part300']

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

    @staticmethod
    def _sanitize_request_html2xml(request):
        for action in (
            HTML2XML_REQUEST_PARAMETERS, HTML2XML_RESPONSE_PARAMETERS_CORRECT,
            HTML2XML_RESPONSE_PARAMETERS_PREVIEW, HTML2XML_RESPONSE_PARAMETERS_CHECK
            ):
            for key in action:
                request.pop(key, None)

    @staticmethod
    def _sanitize_request_standalone(request):
        for action in (
            STANDALONE_REQUEST_PARAMETERS, STANDALONE_RESPONSE_PARAMETERS_CORRECT,
            STANDALONE_RESPONSE_PARAMETERS_PREVIEW, STANDALONE_RESPONSE_PARAMETERS_CHECK
            ):
            for key in action:
                request.pop(key, None)

    def request_webwork_html2xml_split_json(self, params):
        # html2xml uses HTTP GET
        # See https://requests.readthedocs.io/en/master/user/quickstart/#make-a-request

        # Get updated main course settings from main course "Other course settings"
        # Do this now, as we may need updated main connection settings
        self.reload_main_setting()
        # and then
        self.set_current_server_settings()
        my_url = self.current_server_settings.get("server_api_url")
        my_auth_data = self.current_server_settings.get("auth_data",{})
        if my_url:
            my_res = requests.get(my_url, params=dict(
                    params,
                    courseID=my_auth_data.get('ww_course','error'),
                    userID=my_auth_data.get('ww_username','error'),
                    course_password=my_auth_data.get('ww_password','error'),
                    problemSeed=str(self.seed),
                    psvn=str(self.get_psvn()),
                    sourceFilePath=str(self.problem)
                ))
        if my_res:
            return my_res.json()
        return None

    def request_webwork_standalone(self, params):
        # Standalone uses HTTP POST
        # See https://requests.readthedocs.io/en/master/user/quickstart/#make-a-request
        # and outputFormat set to "simple" and format set to "json".
        # Check by examining form parameters from Rederly UI on "render" call.

        # Get updated main course settings from main course "Other course settings"
        # Do this now, as we may need updated main connection settings
        my_timeout = max(self.webwork_request_timeout,0.5)
        self.reload_main_setting()
        # and then
        self.set_current_server_settings()

        my_url = self.current_server_settings.get("server_api_url")
        if my_url:
            my_res = requests.post(my_url,
                params=dict(params,
                    # standalone does not have course/user/password
                    problemSeed=str(self.seed),
                    psvn=str(self.get_psvn()),
                    sourceFilePath=str(self.problem)
                ),
                timeout = my_timeout)
            if my_res:
                return my_res.json()
            return None
            

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
        """
        return Score(float(self.best_student_score), float(self.get_max_score()))

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

    def set_gracperiod(self):
        try:
            self.graceperiod = CourseGradingModel.fetch(self.course.id).grace_period
        except AttributeError:
            self.graceperiod = None

    # ----------- View -----------
    def student_view(self, context=None, show_detailed_errors=False):
        """
        The primary view of the XBlock, shown to students
        when viewing courses.
        """

        # Get updated main course settings from main course "Other course settings"
        # Do this now, as we may need updated main connection settings
        self.reload_main_setting()
        # and then
        self.set_current_server_settings()

        if self.current_server_settings.get("server_type") == 'html2xml':
            return self.student_view_html2xml_no_iframe(self)
        if self.current_server_settings.get("server_type") == 'standalone':
            return self.student_view_standalone(self)
        return self.student_view_error(self)

    # ----------- View for html2xml -----------

    #FIXME
    #def student_view_html2xml_no_iframe(self, context=None, show_detailed_errors=False):
    def student_view_html2xml_no_iframe(self, context=None, show_detailed_errors=True):
        """
        The primary view of the XBlock, shown to students
        when viewing courses. For html2xml interface use
        """
        if not self.seed:
            self.seed = random.randint(1,2**31-1)


        if self.max_attempts > 0 and self.student_attempts >= self.max_attempts:
            disabled = True

        form = self._problem_from_json(self.request_webwork_html2xml_split_json(HTML2XML_REQUEST_PARAMETERS))

        # hide the show answers button
        if not self.show_answers:
            form += "<style> input[name='WWcorrectAns']{display: none !important;}</style>"

        html = self.resource_string("static/html/webwork_html2xml_no_iframe.html")
        frag = Fragment(html.format(self=self,form=form))
        frag.add_css(self.resource_string("static/css/webwork.css"))
        frag.add_javascript(self.resource_string("static/js/src/webwork_html2xml_no_iframe.js"))
        frag.initialize_js('WeBWorKXBlockHtml2xmlNoIframe')
        return frag

    # ----------- View for standalone -----------

    # FIXME
    #def student_view_standalone(self, context=None, show_detailed_errors=False):
    def student_view_standalone(self, context=None, show_detailed_errors=True):
        """
        The primary view of the XBlock, shown to students
        when viewing courses. For standalone renderer use
        """
        #problem = self.store.get_item(self.problem.location)
        if not self.seed:
            self.seed = random.randint(1,2**31-1)

        if self.max_attempts > 0 and self.student_attempts >= self.max_attempts:
            disabled = True

        # FIXME hide the show answers button when necessary
        # FIXME - the standalone renderer should do this or JS code

        mysrcdoc = self._problem_from_json(self.request_webwork_standalone(STANDALONE_REQUEST_PARAMETERS)
           ).replace( "&", "&amp;"      # srcdoc needs "&" encoded
           ).replace( "\"", "&quot;" )  # srcdoc needs double quotes encoded. Must do second.
           #.replace( "<br/>", "" )

        test123 = self.current_server_settings
        test123.update( {"psvn_options_": self.psvn_options })
        test123.update({"psvn":self.get_psvn()})
        test123.update({"unique_id":str(self.unique_id)})
        my_st = "error reading server type  from self.current_server_settings"
        try:
            test123a = json.dumps(test123,skipkeys=True)
        except TypeError:
            test123a = "could not provide self.current_server_settings"
        try:
            my_st = self.current_server_settings.get("server_type","")
        except:
            my_st = "hit here"
        tmp1 = "temp value"
        if  my_st == 'standalone':
            tmp1 = "reports == standalone"
        else:
            tmp1 = "reports != standalone"
        test123a = test123a + "   " + my_st + tmp1

        iframe_id = 'rendered-problem-' + self.unique_id;
        iframe_resize_init = \
           '<script type="text/javascript">//<![CDATA[\n iFrameResize({ ' + \
           'checkOrigin: false, scrolling: true' + \
           ', minHeight: ' + str(self.iframe_min_height) + \
           ', maxHeight: ' + str(self.iframe_max_height) + \
           ', minWidth: '  + str(self.iframe_min_width)  + \
           '}, "#' + iframe_id + '")\n //]]></script>'

        # FIXME hide the show answers button
        # FIXME - the standalone renderer should do this

        html = self.resource_string("static/html/webwork_standalone.html")

        messageDiv_id = 'edx_message-' + self.unique_id;
        resultDiv_id  = 'edx_webwork_result-' + self.unique_id;

        js1  = self.resource_string("static/js/src/webwork_standalone.js")

        frag = Fragment(html.format(self=self,srcdoc=mysrcdoc,unique_id=self.unique_id,iFrameInit=iframe_resize_init,test123a=test123a))

        frag.add_javascript_url('https://cdnjs.cloudflare.com/ajax/libs/iframe-resizer/4.2.9/iframeResizer.js')

        frag.add_css(self.resource_string("static/css/webwork.css"))
        frag.add_javascript( js1 )

        frag.initialize_js('WeBWorKXBlockStandalone', {
          'unique_id' : self.unique_id,
          'rpID' : iframe_id,
          'messageDivID' : messageDiv_id,
          'resultDivID' : resultDiv_id
        })

        return frag


    # ----------- View for error -----------

    def student_view_error(self, context=None, show_detailed_errors=False):
        """
        The primary view of the XBlock, shown to students
        when viewing courses. When error hit
        """

        form = ""

        html = self.resource_string("static/html/webwork_html2xml_no_iframe.html")
        frag = Fragment(html.format(self=self,form=form))
        frag.add_css(self.resource_string("static/css/webwork.css"))
        return frag

    def create_score_message(self, new_score):
        """
        Message to show for score received now.
        Should indicate whether saved or now.
        """
        # FIXME
        if ( new_score > self.best_student_score ):
            return 'You score from this submission is ' + \
                str(new_score) + ' from ' + str(self.get_max_score()) + \
                ' points, which will replace your prior best score of ' + \
                str(self.best_student_score) + ' points.'
        else:
            return 'You score from this submission is ' + \
                str(new_score) + ' from ' + str(self.get_max_score()) + \
                ' points. Your prior best score was ' + \
                str(self.best_student_score) + ' points, and remains your current saved score.'

    # ----------- Handler for htm2lxml_no_iframe-----------
    @XBlock.handler
    def submit_webwork_html2xml_no_iframe(self, request_original, suffix=''):
        """
        Handle the student's submission.
        """
        response = {
            'success': False,
            'message': "Unexpected error occurred!",
            'data': '',
            'score': '',
            'scored': False
        }

        try:
            # Copy the request
            self._sanitize_request_html2xml(request)

            # Handle check answer
            if request['submit_type'] == "WWsubmit":

                if self.max_attempts > 0 and self.student_attempts >= self.max_attempts:
                    raise WeBWorKXBlockError("Maximum allowed attempts reached")

                if self.is_past_due():
                    raise WeBWorKXBlockError("Problem deadline has passed")

                #self.student_answer = request_original.copy() # This is far too to much
                self.student_answer = request.copy() # This is really to much
                self.student_attempts += 1
                response['scored'] = True

                response_parameters = HTML2XML_RESPONSE_PARAMETERS_CHECK

            # Handle show correct answer
            elif request['submit_type'] == "WWcorrectAns":

                if not self.show_answers:
                    raise WeBWorKXBlockError("Answers may not be shown for this problem")

                response_parameters = HTML2XML_RESPONSE_PARAMETERS_CORRECT

            # Handle preview answer
            elif request['submit_type'] == "preview":
                response_parameters = HTML2XML_RESPONSE_PARAMETERS_PREVIEW

            else:
                raise WeBWorKXBlockError("Unknown submit button used")

            # Looks good! Send the data to WeBWorK
            request.update(response_parameters)

            webwork_response = self.request_webwork_html2xml_split_json(request)

            # This is the "answer" that is recorded in the mysql DB tables.
            # TODO: We need to build a better JSON object to store for the html2xml option

            response["data"] = self._result_from_json_html2xml_split_json(webwork_response)

            # The next line can add something into "student_answer" which ends up in the submission saved data
            #self.student_answer.update({"aa":"bb"})

            if response["scored"]:
                raw_ww_score = float(webwork_response["score"])
                self.best_student_score = raw_ww_score * self.get_max_score()
                response["score"] = float(self.best_student_score)

                # Also send to the submissions API - if needed
                # see discussion below. Does not seem necessary for webwork
                #if sub_api:
                #    sub_api.create_submission(self.student_item_key, response)

                # Need to update the code here
                self.save()
                self.runtime.publish(self, 'grade', {
                    'value': float(self.best_student_score),
                    'max_value': self.get_max_score()
                })

            response['success'] = True
            response['message'] = "Success!"


        except WeBWorKXBlockError as e:
            response['message'] = e.message

        return Response(
                text = json.dumps(response),
                content_type =  "application/json",
                status = 200,
            )


    # ----------- Handler for standalone -----------
    @XBlock.handler
    def submit_webwork_standalone(self, request_original, suffix=''):
        """
        Handle the student's submission.
        """
        response = {
            'success': False,
            'message': "Unexpected error occurred!",
            'data': '',
            'score': '',
            'scored': False
        }

        try:
            # make 2 copies of the student_answer.
            # 1. For future reference and documentation and
            # the other for the submission usage an
            self.student_answer = request_original.json.copy()
            request = request_original.json.copy()
            self._sanitize_request_standalone(request)

            self.set_problem_period()
            # TODO: Consider tranform into a match-case claus
            # after upgrading to python 3.10 and above
            #===========Treat Predue submissions =================
            if self.problem_period is PPeriods.PreDue:
                #====Treat Submit Answers Button request====
                if request['submit_type'] == "submitAnswers":
                    response_parameters = STANDALONE_RESPONSE_PARAMETERS_CHECK
                    request.update(response_parameters)
                    if self.max_attempts > 0 and self.student_attempts > self.max_attempts:
                        # Do nothing aside adequate failure message
                        response['message'] = "Sorry, can't submit since your maximum allowed attempts reached"
                    else:
                        # At last...Conditions for positive request treatment are met:
                        # 1. self.max_attempts==0 or self.student_attempts <= self.max_attempts
                        # 2. request==submitAnswers
                        # 3. period==PreDue + small enough student_attempts
                        # So send a request to webwork (with the student answer)
                        # and deliver it's response to the student + save it to edx submission database
                        self.student_attempts += 1
			self.set_last_submission_time()
			self.student_answer = request.copy() # This is really too much
                        webwork_response = self.request_webwork_standalone(request)
                        response['renderedHTML'] = self._problem_from_json(webwork_response)
                        data_to_save = self._result_from_json_standalone(webwork_response)
                        response['scored'] = True
                        score = Score(
                            raw_earned = webwork_response['problem_result']['score'],
                            raw_possible = self.get_max_score()
                            )
                        self.set_score(score)
                        response['score'] = self.CurrentScore.raw_earned
                        #TO-DELETE#response['data'] = self._result_from_json_standalone(webwork_response)
                        response['success'] = True
                        response['message'] = "Successfull scored request treatment!"
                #====Treat Show Correct Answers Button request====
                elif request['submit_type'] == "showCorrectAnswers":
                    response_parameters = STANDALONE_RESPONSE_PARAMETERS_CORRECT
                    request.update(response_parameters)
                    response['message'] = (
                        "Invalid request: Correct answers can be shown only after " +
                        self.lock_date_end.strftime("%d/%m/%Y, %H:%M:%S")
                    )
                #====Treat Preview My Answers Button request====
                elif request['submit_type'] ==  "previewAnswers":
                    response_parameters = STANDALONE_RESPONSE_PARAMETERS_PREVIEW
                    request.update(response_parameters)
                    webwork_response = self.request_webwork_standalone(request)
                    response['renderedHTML'] = self._problem_from_json(webwork_response)
                    data_to_save = self._result_from_json_standalone(webwork_response)
                    #response['data'] = self._result_from_json_standalone(webwork_response)
                    response['success'] = True
                    response['message'] = "Successfull request treatment!"
                else:
                    raise WeBWorKXBlockError("Unknown submit button used")
            #===========Treat PostDueLocked submissions ==========
            elif self.problem_period is PPeriods.PostDueLocked:
                #====Treat Submit Answers Button request====
                if request['submit_type'] == "submitAnswers":
                    response['message'] = (
                        "Sorry, can't submit: Submissions are locked up until " +
                        self.lock_date_end.strftime("%d/%m/%Y, %H:%M:%S")
                    )
                #====Treat Show Correct Answers Button request====
                elif request['submit_type'] == "showCorrectAnswers":
                    response['message'] = (
                        "Sorry, Show Correct Answers is locked up until " +
                        self.lock_date_end.strftime("%d/%m/%Y, %H:%M:%S")
                    )
                #====Treat Preview My Answers Button request====
                elif request['submit_type'] ==  "previewAnswers":
                    response['message'] = (
                        "Sorry, previewing answers is locked up until" +
                        self.lock_date_end.strftime("%d/%m/%Y, %H:%M:%S")
                    )
                else:
                    raise WeBWorKXBlockError("Unknown submit button used")
            #===========Treat PostDueUnLocked submissions ========
            elif self.problem_period is PPeriods.PostDueUnLocked:
                #====Treat Submit Answers Button request====
                if request['submit_type'] == "submitAnswers":
                    response_parameters = STANDALONE_RESPONSE_PARAMETERS_CHECK
                    request.update(response_parameters)
                    webwork_response = self.request_webwork_standalone(request)
                    response['renderedHTML'] = self._problem_from_json(webwork_response)
                    data_to_save = self._result_from_json_standalone(webwork_response)
                    #TO-DELETE#response['data'] = self._result_from_json_standalone(webwork_response)
                    response['success'] = True
                    response['message'] = "Successfull unscored request treatment!"
                #====Treat Show Correct Answers Button request====
                elif request['submit_type'] == "showCorrectAnswers":
                    response_parameters = STANDALONE_RESPONSE_PARAMETERS_CORRECT
                    request.update(response_parameters)
                    webwork_response = self.request_webwork_standalone(request)
                    response['renderedHTML'] = self._problem_from_json(webwork_response)
                    data_to_save = self._result_from_json_standalone(webwork_response)
                    #TO-DELETE#response['data'] = self._result_from_json_standalone(webwork_response)
                    response['success'] = True
                    response['message'] = "Successfull request treatment!"
                #====Treat Preview My Answers Button request====
                elif request['submit_type'] ==  "previewAnswers":
                    response_parameters = STANDALONE_RESPONSE_PARAMETERS_PREVIEW
                    request.update(response_parameters)
                    webwork_response = self.request_webwork_standalone(request)
                    response['renderedHTML'] = self._problem_from_json(webwork_response)
                    data_to_save = self._result_from_json_standalone(webwork_response)
                    #TO-DELETE#response['data'] = self._result_from_json_standalone(webwork_response)
                    response['success'] = True
                    response['message'] = "Successfull request treatment!"
                else:
                    raise WeBWorKXBlockError("Unknown submit button used")
            #===========Treat problems without duedate============
            elif self.problem_period is PPeriods.NoDue:
                #====Treat Submit Answers Button request====
                if request['submit_type'] == "submitAnswers":
                    response_parameters = STANDALONE_RESPONSE_PARAMETERS_CHECK
                    request.update(response_parameters)
                    webwork_response = self.request_webwork_standalone(request)
                    response['renderedHTML'] = self._problem_from_json(webwork_response)
                    data_to_save = self._result_from_json_standalone(webwork_response)
                    #TO-DELETE#response['data'] = self._result_from_json_standalone(webwork_response)
                    response['success'] = True
                    if self.max_attempts > 0 and self.student_attempts > self.max_attempts:
                        response['message'] = (
                            "Successfull but unscored request treatment! <br/>" +
                            "Notice: <br/>" +
                            "   You have reached your maximum " + str(self.max_attempts) + " scorable attempts. <br/>" +
                            "   So no scores will be documented. <br/>" +
                            "   Feel free to use the show-correct-answers button"
                            )
                    else:
                        response['scored'] = True
                        score = Score(
                            raw_earned = webwork_response['problem_result']['score'],
                            raw_possible = self.get_max_score()
                            )
                        self.set_score(score)
                        response['score'] = self.CurrentScore.raw_earned
                        response['message'] = (
                            "Successfull scored request treatment! <br/>" +
                            "This is your " + str(self.student_attempts) + " submission attempt" +
                            " Out of the " + str(self.max_attempts) + " scorable submissions <br/>" +
                            "Your score for this submission try is: " + str(self.CurrentScore.raw_earned)
                            )
                    self.student_attempts += 1
                #====Treat Show Correct Answers Button request====
                elif request['submit_type'] == "showCorrectAnswers":
                    if self.max_attempts > 0 and self.student_attempts > self.max_attempts:
                        response_parameters = STANDALONE_RESPONSE_PARAMETERS_CORRECT
                        request.update(response_parameters)
                        webwork_response = self.request_webwork_standalone(request)
                        response['renderedHTML'] = self._problem_from_json(webwork_response)
                        data_to_save = self._result_from_json_standalone(webwork_response)
                        #TO-DELETE#response['data'] = self._result_from_json_standalone(webwork_response)
                        response['success'] = True
                        response['message'] = "Successfull unscored request treatment!"
                    else:
                        response['message'] = (
                            "Invalid request: Correct answers can be shown only after" +
                            " you will pass your maximum " + str(self.max_attempts) +
                            " scorable submission attempts. <br/>" +
                            "It is your " + str(self.student_attempts) + " submission attempt"
                            )
                #====Treat Preview My Answers Button request====
                elif request['submit_type'] ==  "previewAnswers":
                    response_parameters = STANDALONE_RESPONSE_PARAMETERS_PREVIEW
                    request.update(response_parameters)
                    webwork_response = self.request_webwork_standalone(request)
                    response['renderedHTML'] = self._problem_from_json(webwork_response)
                    data_to_save = self._result_from_json_standalone(webwork_response)
                    #TO-DELETE#response['data'] = self._result_from_json_standalone(webwork_response)
                    response['success'] = True
                    response['message'] = "Successfull request treatment!"
                else:
                    raise WeBWorKXBlockError("Unknown submit button used")
            #===========Unknown period - raise error==============
            else:
                raise WeBWorKXBlockError(
                    "Oops Problem period is undefined, thus request can't be treated!"
                    )


            # FIXME hide the show answers button
            # FIXME - the standalone renderer should do this or JS code

            # FIXME - we do NOT want all that data in the response. Comment out.
            response["data"] = json.dumps( data_to_save )

            current_submission_score = data_to_save.get('grade',0.0) # default to 0

# FIXME - CODE BELOW NEEDS TO BE MOVED UP TO WHERE IT IS RELEVANT
            if request["submit_type"] == "submitAnswers":
                # This line and the fact that it is a field, gets it to be saved.
                self.submission_data_to_save = self._result_from_json_standalone(webwork_response)

                scaled_ww_score = self.submission_data_to_save.get('current_submission_scaled_score',0.0)
                response['score'] = self.create_score_message(scaled_ww_score)

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
                    self.set_score(myscore) # will set self.best_student_score again

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

        except WeBWorKXBlockError as e:
            response['message'] = "fixme" # e.message

        return Response(
                # FIXME - this is from the html2xml code
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

    # ----------- Extras -----------
    @staticmethod
    def workbench_scenarios():
        """
        A canned scenario for display in the workbench.
        """
        return [
            ("WeBWorKXBlock",
             """<webwork/>
             """),
            ("WeBWorKXBlock With Parameters",
             """<webwork display_name="Tester test"
             problem="Technion/LinAlg/InvMatrix/en/3x3_seq01_calc_invA.pg"
             max_allowed_score="100" max_attempts="1" show_answers="True"/>
             """),
        ]
