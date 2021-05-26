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
from xblock.core import XBlock
from django.utils.translation import ugettext_lazy as _
from xblock.fields import String, Scope, Integer, List, Dict, Float, Boolean, DateTime, UNIQUE_ID
from xblock.validation import ValidationMessage
from web_fragments.fragment import Fragment
from webob.response import Response # Uses WSGI format(Web Server Gateway Interface) over HTTP to contact webwork
from xblockutils.studio_editable import StudioEditableXBlockMixin
from xblock.scorable import ScorableXBlockMixin, Score
from xblock.completable import XBlockCompletionMode
try:
    from submissions import api as sub_api
except ImportError:
    sub_api = None  # We are probably in the workbench. Don't use the submissions API

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
    "answersSubmitted": "0",
})

# FIXME  - Increase by 1 from current answersSubmitted
HTML2XML_RESPONSE_PARAMETERS_BASE = dict(HTML2XML_PARAMETERS, **{
    "psvn" : "54321",
    "showSummary" : "1",
    "answersSubmitted": "1",
})

HTML2XML_RESPONSE_PARAMETERS_CHECK = dict(HTML2XML_RESPONSE_PARAMETERS_BASE, **{
    "WWsubmit": "Check Answers"
})

HTML2XML_RESPONSE_PARAMETERS_PREVIEW = dict(HTML2XML_RESPONSE_PARAMETERS_BASE, **{
    "preview": "Preview My Answers"
})

HTML2XML_RESPONSE_PARAMETERS_CORRECT = dict(HTML2XML_RESPONSE_PARAMETERS_BASE, **{
    "WWcorrectAns": "Show correct answers"
})

STANDALONE_PARAMETERS = {
    "language": "en",
    "displayMode": "MathJax",
    "format" : "json",
    "outputFormat": "simple",
    "showSummary": "1",
    "permissionLevel": "0",
}

# FIXME  - allow update of answersSubmitted according to user history
STANDALONE_REQUEST_PARAMETERS = dict(STANDALONE_PARAMETERS, **{
    "answersSubmitted": "0",
})

# FIXME  - Increase by 1 from current answersSubmitted
STANDALONE_RESPONSE_PARAMETERS_BASE = dict(STANDALONE_PARAMETERS, **{
    "psvn" : "54321",
    "showSummary" : "1",
    "answersSubmitted": "1",
})

STANDALONE_RESPONSE_PARAMETERS_CHECK = dict(STANDALONE_RESPONSE_PARAMETERS_BASE, **{
    "WWsubmit": "Check Answers"
})

STANDALONE_RESPONSE_PARAMETERS_PREVIEW = dict(STANDALONE_RESPONSE_PARAMETERS_BASE, **{
    "preview": "Preview My Answers"
})

STANDALONE_RESPONSE_PARAMETERS_CORRECT = dict(STANDALONE_RESPONSE_PARAMETERS_BASE, **{
    "WWcorrectAns": "Show correct answers"
})

class WeBWorKXBlockError(RuntimeError):
    pass

# FIXME - this should be kept in a different file, clearing keeping the code from that
# project seperate from that of this project.
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

class SubmittingXBlockMixin:
    """
    This class has been copy-pasted from the problem-builder xblock
    It Simplifies the use of edX "submissions API"
    within the Webwork XBlock
    """
    completion_mode = XBlockCompletionMode.COMPLETABLE
    has_score = True

    @property
    def student_item_key(self):
        """
        Get the student_item_dict required for the submissions API.
        """
        assert sub_api is not None
        location = self.location.replace(branch=None, version=None)  # Standardize the key in case it isn't already
        return dict(
            student_id=self.runtime.anonymous_student_id,
            course_id=six.text_type(location.course_key),
            item_id=six.text_type(location),
            item_type=self.scope_ids.block_type,
        )

@XBlock.needs("user")
class WeBWorKXBlock(
    ScorableXBlockMixin, XBlock, StudioEditableXBlockMixin,
    SubmittingXBlockMixin, StudentViewUserStateMixin):
    """
    XBlock that uses WeBWorK's PG grader.
    """

    # Makes LMS icon appear as a problem
    icon_class = 'problem'
    category = 'ww-problem'

