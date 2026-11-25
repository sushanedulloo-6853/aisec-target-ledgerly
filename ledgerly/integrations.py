"""Outbound integrations: Bankrail (payments) and SMTP notifications."""

import logging
import secrets
import smtplib
from email.message import EmailMessage

import requests

from ledgerly.config import settings

log = logging.getLogger("ledgerly.integrations")


def submit_transfer(transfer: dict) -> str:
    if not settings.BANKRAIL_LIVE:
        ref = "brk_tr_" + secrets.token_hex(8)
        log.info("bankrail sandbox transfer %s %s", ref, transfer)
        return ref
    resp = requests.post(
        f"{settings.BANKRAIL_BASE_URL}/transfers",
        json=transfer,
        headers={"Authorization": f"Bearer {settings.BANKRAIL_API_KEY}"},
        timeout=20,
    )
    resp.raise_for_status()
    return resp.json()["id"]


def send_email(to: str, subject: str, body: str) -> None:
    if not settings.MAIL_ENABLED:
        log.info("mail disabled, would send to=%s subject=%s", to, subject)
        return
    msg = EmailMessage()
    msg["From"] = settings.SMTP_USER
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    with smtplib.SMTP(settings.SMTP_HOST, 587, timeout=20) as smtp:
        smtp.starttls()
        smtp.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        smtp.send_message(msg)


def notify(conn, business_id: int, user_id: int | None, email: str, subject: str, body: str) -> int:
    cur = conn.execute(
        "INSERT INTO notifications (business_id, recipient_user_id, recipient_email, subject, body)"
        " VALUES (?, ?, ?, ?, ?)",
        (business_id, user_id, email, subject, body),
    )
    conn.commit()
    send_email(email, subject, body)
    return cur.lastrowid
