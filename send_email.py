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


def get_team_member_emails(team_id):
    try:
        user_teams = db.userteams.find({"teamId": ObjectId(team_id)})
        user_ids = [ut["userId"] for ut in user_teams]
        return [u["email"] for u in db.users.find({"_id": {"$in": user_ids}}) if u.get("email")]
    except Exception as e:
        print("❌ Failed to get team member emails:", e)
        return []


def notify_waiver_saved(team_id, team_name, updated_by, timestamp, released_players):
    to_list = get_team_member_emails(team_id)
    if not to_list:
        print("⚠️ No emails found for team:", team_name)
        return

    players_text = "\n".join(f"- {p}" for p in released_players if p)
    players_html = "".join(f"<li style='margin-bottom:4px'>{p}</li>" for p in released_players if p)

    subject = f"[{team_name}] Release preferences saved"

    text_body = (
        f"Hi,\n\n"
        f"{updated_by} saved {team_name}'s release preferences on {timestamp} PST.\n\n"
        f"Players selected to release:\n{players_text}\n\n"
        f"Visit Team Hub to review:\nhttps://www.auctionfantasycricket.com/#/teamhub\n\n"
        f"Thanks,\nAuction Fantasy Cricket Team"
    )

    html_body = f"""
<div style="font-family: Arial, sans-serif; max-width: 500px; margin: 0 auto; padding: 20px;">
  <h2 style="color: #1a1a2e;">🏏 Release Preferences Saved</h2>
  <p>Hi,</p>
  <p><strong>{updated_by}</strong> saved <strong>{team_name}</strong>'s release preferences on <strong>{timestamp} PST</strong>.</p>
  <h3 style="color: #444;">Players Selected to Release:</h3>
  <ul>{players_html}</ul>
  <a href="https://www.auctionfantasycricket.com/#/teamhub"
     style="display:inline-block; margin-top:12px; padding:10px 20px; background:#1890ff; color:white; text-decoration:none; border-radius:4px;">
    View Team Hub
  </a>
  <p style="margin-top:20px; font-size:12px; color:#999;">Auction Fantasy Cricket Team</p>
</div>
"""
    send_email(subject, text_body, html_body, to_list)


def notify_draft_waiver_saved(team_id, team_name, updated_by, timestamp, pairs):
    to_list = get_team_member_emails(team_id)
    if not to_list:
        print("⚠️ No emails found for team:", team_name)
        return

    # pairs is a list of (pick, drop) tuples
    text_rows = "\n".join(
        f"  {i+1}. Pick: {pick or '—'}  |  Drop: {drop or '—'}"
        for i, (pick, drop) in enumerate(pairs)
    )
    html_rows = "".join(
        f"""<tr>
          <td style='padding:6px 12px;border:1px solid #ddd;text-align:center'>{i+1}</td>
          <td style='padding:6px 12px;border:1px solid #ddd;color:#1a7f37'>{pick or '—'}</td>
          <td style='padding:6px 12px;border:1px solid #ddd;color:#cf1322'>{drop or '—'}</td>
        </tr>"""
        for i, (pick, drop) in enumerate(pairs)
    )

    subject = f"[{team_name}] Waiver preferences saved"

    text_body = (
        f"Hi,\n\n"
        f"{updated_by} saved {team_name}'s waiver preferences on {timestamp} PST.\n\n"
        f"Saved pairs:\n{text_rows}\n\n"
        f"Visit Team Hub to review:\nhttps://www.auctionfantasycricket.com/#/teamhub\n\n"
        f"Thanks,\nAuction Fantasy Cricket Team"
    )

    html_body = f"""
<div style="font-family: Arial, sans-serif; max-width: 560px; margin: 0 auto; padding: 20px;">
  <h2 style="color: #1a1a2e;">🏏 Waiver Preferences Saved</h2>
  <p>Hi,</p>
  <p><strong>{updated_by}</strong> saved <strong>{team_name}</strong>'s waiver preferences on <strong>{timestamp} PST</strong>.</p>
  <table style="border-collapse:collapse; width:100%; margin-top:12px;">
    <thead>
      <tr style="background:#f0f0f0;">
        <th style="padding:6px 12px;border:1px solid #ddd;">#</th>
        <th style="padding:6px 12px;border:1px solid #ddd;">Pick (IN)</th>
        <th style="padding:6px 12px;border:1px solid #ddd;">Drop (OUT)</th>
      </tr>
    </thead>
    <tbody>{html_rows}</tbody>
  </table>
  <a href="https://www.auctionfantasycricket.com/#/teamhub"
     style="display:inline-block; margin-top:16px; padding:10px 20px; background:#1890ff; color:white; text-decoration:none; border-radius:4px;">
    View Team Hub
  </a>
  <p style="margin-top:20px; font-size:12px; color:#999;">Auction Fantasy Cricket Team</p>
</div>
"""
    send_email(subject, text_body, html_body, to_list)


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
