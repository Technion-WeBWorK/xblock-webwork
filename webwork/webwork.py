"""
XBlock that uses WeBWorK's PG grader.
"""
import json
import random
import datetime
import requests # Ease the contact with webwork server via HTTP/1.1
import pkg_resources # Used here to return resource name as a string
import pytz # python timezone
from xblock.core import XBlock
from django.utils.translation import ugettext_lazy as _
from xblock.fields import String, Scope, Integer, Dict, Float, Boolean, DateTime
from xblock.fragment import Fragment
from webob.response import Response # Uses WSGI format(Web Server Gateway Interface) over HTTP to contact webwork
from xblockutils.studio_editable import StudioEditableXBlockMixin
from xblock.scorable import ScorableXBlockMixin, Score
import six
from xblock.completable import XBlockCompletionMode
try:
    from submissions import api as sub_api
except ImportError:
    sub_api = None  # We are probably in the workbench. Don't use the submissions API

PARAMETERS = {
    "language": "en",
    "displayMode": "MathJax",
    "outputformat": "json",
}
# FIXME  - allow update of answersSubmitted according to user history
REQUEST_PARAMETERS = dict(PARAMETERS, **{
    "answersSubmitted": "0",
})

# FIXME  - Increase by 1 from current answersSubmitted
RESPONSE_PARAMETERS_BASE = dict(PARAMETERS, **{
    "psvn" : "54321",
    "showSummary" : "1",
    "answersSubmitted": "1",
})

RESPONSE_PARAMETERS_CHECK = dict(RESPONSE_PARAMETERS_BASE, **{
    "WWsubmit": "Check Answers"
})

RESPONSE_PARAMETERS_PREVIEW = dict(RESPONSE_PARAMETERS_BASE, **{
    "preview": "Preview My Answers"
})

RESPONSE_PARAMETERS_CORRECT = dict(RESPONSE_PARAMETERS_BASE, **{
    "WWcorrectAns": "Show correct answers"
})

class WeBWorKXBlockError(RuntimeError):
    pass

