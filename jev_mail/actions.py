from __future__ import annotations

import httpx

from jev_mail.config import Action
from jev_mail.mailbox import Email, MailBackend


def run_action(mailbox: MailBackend, mail: Email, action: Action, category_name: str, probability: float) -> None:
    if action.type == "tag":
        mailbox.add_tag(mail.uid, action.value)
    elif action.type == "move":
        mailbox.move(mail.uid, action.folder)
    elif action.type == "flag":
        mailbox.set_flag(mail.uid, True)
    elif action.type == "unflag":
        mailbox.set_flag(mail.uid, False)
    elif action.type == "mark_read":
        mailbox.set_seen(mail.uid, True)
    elif action.type == "mark_unread":
        mailbox.set_seen(mail.uid, False)
    elif action.type == "webhook":
        httpx.post(
            action.url,
            json={"category": category_name, "probability": probability, "subject": mail.subject},
            timeout=10.0,
        )
    else:
        raise ValueError(f"unknown action type: {action.type}")
