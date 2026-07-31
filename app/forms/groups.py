from flask_wtf import FlaskForm
from wtforms import (
    BooleanField,
    IntegerField,
    SelectField,
    StringField,
    SubmitField,
    TextAreaField,
)
from wtforms.validators import (
    DataRequired,
    Email,
    Length,
    NumberRange,
    Regexp,
    ValidationError,
)


class GroupRulesMixin:
    """Pick rule settings shared by the create and edit group forms"""

    pick_team_once = BooleanField(
        "Each team can only be picked once during the regular season",
        default=True,
    )
    no_repeat_opponent = BooleanField(
        "No picking against the same opponent two weeks in a row",
        default=True,
    )
    playoff_spots = IntegerField(
        "Playoff Spots",
        validators=[
            DataRequired(),
            NumberRange(min=2, max=10, message="Playoff spots must be between 2 and 10"),
        ],
        default=4,
        description="Top N players qualify for the playoffs",
    )
    superbowl_spots = IntegerField(
        "Super Bowl Spots",
        validators=[
            DataRequired(),
            NumberRange(min=2, max=4, message="Super Bowl spots must be between 2 and 4"),
        ],
        default=2,
        description="Top N playoff players qualify for the Super Bowl",
    )

    def validate_superbowl_spots(self, field):
        if self.playoff_spots.data and field.data and field.data > self.playoff_spots.data:
            raise ValidationError("Super Bowl spots cannot exceed playoff spots")


class CreateGroupForm(GroupRulesMixin, FlaskForm):
    name = StringField(
        "Group Name",
        validators=[
            DataRequired(),
            Length(
                min=3,
                max=100,
                message="Group name must be between 3 and 100 characters",
            ),
            Regexp(
                r"^[a-zA-Z0-9 _.-]+$", message="Group name contains invalid characters"
            ),
        ],
    )
    description = TextAreaField(
        "Description",
        validators=[
            Length(max=500, message="Description cannot exceed 500 characters")
        ],
    )
    is_public = BooleanField("Make this group public", default=False)
    max_members = IntegerField(
        "Maximum Members",
        validators=[
            DataRequired(),
            NumberRange(
                min=2, max=100, message="Maximum members must be between 2 and 100"
            ),
        ],
        default=50,
    )
    submit = SubmitField("Create Group")


class EditGroupForm(GroupRulesMixin, FlaskForm):
    name = StringField(
        "Group Name", validators=[DataRequired(), Length(min=3, max=100)]
    )
    description = TextAreaField("Description", validators=[Length(max=500)])
    is_public = BooleanField("Make this group public")
    max_members = IntegerField(
        "Maximum Members", validators=[DataRequired(), NumberRange(min=2, max=100)]
    )
    submit = SubmitField("Update Group")


class InviteForm(FlaskForm):
    email = StringField(
        "Email Address",
        validators=[
            DataRequired(),
            Email(message="Please enter a valid email address"),
        ],
    )
    submit = SubmitField("Send Invitation")


class AdminPickForm(FlaskForm):
    user_id = SelectField("User", validators=[DataRequired()], coerce=int)
    week = SelectField("Week", validators=[DataRequired()], coerce=int)
    game_id = IntegerField("Game", validators=[DataRequired()])
    team_id = IntegerField("Team", validators=[DataRequired()])
    admin_override = BooleanField(
        "Admin Override",
        default=False,
        description="Check to bypass normal pick validation rules",
    )
    submit = SubmitField("Create/Update Pick")
