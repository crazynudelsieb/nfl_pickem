import html

from flask_wtf import FlaskForm
from wtforms import (
    BooleanField,
    IntegerField,
    SelectField,
    StringField,
    SubmitField,
    TextAreaField,
)
from wtforms.validators import DataRequired, Email, Length, NumberRange, Regexp


def sanitize_input(text):
    """Sanitize user input to prevent XSS"""
    if not text:
        return text
    return html.escape(text.strip())


class CreateGroupForm(FlaskForm):
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


class EditGroupForm(FlaskForm):
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
