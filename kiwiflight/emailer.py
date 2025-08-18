"""Email sending helper using yagmail.

Isolated from application logic for easier mocking/testing.
"""
import logging

import yagmail

from .config import settings


def send_email(subject: str, html_body: str) -> None:
    if not settings.email_configured():
        logging.warning("Email not sent: email credentials not fully configured.")
        return
    yag = yagmail.SMTP(settings.src_mail, settings.src_pwd, port=587, smtp_starttls=True, smtp_ssl=False)
    yag.send(to=settings.dst_mail, subject=subject, contents=html_body)
    logging.info("Email sent to %s", settings.dst_mail)
