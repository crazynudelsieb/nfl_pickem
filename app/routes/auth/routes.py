import logging
from urllib.parse import urlparse

from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user
from flask_wtf.csrf import validate_csrf
from wtforms import ValidationError

from app import db, limiter, login_manager
from app.forms.auth import (
    ChangePasswordForm,
    EditProfileForm,
    LoginForm,
    RegistrationForm,
)
from app.models import Season, User
from app.routes.auth import bp

logger = logging.getLogger(__name__)


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


@bp.route("/login", methods=["GET", "POST"])
@limiter.limit("10 per minute")
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()

        if user and user.check_password(form.password.data):
            if not user.is_active:
                flash(
                    "Your account has been deactivated. Please contact support.",
                    "error",
                )
                return render_template("auth/login.html", form=form)

            login_user(user, remember=form.remember_me.data)
            user.update_last_login()

            # Smart redirect logic based on user's groups
            next_page = request.args.get("next")
            if not next_page or urlparse(next_page).netloc != "":
                user_groups = user.get_groups()

                if not user_groups:
                    # No groups - redirect to groups page to join/create
                    next_page = url_for("groups.index")
                elif len(user_groups) == 1:
                    # Only one group - redirect directly to picks
                    next_page = url_for("main.current_picks")
                else:
                    # Multiple groups - go to dashboard for group selection
                    next_page = url_for("main.dashboard")

            flash(f"Welcome back, {user.full_name}!", "success")
            return redirect(next_page)

        flash("Invalid username or password.", "error")

    return render_template("auth/login.html", form=form)


@bp.route("/register", methods=["GET", "POST"])
@limiter.limit("5 per hour")
def register():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    form = RegistrationForm()
    if form.validate_on_submit():
        # Create new user (form validators already checked for duplicates)
        user = User(
            username=form.username.data,
            email=form.email.data,
            display_name=form.display_name.data,
            avatar_url=User.generate_avatar_url(
                form.username.data
            ),  # Generate avatar based on username
        )
        user.set_password(form.password.data)

        db.session.add(user)
        db.session.commit()

        flash("Registration successful! Welcome to NFL Pick'em!", "success")
        login_user(user)

        # New users always start with no groups, so redirect to groups page
        return redirect(url_for("groups.index"))

    return render_template("auth/register.html", form=form)


@bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out successfully.", "info")
    return redirect(url_for("main.index"))


@bp.route("/profile")
@login_required
def profile():
    from app.models import SeasonWinner

    current_season = Season.get_current_season()
    season_stats = None
    if current_season:
        # Get overall stats (not filtered by group - all picks across all groups)
        season_stats = current_user.get_season_stats(current_season.id, group_id=None)

    # Get user's awards
    user_awards = SeasonWinner.get_user_awards(current_user.id)

    # Count championship types
    global_championships = len(
        [a for a in user_awards if a.award_type == "champion" and a.group_id is None]
    )
    group_championships = len(
        [
            a
            for a in user_awards
            if a.award_type == "champion" and a.group_id is not None
        ]
    )

    # Get all-time statistics across all seasons
    from app.models import Game, Pick

    all_picks = Pick.query.filter_by(user_id=current_user.id).all()
    all_completed_picks = [p for p in all_picks if p.is_correct is not None]
    all_wins = sum(1 for p in all_completed_picks if p.is_correct)
    all_losses = sum(1 for p in all_completed_picks if not p.is_correct)

    # Count missed games across all seasons
    # Note: Game.status is calculated in Python, so we check all games
    # This count is used for overall stats tracking

    # Get unique weeks with completed games that user missed
    picked_game_ids = {p.game_id for p in all_picks}
    # NOTE: Must use is_final column, not status property (status is @property, can't filter)
    completed_game_ids = {
        g.id for g in Game.query.filter(Game.is_final == True).all()
    }
    missed_game_ids = completed_game_ids - picked_game_ids
    all_missed_games = len(missed_game_ids)

    # Calculate all-time accuracy (includes missed games as losses)
    all_time_accuracy_denominator = len(all_completed_picks) + all_missed_games
    all_time_accuracy = (
        (all_wins / all_time_accuracy_denominator * 100)
        if all_time_accuracy_denominator > 0
        else 0
    )

    # Calculate all-time longest streak
    all_time_longest_streak = current_user.calculate_alltime_longest_streak()

    all_time_stats = {
        "total_picks": len(all_picks),
        "wins": all_wins,
        "losses": all_losses,
        "missed_games": all_missed_games,
        "completed_picks": len(all_completed_picks),
        "accuracy": all_time_accuracy,
        "tiebreaker_points": sum(p.tiebreaker_points or 0 for p in all_completed_picks),
        "longest_streak": all_time_longest_streak,
    }

    return render_template(
        "auth/profile.html",
        user=current_user,
        current_season=current_season,
        season_stats=season_stats,
        all_time_stats=all_time_stats,
        user_awards=user_awards,
        global_championships=global_championships,
        group_championships=group_championships,
    )


