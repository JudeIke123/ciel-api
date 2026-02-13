import os
import re
import sqlite3
import smtplib
from typing import Optional
from datetime import datetime
from email.message import EmailMessage
from flask import Flask, request, jsonify
from flask_cors import CORS

DB_PATH = os.getenv("DB_PATH", "ciel.db")

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": ["https://cielprofs.com", "https://www.cielprofs.com"]}})

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = db()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS newsletter (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            email TEXT NOT NULL UNIQUE,
            interest TEXT,
            created_at TEXT NOT NULL
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS contact_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            phone TEXT,
            topic TEXT,
            message TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()
    
# ✅ Create tables on startup (Gunicorn/Render safe)
init_db()


@app.get("/health")
def health():
    return {"status": "ok", "time": datetime.utcnow().isoformat() + "Z"}
    
def send_email(to_email: str, subject: str, text_body: str, reply_to: Optional[str] = None):
    host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    port = int(os.getenv("SMTP_PORT", "587"))
    user = os.getenv("SMTP_USER")
    password = os.getenv("SMTP_PASS")

    if not user or not password:
        raise RuntimeError("SMTP_USER/SMTP_PASS not set in Render Environment Variables")

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = f"CIEL Professionals <{user}>"
    msg["To"] = to_email
    if reply_to:
        msg["Reply-To"] = reply_to
    msg.set_content(text_body)

    with smtplib.SMTP(host, port) as smtp:
        smtp.ehlo()
        smtp.starttls()
        smtp.login(user, password)
        smtp.send_message(msg)


@app.post("/api/newsletter")
def newsletter():
    payload = request.get_json(silent=True) or {}
    name = (payload.get("name") or "").strip()
    email = (payload.get("email") or "").strip().lower()
    interest = (payload.get("interest") or "").strip()

    if not email or not EMAIL_RE.match(email):
        return jsonify({"ok": False, "error": "Valid email is required"}), 400

    conn = db()
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO newsletter (name, email, interest, created_at) VALUES (?, ?, ?, ?)",
            (name, email, interest, datetime.utcnow().isoformat() + "Z"),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        # already subscribed
        return jsonify({"ok": True, "message": "Already subscribed"}), 200
    finally:
        conn.close()

    return jsonify({"ok": True, "message": "Subscribed"}), 201


@app.post("/api/contact")
def contact():
    payload = request.get_json(silent=True) or {}
    name = (payload.get("name") or "").strip()
    email = (payload.get("email") or "").strip().lower()
    phone = (payload.get("phone") or "").strip()
    topic = (payload.get("topic") or "").strip()
    message = (payload.get("message") or "").strip()

    if not name:
        return jsonify({"ok": False, "error": "Name is required"}), 400
    if not email or not EMAIL_RE.match(email):
        return jsonify({"ok": False, "error": "Valid email is required"}), 400
    if not message:
        return jsonify({"ok": False, "error": "Message is required"}), 400

    conn = db()
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO contact_messages (name, email, phone, topic, message, created_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (name, email, phone, topic, message, datetime.utcnow().isoformat() + "Z"),
    )
    conn.commit()
    conn.close()
    admin_email = os.getenv("ADMIN_EMAIL", "jesedebe@gmail.com")

    # Email admin
    try:
        subject = f"New Contact Message - {topic or 'General'}"
        body = (
            f"New message from cielprofs.com\n\n"
            f"Name: {name}\n"
            f"Email: {email}\n"
            f"Phone: {phone}\n"
            f"Topic: {topic}\n\n"
            f"Message:\n{message}\n\n"
            f"Time (UTC): {datetime.utcnow().isoformat()}Z\n"
        )
        send_email(admin_email, subject, body, reply_to=email)
        print("✅ Admin email sent to", admin_email)
    except Exception as e:
        print("❌ Admin email failed:", e)

    # Auto-reply user
    try:
        subject2 = "We received your message | CIEL Professionals"
        body2 = (
            f"Hi {name},\n\n"
            "Thanks for contacting CIEL Professionals. We have received your message and will respond shortly.\n\n"
            "Regards,\n"
            "CIEL Professionals\n"
            "https://cielprofs.com\n"
        )
        send_email(email, subject2, body2, reply_to=admin_email)
        print("✅ Auto-reply sent to", email)
    except Exception as e:
        print("❌ Auto-reply failed:", e)

    # Optional: email notification (add later)
    return jsonify({"ok": True, "message": "Message received"}), 201


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")))