class StudentViewUserStateMixin:
    """
    This class has been copy-pasted from the problem-builder xblock file mixins.py
    it provides student_view_user_state view.

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

# TODO consider adding more decorations to XBlock (@XBlock.needs("user")).
# i.e. other needs/wants such as "user_state"
# Notice though that documentation is scarce.
# I found some useful links below:
# 1. In module_render.py you can find LMS services by
#    running a search for "services={".
# https://github.com/edx/edx-platform/blob/master/lms/djangoapps/courseware/module_render.py
# 2. General info from open edx conference
# https://openedx.atlassian.net/wiki/spaces/AC/pages/161400730/Open+edX+Runtime+XBlock+API
# 3. The below link to user_service.py might be the source
# code that sets the "user" service
# https://github.com/edx/XBlock/blob/d93d0981947c69d0b8d6bae269b131942006bb02/xblock/reference/user_service.py
#
# Needed features:
# ----------------
# 1. attempts_management
# 2. submission_date_management
# 3. get_old_answers
# 4. grade_management
# ----------------
# out of which the first 2 are handled (but not tested) and the last
# ones need to be accomplished

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

    # ----------- External, editable fields -----------
    editable_fields = (
        'ww_server_root', 'ww_server', 'ww_course', 'ww_username', 'ww_password',
        'display_name', 'problem', 'max_allowed_score', 'max_attempts', 'show_answers'
        )

    ww_server_root = String(
       display_name = _("WeBWorK server root address"),
       default = _("https://webwork2.technion.ac.il"),
       # default = _("http://localhost:8080"),  # full local docker webwork
       # default = _("http://webwork"), # docker webwork2 container attached to edx docker network
       # default = _("http://localhost:3000"),  # standalone local docker webwork
       scope = Scope.content,
       help=_("This is the root URL of the webwork server."),
    )

    # FIXME - ww_server should be a relative address, based on ww_server_root
    ww_server = String(
       display_name = _("WeBWorK server address"),
       default = _("https://webwork2.technion.ac.il/webwork2/html2xml"),
       # Next line is for when working with full local docker webwork
       # default = _("http://localhost:8080/webwork2/html2xml"),
       # when webwork2 containter is on edx docker network
       # default = _("http://webwork2/webwork2/html2xml"),
       # Next line is for when working with local docker StandAlone webwork
       # default = _("http://localhost:3000/"),
       scope = Scope.content,
       help=_("This is the full URL of the webwork server."),
    )

    ww_course = String(
       display_name = _("WeBWorK course"),
       default = _("daemon_course"),
       scope = Scope.content,
       help=_("This is the course name to use when interfacing with the webwork server."),
    )

    ww_username = String(
       display_name = _("WeBWorK username"),
       default = _("daemon"),
       scope = Scope.content,
       help=_("This is the username to use when interfacing with the webwork server."),
    )

    ww_password = String(
       display_name = _("WeBWorK password"),
       default = _("wievith3Xos0osh"),
       scope = Scope.content,
       help=_("This is the password to use when interfacing with the webwork server."),
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
        scope = Scope.settings,
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

    show_answers = Boolean(
        display_name = _("Show Answers"),
        default = False,
        scope = Scope.settings,
        help = _("Allow students to view correct answers?"),
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

    # ---------- Utils --------------

    @staticmethod
    def _problem_from_json(response_json):
        raw_state = \
            response_json["body_part100"] + response_json["body_part300"] + \
            response_json["body_part500"] + response_json["body_part530"] + \
            response_json["body_part550"] + response_json["body_part590"] + \
            response_json["body_part710"] + response_json["body_part780_optional"] + \
            response_json["body_part790"] + response_json["body_part999"][:-16] + \
            response_json["head_part200"]
        # Rederly standalone - need:
        #     everything between <body> and </body>
        # and then the JS loads
        #     between <!-- JS Loads --> and BEFORE <title>

        # Replace source address where needed
        fixed_state = raw_state.replace( "\"/webwork2_files", "\"https://webwork2.technion.ac.il/webwork2_files" )
        # fixed_state = raw_state.replace( "\"/webwork2_files", "\"http://localhost:8080/webwork2_files" )
        # Next line is for when working with full local docker webwork
        # fixed_state = raw_state.replace("\"/webwork2_files", "\"file:///home/guy/WW/webwork2/htdocs" )
        # FIXME
        #fixed_state = raw_state.replace( "\"/webwork2_files", "\"" + str(self.ww_server_root) + "/webwork2_files" )
        return fixed_state

    @staticmethod
    def _result_from_json(response_json):
        return response_json["body_part300"]

    @staticmethod
    def _sanitize(request):
        for action in (
            REQUEST_PARAMETERS, RESPONSE_PARAMETERS_CORRECT,
            RESPONSE_PARAMETERS_PREVIEW, RESPONSE_PARAMETERS_CHECK
            ):
            for key in action:
                request.pop(key, None)

    def request_webwork(self, params):
        # html2xml uses HTTP GET
        # Standalone uses HTTP POST
        # See https://requests.readthedocs.io/en/master/user/quickstart/#make-a-request
        # probably need something like date = { params, 'courseID':str(self.ww_course), ... }
        # remember the URL needs to have :3000/render-api
        # and outputFormat set to "simple" and format set to "json".
        # Check by examining form parameters from Rederly UI on "render" call.
        return requests.get(self.ww_server, params=dict(
                params,
                courseID=str(self.ww_course),
                userID=str(self.ww_username),
                course_password=str(self.ww_password),
                problemSeed=str(self.seed),
                psvn=str(self.psvn),
                sourceFilePath=str(self.problem)
            )).json()


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
        For socring, get the score.
        """
        return self.CurrentScore

    def set_score(self, score):
        """
        score type must be of of type Score
        This method sets WeBWorKXBlock student_score and CurrentScore fields.
        student_score is a webwork-problem database field to be saved
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
        if not self.seed:
            self.seed = random.randint(1,2**31-1)

        if not self.psvn:
            self.psvn = random.randint(1,500)

        if self.max_attempts > 0 and self.student_attempts >= self.max_attempts:
            disabled = True

        form = self._problem_from_json(self.request_webwork(REQUEST_PARAMETERS))

        # hide the show answers button
        if not self.show_answers:
            form += "<style> input[name='WWcorrectAns']{display: none !important;}</style>"

        html = self.resource_string("static/html/webwork.html")
        frag = Fragment(html.format(self=self,form=form))
        frag.add_css(self.resource_string("static/css/webwork.css"))
        frag.add_javascript(self.resource_string("static/js/src/webwork.js"))
        frag.initialize_js('WeBWorKXBlock')
        return frag

    # ----------- Handler -----------
    @XBlock.handler
    def submit_webwork(self, request_original, suffix=''):
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
            self._sanitize(request)

            # Handle check answer
            if request["submit_type"] == "WWsubmit":

                if self.max_attempts > 0 and self.student_attempts >= self.max_attempts:
                    raise WeBWorKXBlockError("Maximum allowed attempts reached")

                if self.is_past_due():
                    raise WeBWorKXBlockError("Problem deadline has passed")

                self.student_answer = request.copy()
                self.student_attempts += 1
                response["scored"] = True

                response_parameters = RESPONSE_PARAMETERS_CHECK

            # Handle show correct answer
            elif request["submit_type"] == "WWcorrectAns":

                if not self.show_answers:
                    raise WeBWorKXBlockError("Answers may not be shown for this problem")

                response_parameters = RESPONSE_PARAMETERS_CORRECT

            # Handle preview answer
            elif request["submit_type"] == "preview":
                response_parameters = RESPONSE_PARAMETERS_PREVIEW

            else:
                raise WeBWorKXBlockError("Unknown submit button used")

            # Looks good! Send the data to WeBWorK
            request.update(response_parameters)

            webwork_response = self.request_webwork(request)
            # This is the "answer" that is documented in the mysql DB tables.
            # TODO: We need to build a better JSON object to store
            response["data"] = self._result_from_json(webwork_response)

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
