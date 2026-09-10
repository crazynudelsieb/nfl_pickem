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


def _username_taken(value, exclude=None):
    """True if some other account already holds this username, ignoring case."""
    from app import db

    folded = (value or "").strip().lower()
    if not folded:
        return False
    query = User.query.filter(db.func.lower(User.username) == folded)
    if exclude is not None:
        query = query.filter(db.func.lower(User.username) != exclude.strip().lower())
    return query.first() is not None


def _email_taken(value, exclude=None):
    """True if some other account already holds this email, ignoring case."""
    from app import db

    folded = (value or "").strip().lower()
    if not folded:
        return False
    query = User.query.filter(db.func.lower(User.email) == folded)
    if exclude is not None:
        query = query.filter(db.func.lower(User.email) != exclude.strip().lower())
    return query.first() is not None


class LoginForm(FlaskForm):
    # Named "username" because that is the column it usually matches, but the
    # field takes an email address too - see User.find_by_login_identifier.
    # The cap follows the email column (120), not the username column (80), or
    # a long address would be rejected before it ever reached the lookup.
    username = StringField(
        "Username or Email", validators=[DataRequired(), Length(min=3, max=120)]
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
        # Case-insensitive: sign-in folds case, so two names differing only in
        # case would make the lookup ambiguous.
        if _username_taken(username.data):
            raise ValidationError(
                "Username already exists. Please choose a different username."
            )

    def validate_email(self, email):
        if _email_taken(email.data):
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
        if username.data != self.original_username and _username_taken(
            username.data, exclude=self.original_username
        ):
            raise ValidationError(
                "Username already taken. Please choose a different username."
            )

    def validate_email(self, email):
        if email.data != self.original_email and _email_taken(
            email.data, exclude=self.original_email
        ):
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