# FIXME
    main_settings = None
    def reload_main_setting(self):
        self.main_settings = self.course.other_course_settings.get('webwork_settings', {})

    def get_default_server(self):
        return self.main_settings.get('course_defaults',{}).get('default_server')

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
            self.current_server_settings.update({
                "server_type":             self.ww_server_type,
                "server_api_url":          self.ww_server_api_url,
                "server_static_files_url": self.ww_server_static_files_url,
                "auth_data":               self.auth_data,
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
        self.ww_server_id_options = options_to_offer

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
        'problem', 'max_allowed_score', 'max_attempts',
        # For html2xml only:
        'ww_course', 'ww_username', 'ww_password',
        # Less important settings
        'show_answers',
        'post_deadline_lockdown',
        'iframe_min_height', 'iframe_max_height', 'iframe_min_width',
        'display_name',
        # Need in Studio but should be hidden from end-user
        'settings_are_dirty'
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

    settings_are_dirty = Boolean(
       scope = Scope.settings,
       default = False
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
       display_name = _("WeBWorK server address with API endoint"),
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

    # Moved into external settings - "Other course settings" data structure
    ww_course = String(
       display_name = _("WeBWorK course"),
       default = _("daemon_course"),
       scope = Scope.settings,
       help=_("This is the course name to use when interfacing with the html2xml interface on a regular webwork server."),
    )

    ww_username = String(
       display_name = _("WeBWorK username"),
       default = _("daemon"),
       scope = Scope.settings,
       help=_("This is the username to use when interfacing with the html2xml interface on a regular webwork server."),
    )

    ww_password = String(
       display_name = _("WeBWorK password"),
       default = _("wievith3Xos0osh"),
       scope = Scope.settings,
       help=_("This is the password to use when interfacing with the html2xml interface on a regular webwork server."),
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
        # FIXME
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

    psvn = Integer(
        default = 0,
        scope = Scope.preferences,
        help = _("Problem set version number, used to seed multi-part problems"),
    )

    student_score = Float(
        default = 0,
        scope = Scope.user_state,
        help = _("The student's score"),
    )

    # ----------- Internal runtime fields -----------

    unique_id = String(
        display_name = _("Runtime XBlock UNIQUE_ID"),
        default = UNIQUE_ID,
        scope = Scope.user_state,
        help = _("A runtime unique ID for this instance of this XBlock."),
    )



    def validate_field_data(self, validation, data):
        if not isinstance(data.custom_parameters, list):
            _ = self.runtime.service(self, "i18n").ugettext
            validation.add(ValidationMessage(ValidationMessage.ERROR, str(
                _("Custom Parameters must be a list")
            )))

    @property
    def course(self):
        """
        Return course by course id.
        """
        return self.runtime.modulestore.get_course(self.runtime.course_id)


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
        #if self.ww_server_type == 'html2xml':
        if self.current_server_settings.get("server_type","") == 'html2xml':
            raw_state = \
                response_json["body_part100"] + response_json["body_part300"] + \
                response_json["body_part500"] + response_json["body_part530"] + \
                response_json["body_part550"] + response_json["body_part590"] + \
                response_json["body_part710"] + response_json["body_part780_optional"] + \
                response_json["body_part790"] + response_json["body_part999"][:-16] + \
                response_json["head_part200"]
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
            fixed_state = response_json["renderedHTML"]
        else:
            fixed_state = 'Error'

        return fixed_state

    def _result_from_json_html2xml(self,response_json):
        if response_json is None:
            return "Error"
        return response_json["body_part300"]

    def _result_from_json_standalone(self,response_json):
        # Need data from
        #   answers
        #   form_data
        #   problem_result
        #   problem_state
        # Maybe also:
        #   flags
        #   debug
        return "testing";
# FIXME
#        return '{ answers: '        + response_json["answers"] + \
#               '  form_data: '      + response_json["form_data"] + \
#               '  problem_result: ' + response_json["problem_result"] + \
#               '  problem_state: '  + response_json["problem_state"] + ' }'

    @staticmethod
    def _sanitize_html2xml(request):
        for action in (
            HTML2XML_REQUEST_PARAMETERS, HTML2XML_RESPONSE_PARAMETERS_CORRECT,
            HTML2XML_RESPONSE_PARAMETERS_PREVIEW, HTML2XML_RESPONSE_PARAMETERS_CHECK
            ):
            for key in action:
                request.pop(key, None)

    @staticmethod
    def _sanitize_standalone(request):
        for action in (
            STANDALONE_REQUEST_PARAMETERS, STANDALONE_RESPONSE_PARAMETERS_CORRECT,
            STANDALONE_RESPONSE_PARAMETERS_PREVIEW, STANDALONE_RESPONSE_PARAMETERS_CHECK
            ):
            for key in action:
                request.pop(key, None)

    def request_webwork_html2xml(self, params):
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
                    psvn=str(self.psvn),
                    sourceFilePath=str(self.problem)
                ))
        if my_res:
            return my_res.json()
        return None

    def request_webwork_standalone(self, params):
        # Standalone uses HTTP POST
        # See https://requests.readthedocs.io/en/master/user/quickstart/#make-a-request
        # probably need something like date = { params, 'courseID':str(self.ww_course), ... }
        # remember the URL needs to have :3000/render-api
        # and outputFormat set to "simple" and format set to "json".
        # Check by examining form parameters from Rederly UI on "render" call.

        # Get updated main course settings from main course "Other course settings"
        # Do this now, as we may need updated main connection settings

        self.reload_main_setting()
        # and then
        self.set_current_server_settings()

        my_url = self.current_server_settings.get("server_api_url")
        if my_url:
            my_res = requests.post(my_url, params=dict(
                    params,
                    # standalone does not have course/user/password
                    problemSeed=str(self.seed),
                    psvn=str(self.psvn),
                    sourceFilePath=str(self.problem)
                ))
            if my_res:
                return my_res.json()
            return None;
            

    # ----------- Grading -----------
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
        """
        return self.CurrentScore

    def set_score(self, score):
        """
        score type must be of of type Score
        This method sets WeBWorKXBlock student_score and CurrentScore fields.
        student_score is a webwork-problem database field to be saved.
        CurrentScore is a ScorableXBlockMixin defined tuple.
        this field is needed for the "must be implemented in a child class"
        methods: calculate_score() and get_score()
        """
        assert type(score) == Score
        self.student_score = float(score.raw_earned)
        self.CurrentScore = score

    def calculate_score(self):
        return self.CurrentScore

    def max_score(self):
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
            return self.student_view_html2xml(self)
        if self.current_server_settings.get("server_type") == 'standalone':
            return self.student_view_standalone(self)
        return self.student_view_error(self)

    # ----------- View for html2xml -----------

    #FIXME
    #def student_view_html2xml(self, context=None, show_detailed_errors=False):
    def student_view_html2xml(self, context=None, show_detailed_errors=True):
        """
        The primary view of the XBlock, shown to students
        when viewing courses. For html2xml interface use
        """
        if not self.seed:
            self.seed = random.randint(1,2**31-1)

        if not self.psvn:
            self.psvn = random.randint(1,500)

        if self.max_attempts > 0 and self.student_attempts >= self.max_attempts:
            disabled = True

        form = self._problem_from_json(self.request_webwork_html2xml(HTML2XML_REQUEST_PARAMETERS))

        # hide the show answers button
        if not self.show_answers:
            form += "<style> input[name='WWcorrectAns']{display: none !important;}</style>"

        html = self.resource_string("static/html/webwork_html2xml.html")
        frag = Fragment(html.format(self=self,form=form))
        frag.add_css(self.resource_string("static/css/webwork.css"))
        frag.add_javascript(self.resource_string("static/js/src/webwork_html2xml.js"))
        frag.initialize_js('WeBWorKXBlock')
        return frag

    # ----------- View for standalone -----------

    # FIXME
    #def student_view_standalone(self, context=None, show_detailed_errors=False):
    def student_view_standalone(self, context=None, show_detailed_errors=True):
        """
        The primary view of the XBlock, shown to students
        when viewing courses. For standalone renderer use
        """
        if not self.seed:
            self.seed = random.randint(1,2**31-1)

        if not self.psvn:
            self.psvn = random.randint(1,500)

        if self.max_attempts > 0 and self.student_attempts >= self.max_attempts:
            disabled = True

        mysrcdoc = self._problem_from_json(self.request_webwork_standalone(STANDALONE_REQUEST_PARAMETERS)
           ).replace( "&", "&amp;"      # srcdoc needs "&" encoded
           ).replace( "\"", "&quot;" )  # srcdoc needs double quotes encoded. Must do second.
           #.replace( "\n", "" )

        #test123 = self.course.other_course_settings.get('ww_standalone')
        #test123a = test123[ "test1" ]
        test123 = self.current_server_settings
        test123a = json.dumps(test123)
        tmp1 = "temp value"
        if self.current_server_settings.get("server_type","") == 'standalone':
            tmp1 = "reports == standalone"
        else:
            tmp1 = "reports != standalone"
        test123a = test123a + "   " + self.current_server_settings.get("server_type","") + tmp1
            

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
        js1  = self.resource_string("static/js/src/webwork_standalone.js")

        frag = Fragment(html.format(self=self,srcdoc=mysrcdoc,unique_id=self.unique_id,iFrameInit=iframe_resize_init,test123a=test123a))

        frag.add_javascript_url('https://cdnjs.cloudflare.com/ajax/libs/iframe-resizer/4.2.9/iframeResizer.js')

        frag.add_css(self.resource_string("static/css/webwork.css"))
        frag.add_javascript( js1 )

        frag.initialize_js('WeBWorKXBlock', {
          'unique_id' : self.unique_id,
          'rpID' : iframe_id
        })

        return frag


    # ----------- View for error -----------

    def student_view_error(self, context=None, show_detailed_errors=False):
        """
        The primary view of the XBlock, shown to students
        when viewing courses. When error hit
        """

        form = ""

        html = self.resource_string("static/html/webwork_html2xml.html")
        frag = Fragment(html.format(self=self,form=form))
        frag.add_css(self.resource_string("static/css/webwork.css"))
        return frag


    # ----------- Handler for htm2lxml-----------
    @XBlock.handler
    def submit_webwork_html2xml(self, request_original, suffix=''):
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
            request = request_original.json.copy()
            self._sanitize_html2xml(request)

            # Handle check answer
            if request["submit_type"] == "WWsubmit":

                if self.max_attempts > 0 and self.student_attempts >= self.max_attempts:
                    raise WeBWorKXBlockError("Maximum allowed attempts reached")

                if self.is_past_due():
                    raise WeBWorKXBlockError("Problem deadline has passed")

                self.student_answer = request.copy()
                self.student_attempts += 1
                response["scored"] = True

                response_parameters = HTML2XML_RESPONSE_PARAMETERS_CHECK

            # Handle show correct answer
            elif request["submit_type"] == "WWcorrectAns":

                if not self.show_answers:
                    raise WeBWorKXBlockError("Answers may not be shown for this problem")

                response_parameters = HTML2XML_RESPONSE_PARAMETERS_CORRECT

            # Handle preview answer
            elif request["submit_type"] == "preview":
                response_parameters = HTML2XML_RESPONSE_PARAMETERS_PREVIEW

            else:
                raise WeBWorKXBlockError("Unknown submit button used")

            # Looks good! Send the data to WeBWorK
            request.update(response_parameters)

            webwork_response = self.request_webwork_html2xml(request)
            # This is the "answer" that is documented in the mysql DB tables.
            # TODO: We need to build a better JSON object to store
            response["data"] = self._result_from_json_html2xml(webwork_response)

            if response["scored"]:
                score = Score(raw_earned = webwork_response["score"], raw_possible = self.max_score())
                self.set_score(score)
                response["score"] = self.CurrentScore.raw_earned

            response['success'] = True
            response['message'] = "Success!"

            # Create a submission entry at courseware_studentmodule mysql57 table
            if sub_api:
                # Also send to the submissions API:
                sub_api.create_submission(self.student_item_key, response)

            self.runtime.publish(self, 'grade', {
                'value': self.CurrentScore.raw_earned,
                'max_value': self.CurrentScore.raw_possible,
            })

            self.runtime.publish(self, 'xblock.webwork.submitted', {
                'num_attempts': self.student_attempts,
                'submitted_answer': response["data"],
                'grade': self.student_score,
            })

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
            # Copy the request
            request = request_original.json.copy()
            self._sanitize_standalone(request)


            # Handle check answer
            if request["submit_type"] == "submitAnswers":

                if self.max_attempts > 0 and self.student_attempts >= self.max_attempts:
                    raise WeBWorKXBlockError("Maximum allowed attempts reached")

                if self.is_past_due():
                    raise WeBWorKXBlockError("Problem deadline has passed")

                self.student_answer = request.copy()
                self.student_attempts += 1
                response["scored"] = True

                response_parameters = STANDALONE_RESPONSE_PARAMETERS_CHECK

            # Handle show correct answer
            elif request["submit_type"] == "showCorrectAnswers":

                if not self.show_answers:
                    raise WeBWorKXBlockError("Answers may not be shown for this problem")

                response_parameters = STANDALONE_RESPONSE_PARAMETERS_CORRECT

            # Handle preview answer
            elif request["submit_type"] == "previewAnswers":
                response_parameters = STANDALONE_RESPONSE_PARAMETERS_PREVIEW

            else:
                raise WeBWorKXBlockError("Unknown submit button used")

            # Looks good! Send the data to WeBWorK

            # FIXME - this is from the html2xml code

            request.update(response_parameters)

            webwork_response = self.request_webwork_standalone(request)

            # This is the "answer" that is documented in the mysql DB tables.
            # TODO: We need to build a better JSON object to store

            # Here we do not need to add URL encoding for double quote '"' or ampersand '&'
            response["renderedHTML"] = self._problem_from_json(webwork_response)

            # FIXME hide the show answers button
            # FIXME - the standalone renderer should do this

            response["data"] = self._result_from_json_standalone(webwork_response)

            # FIXME - this is from the html2xml code

# FIXME
            #if response["scored"]:
            #    score = Score(raw_earned = webwork_response["score"], raw_possible = self.max_score())
            #    self.set_score(score)
            #    response["score"] = self.CurrentScore.raw_earned

            response['success'] = True
            response['message'] = "Success!"

            # Create a submission entry at courseware_studentmodule mysql57 table
# FIXME
#            if sub_api:
#                # Also send to the submissions API:
#                sub_api.create_submission(self.student_item_key, response)

# FIXME
#            self.runtime.publish(self, 'grade', {
#                'value': self.CurrentScore.raw_earned,
#                'max_value': self.CurrentScore.raw_possible,
#            })

# FIXME
#            self.runtime.publish(self, 'xblock.webwork.submitted', {
#                'num_attempts': self.student_attempts,
#                'submitted_answer': response["data"],
#                'grade': self.student_score,
#            })

        except WeBWorKXBlockError as e:
            response['message'] = e.message

        return Response(
                # FIXME - this is from the html2xml code
                text = json.dumps(response),
                content_type =  "application/json",
                status = 200,
            )


    # ---------- Due Date ----------
    def utcnow():
        """
        Get current date and time in UTC
        """
        return datetime.datetime.now(tz=pytz.utc)

    def is_past_due(self):
        """
        Is it now past this problem's due date?
        """
        return self.past_due()

    def past_due(self):
        """
        Return whether due date has passed.
        """
        try:
            # The try import clause probably placed here since the import
            # works only under full devstack Edx environment but
            # fails under xblock-sdk Edx environment which lacks
            # the xmodule.
            # TODO - verify proper work of this method in the devstack build
            from xmodule.util.duedate import get_extended_due_date
        except ImportError:
            return False
        due = get_extended_due_date(self)
        try:
            graceperiod = self.graceperiod
        except AttributeError:
            # graceperiod and due are defined in InheritanceMixin
            # It's used automatically in edX but the unit tests will need to mock it out
            graceperiod = None

        if graceperiod is not None and due:
            close_date = due + graceperiod
        else:
            close_date = due

        if close_date is not None:
            return datetime.datetime.now(datetime.timezone.utc) > close_date
        return False


    def studio_view(self, context):
        """
        Get Studio View fragment
        """

        # Get updated main course settings from main course "Other course settings"
        # Do this now, before presenting the options, etc.
        self.reload_main_setting()

        #DELETE THIS#self.main_settings = self.course.other_course_settings.get('webwork_settings', {})
        # The set the list of server_id_options to be displayed
        self.set_ww_server_id_options()

        # When relevant - set a default value for ww_server_id
        if not self.ww_server_id and self.settings_type == 1:
            # No setting currently set, but in server_id mode - so set the default
            default_server = self.main_settings.get('course_defaults',{}).get('default_server')
            if default_server:
                self.ww_server_id = default_server

# FIXME GGGGGGGGGGG
#        if self.default_server:
#            self.default_server_type = self.main_settings.get( self.default_server, {} ).get( "server_type" )
#        else:
#            self.default_server_type = None

        # Initialize the choices
        # GGGGGGGGGG
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
