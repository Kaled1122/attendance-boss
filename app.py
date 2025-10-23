import os
from flask import Flask, request, jsonify, render_template
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, time
from apscheduler.schedulers.background import BackgroundScheduler
import smtplib
from email.mime.text import MIMEText
from dotenv import load_dotenv

# -------------------------------
# ENVIRONMENT SETUP
# -------------------------------
load_dotenv()
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

ADMIN_EMAIL = os.getenv("ADMIN_EMAIL")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")  # App password (not Gmail login)

# -------------------------------
# DATABASE MODEL
# -------------------------------
class Attendance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    staff_name = db.Column(db.String(100), nullable=False)
    check_in = db.Column(db.DateTime)
    check_out = db.Column(db.DateTime)
    status = db.Column(db.String(50))
    date = db.Column(db.Date, default=datetime.utcnow().date())

# -------------------------------
# EMAIL FUNCTION
# -------------------------------
def send_email(subject, body):
    msg = MIMEText(body, "plain")
    msg["Subject"] = subject
    msg["From"] = ADMIN_EMAIL
    msg["To"] = ADMIN_EMAIL

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(ADMIN_EMAIL, EMAIL_PASSWORD)
        server.send_message(msg)
    print(f"✅ Email sent: {subject}")

# -------------------------------
# ATTENDANCE ROUTES
# -------------------------------
@app.route('/')
def home():
    return render_template('index.html')

@app.route('/sign_in', methods=['POST'])
def sign_in():
    name = request.form['name']
    now = datetime.now()
    cutoff = time(6, 15)
    status = "On Time" if now.time() <= cutoff else "Late"

    record = Attendance(staff_name=name, check_in=now, status=status)
    db.session.add(record)
    db.session.commit()
    return f"{name} signed in at {now.strftime('%H:%M:%S')} ({status})"

@app.route('/sign_out', methods=['POST'])
def sign_out():
    name = request.form['name']
    now = datetime.now()
    cutoff = time(12, 45)
    record = Attendance.query.filter_by(staff_name=name, date=datetime.utcnow().date()).first()

    if not record:
        return "No sign-in record found for today."

    record.check_out = now
    if now.time() < cutoff:
        record.status = f"{record.status}, Left Early"
    else:
        if "Late" not in record.status:
            record.status = "On Time"
    db.session.commit()
    return f"{name} signed out at {now.strftime('%H:%M:%S')} ({record.status})"

# -------------------------------
# DAILY REPORT FUNCTIONS
# -------------------------------
def morning_report():
    today = datetime.utcnow().date()
    cutoff = datetime.combine(today, time(6, 15))
    late_staff = Attendance.query.filter(Attendance.check_in > cutoff).all()
    not_signed_in = []  # (optional) if you maintain staff list

    if not late_staff:
        body = "All staff have checked in on time."
    else:
        body = "Late arrivals:\n" + "\n".join([f"- {x.staff_name} at {x.check_in.strftime('%H:%M:%S')}" for x in late_staff])
    send_email("6:20 AM Late Arrival Report", body)

def afternoon_report():
    today = datetime.utcnow().date()
    cutoff = datetime.combine(today, time(12, 45))
    early_leavers = Attendance.query.filter(Attendance.check_out != None, Attendance.check_out < cutoff).all()

    if not early_leavers:
        body = "No one left early today."
    else:
        body = "Early leavers:\n" + "\n".join([f"- {x.staff_name} at {x.check_out.strftime('%H:%M:%S')}" for x in early_leavers])
    send_email("12:50 PM Early Leave Report", body)

# -------------------------------
# SCHEDULER (RUNS TWICE DAILY)
# -------------------------------
scheduler = BackgroundScheduler()
scheduler.add_job(morning_report, "cron", hour=6, minute=20)
scheduler.add_job(afternoon_report, "cron", hour=12, minute=50)
scheduler.start()

# -------------------------------
# RUN APP
# -------------------------------
if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True)
