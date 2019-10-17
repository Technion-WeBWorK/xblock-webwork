"""
XBlock that uses WeBWorK's PG grader.
"""
from __future__ import print_function

import pkg_resources
import json
import requests
import random
import datetime
import pytz

from xblock.core import XBlock
from django.utils.translation import ugettext_lazy as _ 
from xblock.fields import String, Scope, Integer, Dict, Float, Boolean, DateTime
from xblock.fragment import Fragment
from webob.response import Response
from xblockutils.studio_editable import StudioEditableXBlockMixin
from xblock.scorable import ScorableXBlockMixin, Score

PARAMETERS = {
    "language": "en",
    "displayMode": "MathJax",
    "outputformat": "json",
}

REQUEST_PARAMETERS = dict(PARAMETERS, **{
    "answersSubmitted": "0", 
})

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

@XBlock.needs("user")
class WeBWorKXBlock(ScorableXBlockMixin, XBlock, StudioEditableXBlockMixin):
    """
    XBlock that uses WeBWorK's PG grader.
    """

    # Makes LMS icon appear as a problem
    icon_class = 'problem'

    # ----------- External, editable fields -----------
    editable_fields = ('ww_server', 'ww_course', 'ww_username', 'ww_password', 'display_name', 'problem', 'max_allowed_score', 'max_attempts', 'show_answers')

    ww_server = String(
       display_name = _("WeBWorK server address"),
       default = _("https://webwork2.technion.ac.il/webwork2/html2xml"),
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
        default = "Technion/LinAlg/Matrices/en/SplitAsUpperLower.pg",
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

    student_score = Integer(
        default = 0,
        scope = Scope.user_state,
        help = _("The student's score"),
    )


    # ---------- Utils --------------

    @staticmethod
    def _problem_from_json(repsonse_json):
        return repsonse_json["body_part100"] + repsonse_json["body_part300"] + repsonse_json["body_part500"] + repsonse_json["body_part530"] + repsonse_json["body_part550"] + repsonse_json["body_part590"] + repsonse_json["body_part710"]  + repsonse_json["body_part780_optional"] + repsonse_json["body_part790"] + repsonse_json["body_part999"][:-16] + repsonse_json["head_part200"]

    @staticmethod
    def _result_from_json(repsonse_json):
        return repsonse_json["body_part300"]
    
    @staticmethod
    def _sanitize(request):
        for action in (REQUEST_PARAMETERS, RESPONSE_PARAMETERS_CORRECT, RESPONSE_PARAMETERS_PREVIEW, RESPONSE_PARAMETERS_CHECK):
            for key in action:
                request.pop(key, None)

    def request_webwork(self, params):
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
    def has_submitted_answer(self):
        """
        For scoring, has the user alreadu submitted an answer?
        """
        return self.student_attempts > 0

    def max_score(self):
        """
        Get the max score
        """
        return self.max_allowed_score

    def get_score(self):
        """
        For socring, get the score.
        """
        return self.student_score

    def set_score(self, score):
        """
        For socring, save the score.
        """
        self.student_score = score.earned

    def calculate_score(self):
        """
        For scoring, calculate the score.
        """
        return Score(
            earned = self.student_score, 
            possible = self.max_score()
        )

    def resource_string(self, path):
        """
        Handy helper for getting resources from our kit.
        """
        data = pkg_resources.resource_string(__name__, path)
        return data.decode("utf8")

    # ----------- View -----------
    def student_view(self, context=None):
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
            'message': "Unexpected error occured!",
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
                raise WeBWorKXBlockError("Unkown submit button used")

            # Looks good! Send the data to WeBWorK
            request.update(response_parameters)

            webwork_response = self.request_webwork(request)
            response["data"] = self._result_from_json(webwork_response)
            
            if response["scored"]:
                self.student_score = webwork_response["score"]
                response["score"] = self.student_score
            
            response['success'] = True
            response['message'] = "Success!"

        except WeBWorKXBlockError as e:
            response['message'] = e.message

        return Response(
                body = json.dumps(response), 
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
            return utcnow() > close_date
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
             """<webwork display_name="Tester test" problem="Technion/LinAlg/InvMatrix/en/3x3_seq01_calc_invA.pg" max_allowed_score="100" max_attempts="1" show_answers="True"/>
             """),
        ]
