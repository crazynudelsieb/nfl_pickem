from flask_wtf import FlaskForm
from wtforms import SelectField, SubmitField
from wtforms.validators import DataRequired


class MakePickForm(FlaskForm):
    selected_team = SelectField("Select Team", validators=[DataRequired()], coerce=int)
    submit = SubmitField("Make Pick")
