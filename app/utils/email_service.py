"""
Email Service for NFL Pick'em Application

This module handles all email-related functionality including:
- User registration emails
- Password reset emails
- Group invitations
- Weekly reminders
- Score notifications
"""

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from flask import current_app

logger = logging.getLogger(__name__)


class EmailService:
    """Handles all email sending functionality"""

    def __init__(self):
        self.smtp_server = current_app.config.get("MAIL_SERVER", "localhost")
        self.smtp_port = current_app.config.get("MAIL_PORT", 587)
        self.smtp_username = current_app.config.get("MAIL_USERNAME")
        self.smtp_password = current_app.config.get("MAIL_PASSWORD")
        self.from_email = current_app.config.get(
            "FROM_EMAIL"
        ) or current_app.config.get("MAIL_USERNAME", "noreply@nflpickem.com")
        self.from_name = current_app.config.get("FROM_NAME", "NFL Pick'em")
        self.use_tls = current_app.config.get("MAIL_USE_TLS", True)

    def _create_message(self, to_email, subject, body_text, body_html=None):
        """Create email message"""
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"{self.from_name} <{self.from_email}>"
        msg["To"] = to_email

        # Add text part
        part1 = MIMEText(body_text, "plain")
        msg.attach(part1)

        # Add HTML part if provided
        if body_html:
            part2 = MIMEText(body_html, "html")
            msg.attach(part2)

        return msg

    def _send_email(self, message):
        """Send email message"""
        try:
            if not self.smtp_username or not self.smtp_password:
                logger.warning("SMTP credentials not configured. Email not sent.")
                return False

            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                if self.use_tls:
                    server.starttls()
                server.login(self.smtp_username, self.smtp_password)

                text = message.as_string()
                server.sendmail(self.from_email, [message["To"]], text)

            logger.info(f"Email sent successfully to {message['To']}")
            return True

        except Exception as e:
            logger.error(f"Failed to send email to {message['To']}: {str(e)}")
            return False

    def send_welcome_email(self, user):
        """Send welcome email to new user"""
        subject = f"Welcome to {self.from_name}!"

        body_text = f"""
        Hi {user.full_name},

        Welcome to NFL Pick'em! Your account has been created successfully.

        Username: {user.username}
        Email: {user.email}

        You can now log in and start making your NFL picks!

        Best regards,
        The NFL Pick'em Team
        """

        body_html = f"""
        <html>
        <body>
            <h2>Welcome to {self.from_name}!</h2>
            <p>Hi {user.full_name},</p>
            <p>Welcome to NFL Pick'em! Your account has been created successfully.</p>

            <ul>
                <li><strong>Username:</strong> {user.username}</li>
                <li><strong>Email:</strong> {user.email}</li>
            </ul>

            <p>You can now log in and start making your NFL picks!</p>

            <p>Best regards,<br>
            The NFL Pick'em Team</p>
        </body>
        </html>
        """

        message = self._create_message(user.email, subject, body_text, body_html)
        return self._send_email(message)

    def send_password_reset_email(self, user, reset_token):
        """Send password reset email"""
        from flask import url_for

        reset_url = url_for("auth.reset_password", token=reset_token, _external=True)

        subject = "Password Reset - NFL Pick'em"

        body_text = f"""
        Hi {user.full_name},

        You requested a password reset for your NFL Pick'em account.

        Click the link below to reset your password:
        {reset_url}

        This link will expire in 1 hour.

        If you didn't request this reset, please ignore this email.

        Best regards,
        The NFL Pick'em Team
        """

        body_html = f"""
        <html>
        <body>
            <h2>Password Reset</h2>
            <p>Hi {user.full_name},</p>
            <p>You requested a password reset for your NFL Pick'em account.</p>

            <p><a href="{reset_url}" style="background-color: #007bff; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px;">Reset Password</a></p>

            <p>Or copy and paste this link: <br><a href="{reset_url}">{reset_url}</a></p>

            <p><small>This link will expire in 1 hour.</small></p>

            <p>If you didn't request this reset, please ignore this email.</p>

            <p>Best regards,<br>
            The NFL Pick'em Team</p>
        </body>
        </html>
        """

        message = self._create_message(user.email, subject, body_text, body_html)
        return self._send_email(message)

    def send_group_invitation(self, invite, inviter):
        """Send group invitation email"""
        from flask import url_for

        join_url = url_for("groups.join_by_token", token=invite.token, _external=True)

        subject = f"You're invited to join '{invite.group.name}' - NFL Pick'em"

        body_text = f"""
        Hi there,

        {inviter.full_name} has invited you to join their NFL Pick'em group: "{invite.group.name}"

        {invite.group.description if invite.group.description else "Join us for some friendly NFL prediction competition!"}

        GROUP CODE: {invite.group.invite_code}

        Click the link below to accept the invitation:
        {join_url}

        Or manually enter the group code: {invite.group.invite_code}

        If you don't have an account yet, you'll be able to create one when you accept the invitation.

        Best regards,
        The NFL Pick'em Team
        """

        body_html = f"""
        <html>
        <body>
            <h2>You're Invited!</h2>
            <p>Hi there,</p>
            <p><strong>{inviter.full_name}</strong> has invited you to join their NFL Pick'em group:</p>

            <div style="border: 1px solid #ddd; padding: 15px; margin: 15px 0; border-radius: 5px;">
                <h3>{invite.group.name}</h3>
                {f'<p>{invite.group.description}</p>' if invite.group.description else '<p>Join us for some friendly NFL prediction competition!</p>'}
            </div>

            <div style="background-color: #f8f9fa; border: 2px solid #007bff; padding: 15px; margin: 20px 0; border-radius: 5px; text-align: center;">
                <p style="margin: 0; color: #666; font-size: 14px;">GROUP CODE</p>
                <p style="margin: 10px 0; font-size: 24px; font-weight: bold; letter-spacing: 2px; color: #007bff;">{invite.group.invite_code}</p>
            </div>

            <p><a href="{join_url}" style="background-color: #28a745; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px;">Accept Invitation</a></p>

            <p style="color: #666; font-size: 14px;">Or copy this link: <br><span style="word-break: break-all;">{join_url}</span></p>

            <p style="color: #666; font-size: 14px;">You can also manually enter the group code <strong>{invite.group.invite_code}</strong> after logging in.</p>

            <p>If you don't have an account yet, you'll be able to create one when you accept the invitation.</p>

            <p>Best regards,<br>
            The NFL Pick'em Team</p>
        </body>
        </html>
        """

        message = self._create_message(
            invite.invitee_email, subject, body_text, body_html
        )
        return self._send_email(message)

    def send_weekly_reminder(self, user, week_games):
        """Send weekly picks reminder"""
        subject = "Don't forget your Week picks! - NFL Pick'em"

        games_list = "\n".join(
            [
                f"  • {game.away_team.name} @ {game.home_team.name} - {game.game_time.strftime('%a %m/%d %I:%M %p')}"
                for game in week_games[:5]  # Show first 5 games
            ]
        )

        if len(week_games) > 5:
            games_list += f"\n  ... and {len(week_games) - 5} more games"

        body_text = f"""
        Hi {user.full_name},

        Don't forget to make your picks for this week's NFL games!

        This week's games include:
        {games_list}

        Make your picks before the first game starts!

        Best regards,
        The NFL Pick'em Team
        """

        message = self._create_message(user.email, subject, body_text)
        return self._send_email(message)

    def send_weekly_results(self, user, week_results):
        """Send weekly results summary"""
        subject = "Your Week Results - NFL Pick'em"

        body_text = f"""
        Hi {user.full_name},

        Here are your results for this week:

        Correct Picks: {week_results['correct_picks']}/{week_results['total_picks']}
        Points Earned: {week_results['points']}
        Accuracy: {week_results['accuracy']:.1%}

        Keep up the great work!

        Best regards,
        The NFL Pick'em Team
        """

        message = self._create_message(user.email, subject, body_text)
        return self._send_email(message)

    def test_email_configuration(self):
        """Test email configuration"""
        try:
            if not self.smtp_username or not self.smtp_password:
                return False, "SMTP credentials not configured"

            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                if self.use_tls:
                    server.starttls()
                server.login(self.smtp_username, self.smtp_password)

            return True, "Email configuration is working"

        except Exception as e:
            return False, f"Email configuration error: {str(e)}"
