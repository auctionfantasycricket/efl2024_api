import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from bson import ObjectId
from dotenv import load_dotenv
from flask import Blueprint
from config import db

load_dotenv()

# Environment setup
sender_email = "saksharhere@gmail.com"
app_password = os.getenv('GMAIL_APP_PW')  # Your Gmail app password

send_email_bp = Blueprint('send_email', __name__)

def get_emails():
    try:
        teams = db.teams.find({"leagueId": ObjectId('67da30b26a17f44a19c2241a')})
        email_list = []
        for team in teams:
            current_waiver = team.get('currentWaiver', {})
            if 'lastUpdatedBy' not in current_waiver:
                team_id = team['_id']
                user_teams = db.userteams.find({"teamId": team_id})
                user_ids = [user_team['userId'] for user_team in user_teams]
                for user_id in user_ids:
                    user = db.users.find_one({"_id": user_id})
                    if user:
                        email_list.append(user['email'])
        return email_list
    except Exception as e:
        print("❌ Failed to get emails:", e)
        return []


def send_email(subject, text_body, html_body, to_list):
    message = MIMEMultipart("alternative")
    message["Subject"] = subject
    message["From"] = sender_email
    message["To"] = sender_email  # This avoids "no To header" spam flag
    message["Reply-To"] = sender_email

    part1 = MIMEText(text_body, "plain")
    part2 = MIMEText(html_body, "html")
    message.attach(part1)
    message.attach(part2)

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(sender_email, app_password)
            server.sendmail(sender_email, to_list, message.as_string())  # BCC list only here
        print("✅ Email sent successfully!")
    except Exception as e:
        print("❌ Failed to send email:", e)


# Email content
subject = "Reminder: Save your waivers by Tuesday 10pm PST"

text_body = (
    "Hi there,\n\n"
    "Today is waiver day and your team hasn't saved waivers yet.\n"
    "Please save them at https://www.auctionfantasycricket.com/#/teamhub\n"
    "Make sure 'Draft League' is selected.\n\n"
    "Thanks,\nFantasy Cricket Team"
)

html_body = """
    <h2>Waiver Reminder</h2>
    <p>Hi there,</p>
    <p>Today is waiver day and your team hasn't saved waivers yet.</p>
    <p>
        <a href='https://www.auctionfantasycricket.com/#/teamhub'>Click here to open Team Hub</a><br>
        (Make sure 'Draft League' is selected)
    </p>
    <p>Thanks,<br>Fantasy Cricket Team</p>
"""

# Send the email
send_email(
    subject=subject,
    text_body=text_body,
    html_body=html_body,
    to_list=get_emails()
)
