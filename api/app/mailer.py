import os
import smtplib
from email.message import EmailMessage


def smtp_configured():
    return bool(os.environ.get("SMTP_HOST"))


def send_email(to, subject, body):
    """以 SMTP 寄出單封 Email；未設定 SMTP_HOST 時丟出 RuntimeError。"""
    host = os.environ.get("SMTP_HOST")
    if not host:
        raise RuntimeError("尚未設定 SMTP 寄信伺服器")
    port = int(os.environ.get("SMTP_PORT", "587"))
    user = os.environ.get("SMTP_USER")
    password = os.environ.get("SMTP_PASSWORD")
    sender = os.environ.get("SMTP_FROM") or user

    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)

    if port == 465:
        server = smtplib.SMTP_SSL(host, port, timeout=15)
    else:
        server = smtplib.SMTP(host, port, timeout=15)
        if os.environ.get("SMTP_STARTTLS", "true").lower() != "false":
            server.starttls()
    try:
        if user and password:
            server.login(user, password)
        server.send_message(msg)
    finally:
        server.quit()
