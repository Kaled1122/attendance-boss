import os
from flask import Flask, request, render_template, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, time, timezone
from apscheduler.schedulers.background import BackgroundScheduler
import smtplib
from email.mime.text import MIMEText
from dotenv import load_dotenv

# ------------------------------------------------------------
# LOAD ENVIRONMENT VARIABLES
# ------------------------------------------------------------
load_dotenv()

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)

EMAIL_SENDER = os.getenv("EMAIL_SENDER")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
RECIPIENTS = [
    x.strip() for x in os.getenv("EMAIL_RECIPIENTS", "").split(",") if x.strip()
]

# ------------------------------------------------------------
# DATABASE MODEL
# ------------------------------------------------------------
class Attendance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    staff_name = db.Column(db.String(100), nullable=False)
    check_in = db.Column(db.DateTime)
    check_out = db.Column(db.DateTime)
    status = db.Column(db.String(100))
    # Use timezone-aware UTC datetime
    date = db.Column(db.Date, default=lambda: datetime.now(timezone.utc).date())

# ------------------------------------------------------------
# EMAIL UTILITY
# ------------------------------------------------------------
def send_email(subject, body):
    if not EMAIL_SENDER or not EMAIL_PASSWORD:
        print("⚠️ Email not configured properly")
        return

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = EMAIL_SENDER
    msg["To"] = ", ".join(RECIPIENTS)

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(EMAIL_SENDER, EMAIL_PASSWORD)
            server.send_message(msg)
        print(f"✅ Email sent: {subject}")
    except Exception as e:
        print(f"❌ Failed to send email: {e}")

# ------------------------------------------------------------
# HELPER FUNCTIONS
# ------------------------------------------------------------
def get_today_records():
    return Attendance.query.filter_by(date=datetime.now(timezone.utc).date()).all()

def generate_report_text(records, flag):
    lines = []
    for r in records:
        if flag == "morning" and "Late" in (r.status or ""):
            lines.append(f"{r.staff_name} – signed in at {r.check_in.strftime('%H:%M')}")
        if flag == "afternoon" and "Left Early" in (r.status or ""):
            lines.append(f"{r.staff_name} – signed out at {r.check_out.strftime('%H:%M')}")
    return "\n".join(lines) or "No issues so far ✅"

# ------------------------------------------------------------
# ROUTES
# ------------------------------------------------------------
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/sign_in", methods=["POST"])
def sign_in():
    name = request.form["name"].strip().title()
    now = datetime.now(timezone.utc)
    cutoff = time(6, 15)
    status = "On Time" if now.time() <= cutoff else "Late"

    record = Attendance(staff_name=name, check_in=now, status=status)
    db.session.add(record)
    db.session.commit()
    return f"{name} signed in at {now.strftime('%H:%M:%S')} ({status})"

@app.route("/sign_out", methods=["POST"])
def sign_out():
    name = request.form["name"].strip().title()
    now = datetime.now(timezone.utc)
    cutoff = time(12, 45)
    record = Attendance.query.filter_by(
        staff_name=name, date=datetime.now(timezone.utc).date()
    ).first()

    if not record:
        return "⚠️ No sign-in found for today."

    record.check_out = now
    if now.time() < cutoff:
        record.status = f"{record.status}, Left Early"
    elif "Late" not in record.status:
        record.status = "On Time"
    db.session.commit()

    return f"{name} signed out at {now.strftime('%H:%M:%S')} ({record.status})"

@app.route("/report")
def report():
    records = get_today_records()
    return render_template("report.html", records=records)

@app.route("/api/report")
def api_report():
    records = get_today_records()
    return jsonify([
        {
            "name": r.staff_name,
            "check_in": r.check_in.strftime("%H:%M") if r.check_in else "-",
            "check_out": r.check_out.strftime("%H:%M") if r.check_out else "-",
            "status": r.status,
        }
        for r in records
    ])

# ------------------------------------------------------------
# TEST EMAIL ROUTE
# ------------------------------------------------------------
@app.route("/test_email")
def test_email():
    subject = "✅ Attendance System Email Test"
    body = (
        "This is a test email from your Flask Attendance System.\n\n"
        "If you received this message, Gmail integration works correctly."
    )
    try:
        send_email(subject, body)
        return "✅ Test email sent successfully! Check your Gmail inbox."
    except Exception as e:
        return f"❌ Failed to send email: {e}"

# ------------------------------------------------------------
# AUTOMATIC DAILY EMAIL JOBS
# ------------------------------------------------------------
scheduler = BackgroundScheduler()

@scheduler.scheduled_job("cron", hour=6, minute=20)
def morning_report():
    records = get_today_records()
    body = generate_report_text(records, "morning")
    send_email("⏰ Morning Attendance Report (6:20 AM)", body)

@scheduler.scheduled_job("cron", hour=12, minute=50)
def afternoon_report():
    records = get_today_records()
    body = generate_report_text(records, "afternoon")
    send_email("🏁 Afternoon Departure Report (12:50 PM)", body)

scheduler.start()

# ------------------------------------------------------------
# MAIN ENTRY POINT
# ------------------------------------------------------------
if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    # Production-ready entry; disable debug in production
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
