"""Local-dev SMTP stub. Logs the 'sent' email instead of dispatching it."""
import json
import logging
from datetime import datetime, timezone

logger = logging.getLogger("procurebot.email")


def send_email(*, to: str, subject: str, body: str) -> dict:
    payload = {
        "to": to,
        "subject": subject,
        "body": body,
        "sent_at": datetime.now(timezone.utc).isoformat(),
        "transport": "stub",
    }
    logger.info("EMAIL_STUB %s", json.dumps(payload))
    return payload
