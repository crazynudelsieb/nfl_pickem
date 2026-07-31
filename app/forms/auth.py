from flask_wtf import FlaskForm
from wtforms import BooleanField, PasswordField, StringField, SubmitField
from wtforms.validators import (
    DataRequired,
    Email,
    EqualTo,
    Length,
    Regexp,
    ValidationError,
)

from app.models.user import User

# Names reach the browser through HTML data attributes that client code reads
# back with getAttribute(), which returns the decoded value - template escaping
# does not protect that path. Restricting the character set at the door does.
# Every form that writes a name must apply these, not just registration.
USERNAME_PATTERN = r"^[a-zA-Z0-9_.-]+$"
DISPLAY_NAME_PATTERN = r"^[a-zA-Z0-9 _.-]*$"


class LoginForm(FlaskForm):
    username = StringField(
        "Username", validators=[DataRequired(), Length(min=3, max=80)]
    )
    password = PasswordField("Password", validators=[DataRequired()])
    remember_me = BooleanField("Remember Me")
    submit = SubmitField("Sign In")


class RegistrationForm(FlaskForm):
    username = StringField(
        "Username",
        validators=[
            DataRequired(),
            Length(
                min=3, max=80, message="Username must be between 3 and 80 characters"
            ),
            Regexp(
                USERNAME_PATTERN,
                message="Username can only contain letters, numbers, dots, underscores, and hyphens",
            ),
        ],
    )
    email = StringField("Email", validators=[DataRequired(), Email()])
    display_name = StringField(
        "Display Name (Optional)",
        validators=[
            Length(max=100),
            Regexp(
                DISPLAY_NAME_PATTERN,
                message="Display name contains invalid characters",
            ),
        ],
    )
    password = PasswordField(
        "Password",
        validators=[
            DataRequired(),
            Length(min=8, message="Password must be at least 8 characters long"),
            Regexp(
                r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d).*$",
                message="Password must contain at least one uppercase letter, one lowercase letter, and one number",
            ),
        ],
    )
    password_confirm = PasswordField(
        "Confirm Password",
        validators=[
            DataRequired(),
            EqualTo("password", message="Passwords must match"),
        ],
    )
    submit = SubmitField("Register")

    def validate_username(self, username):
        user = User.query.filter_by(username=username.data).first()
        if user:
            raise ValidationError(
                "Username already exists. Please choose a different username."
            )

    def validate_email(self, email):
        user = User.query.filter_by(email=email.data).first()
        if user:
            raise ValidationError(
                "Email already registered. Please use a different email."
            )


class EditProfileForm(FlaskForm):
    # Same character restrictions as RegistrationForm. Without them a user
    # could register with a clean name and then edit it to markup: the
    # leaderboard passes the username to the browser through a data attribute,
    # and getAttribute() hands back the decoded value, so Jinja's escaping does
    # not survive the round trip.
    username = StringField(
        "Username",
        validators=[
            DataRequired(),
            Length(min=3, max=80),
            Regexp(
                USERNAME_PATTERN,
                message="Username can only contain letters, numbers, dots, underscores, and hyphens",
            ),
        ],
    )
    email = StringField("Email", validators=[DataRequired(), Email()])
    display_name = StringField(
        "Display Name (Optional)",
        validators=[
            Length(max=100),
            Regexp(
                DISPLAY_NAME_PATTERN,
                message="Display name contains invalid characters",
            ),
        ],
    )
    submit = SubmitField("Update Profile")

    def __init__(self, original_username, original_email, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.original_username = original_username
        self.original_email = original_email

    def validate_username(self, username):
        if username.data != self.original_username:
            user = User.query.filter_by(username=username.data).first()
            if user:
                raise ValidationError(
                    "Username already taken. Please choose a different username."
                )

    def validate_email(self, email):
        if email.data != self.original_email:
            user = User.query.filter_by(email=email.data).first()
            if user:
                raise ValidationError(
                    "Email already registered. Please use a different email."
                )


class ChangePasswordForm(FlaskForm):
    current_password = PasswordField("Current Password", validators=[DataRequired()])
    new_password = PasswordField(
        "New Password",
        validators=[
            DataRequired(),
            Length(min=8, message="Password must be at least 8 characters long"),
            Regexp(
                r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d).*$",
                message="Password must contain at least one uppercase letter, one lowercase letter, and one number",
            ),
        ],
    )
    confirm_password = PasswordField(
        "Confirm New Password",
        validators=[
            DataRequired(),
            EqualTo("new_password", message="Passwords must match"),
        ],
    )
    submit = SubmitField("Change Password")
