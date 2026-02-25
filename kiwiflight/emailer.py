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
    logging.info(f"Email sent to {settings.dst_mail}")


def send_email_link(subject: str, url: str) -> None:
    """Send an email containing only a link to the hosted report."""
    if not settings.email_configured():
        logging.warning("Email not sent: email credentials not fully configured.")
        return
    html_body = (
        f'<p>Nowe oferty lotów są dostępne.</p>'
        f'<p><a href="{url}">{url}</a></p>'
    )
    yag = yagmail.SMTP(settings.src_mail, settings.src_pwd, port=587, smtp_starttls=True, smtp_ssl=False)
    yag.send(to=settings.dst_mail, subject=subject, contents=html_body)
    logging.info(f"Email (link) sent to {settings.dst_mail}")

