"""
XBlock that uses WeBWorK's PG grader.
"""
from __future__ import print_function

import pkg_resources
import json

from xblock.core import XBlock
from django.utils.translation import ugettext_lazy as _ 
from xblock.fields import String, Scope, Integer, Dictionary, Float
from xblock.fragment import Fragment
from xblockutils.studio_editable import StudioEditableXBlockMixin

from scorable import ScorableXBlockMixin, Score

@XBlock.needs("user")
class WeBWorKXBlock(StudioEditableXBlockMixin, ScorableXBlockMixin, XBlock):
    """
    XBlock that uses WeBWorK's PG grader.
    """

    # Makes LMS icon appear as a problem
    icon_class = 'problem'

    # ----------- External, editable fields -----------
    editable_fields = ('display_name', 'problem', 'max_score', 'max_attempts')

    display_name = String(
	   display_name = _("Display Name"),
       default = _("WeBWorK Problem"),
       scope = Scope.settings,
       help=_("This name appears in the horizontal navigation at the top of the page."),
    )

    problem = String(
        display_name = _("Problem"),
        default = "example",
        scope = Scope.content,
        help =_("The path to load the problem from."),
    )

    max_score = Float(
        display_name = _("Maximum score"),
        default = 0.0,
        scope = Scope.settings,
        help = _("Max possible score attainable"),
    )

    max_attempts = Integer(
        display_name = _("Allowed Submissions"),
        default = 0,
        scope = Scope.settings,
        help = _("Max number of allowed submissions (0 = unlimited)"),
    )

    # ----------- Internal student fields -----------
    student_answer = Dictionary(
        default = None,
        scope = Scope.user_state,
        help = _("The student's answer."),
    )

    student_attempts = Integer(
        default = 0,
        scope = Scope.user_state,
        help = _("Number of times student has submitted problem"),
    )

    # ----------- Grading -----------
    def has_submitted_answer(self):
        """
        For scoring, has the user alreadu submitted an answer?
        """
        return self.student_attempts > 0

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
            possible = sself.max_score
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
        if self.is_past_due() or (self.max_attempts > 0 and self.student_attempts >= self.max_attempts):
            disabled = True

        html = self.resource_string("static/html/webwork.html")
        frag = Fragment(html.format(self=self))
        frag.add_css(self.resource_string("static/css/webwork.css"))
        frag.add_javascript(self.resource_string("static/js/src/webwork.js"))
        frag.initialize_js('WeBWorKXBlock')
        return frag

    # ----------- Handler -----------
    @XBlock.handler
    def submit_webwork(self, request, suffix=''):
        """
        Handle the student's submission.
        """
        response = response = {'success': False}

        # Make sure attempts left
        if self.max_attempts > 0 and self.student_attempts >= self.max_attempts:
            response['error'] = "Maximum allowed attempts reached"

        # Make sure it's not past due
        elif self.is_past_due():
            response['error'] = "Unable to submit past due date: {}".format(self.due)

        # Looks good!
        else:
            response['success'] = True
        
        return Response(
                body = json.dumps(response), 
                content_type =  "application/json",
                status = 200,
            )

        self.count += int(request.increase_by)
        return {"count": self.count}

    # ----------- Extras -----------
    def is_past_due(self):
        """
        Returns True if unit is past due
        """
        if self.due is None:
            return False

        if timezone.now() > self.due:
            return True

    def max_score(self):
        """
        Return current max possible score
        """
        return self.raw_possible

    @staticmethod
    def workbench_scenarios():
        """
        A canned scenario for display in the workbench.
        """
        return [
            ("WeBWorKXBlock",
             """<webwork/>
             """),
            ("Multiple WeBWorKXBlock",
             """<vertical_demo>
                <webwork/>
                <webwork/>
                <webwork/>
                </vertical_demo>
             """),
        ]