@bp.route("/profile/edit", methods=["GET", "POST"])
@login_required
def edit_profile():

    form = EditProfileForm(
        original_username=current_user.username,
        original_email=current_user.email,
        obj=current_user,
    )
    if form.validate_on_submit():
        # Update user information (form validators already checked for duplicates)
        current_user.username = form.username.data
        current_user.email = form.email.data
        current_user.display_name = form.display_name.data

        db.session.commit()
        flash("Profile updated successfully!", "success")
        return redirect(url_for("auth.profile"))

    return render_template("auth/edit_profile.html", form=form)


@bp.route("/profile/regenerate-avatar", methods=["POST"])
@login_required
def regenerate_avatar():
    """Generate a new random avatar for the current user"""
    from flask import jsonify
    
    # Generate new avatar URL with random seed
    new_avatar_url = User.generate_avatar_url()
    current_user.avatar_url = new_avatar_url
    
    db.session.commit()
    
    flash("New profile picture generated!", "success")
    
    # Return JSON for AJAX or redirect for regular form
    if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({
            'success': True,
            'avatar_url': new_avatar_url
        })
    
    return redirect(url_for("auth.edit_profile"))


@bp.route("/change-password", methods=["GET", "POST"])
@login_required
def change_password():

    form = ChangePasswordForm()
    if form.validate_on_submit():
        if not current_user.check_password(form.current_password.data):
            flash("Current password is incorrect.", "error")
            return render_template("auth/change_password.html", form=form)

        current_user.set_password(form.new_password.data)
        db.session.commit()

        flash("Password changed successfully!", "success")
        return redirect(url_for("auth.profile"))

    return render_template("auth/change_password.html", form=form)


@bp.route("/forgot_password", methods=["GET", "POST"])
@limiter.limit("20 per hour")
def forgot_password():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    if request.method == "POST":
        email = request.form.get("email")
        if email:
            user = User.query.filter_by(email=email).first()
            if user:
                # Generate reset token
                token = user.generate_reset_token()
                db.session.commit()

                # Send reset email
                try:
                    from app.utils.email_service import EmailService

                    email_service = EmailService()
                    email_sent = email_service.send_password_reset_email(user, token)

                    if not email_sent:
                        logger.warning(
                            f"Failed to send password reset email to {user.email}"
                        )
                except Exception as e:
                    logger.error(f"Error sending password reset email: {str(e)}")

            # Always show the same message for security (don't reveal if email exists)
            flash(
                "If an account with that email exists, password reset instructions have been sent.",
                "info",
            )
        return redirect(url_for("auth.login"))

    return render_template("auth/forgot_password.html")


@bp.route("/reset_password/<token>", methods=["GET", "POST"])
@limiter.limit("30 per hour")
def reset_password(token):
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    user = User.verify_reset_token(token)
    if not user:
        flash("Invalid or expired password reset link.", "error")
        return redirect(url_for("auth.forgot_password"))

    if request.method == "POST":
        # Validate CSRF token
        try:
            validate_csrf(request.form.get('csrf_token'))
        except ValidationError:
            flash("Security validation failed. Please try again.", "error")
            return render_template("auth/reset_password.html", token=token)

        password = request.form.get("password")
        confirm_password = request.form.get("confirm_password")

        if not password or not confirm_password:
            flash("Please provide both password fields.", "error")
            return render_template("auth/reset_password.html", token=token)

        if password != confirm_password:
            flash("Passwords do not match.", "error")
            return render_template("auth/reset_password.html", token=token)

        if len(password) < 8:
            flash("Password must be at least 8 characters long.", "error")
            return render_template("auth/reset_password.html", token=token)

        # Update password and clear token
        user.set_password(password)
        user.clear_reset_token()
        db.session.commit()

        flash(
            "Your password has been reset successfully. Please log in with your new password.",
            "success",
        )
        return redirect(url_for("auth.login"))

    return render_template("auth/reset_password.html", token=token)
