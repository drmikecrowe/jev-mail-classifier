"""Tier 0: decide an email locally, before Jev, from the sender table and obvious headers."""

from __future__ import annotations

import csv
import re
from email.utils import parseaddr
from pathlib import Path

from jev_mail.config import AppConfig, Category, ConfigError
from jev_mail.mailbox import Email

OTP_SUBJECT = re.compile(
    r"\b(verification code|security code|confirmation code|login code|sign[- ]in code"
    r"|one[- ]time (password|passcode|code)|passcode|otp|2fa|two[- ]factor)\b",
    re.IGNORECASE,
)
NOREPLY_LOCAL_PARTS = ("noreply", "no-reply", "donotreply")
# The category each verdict gives; `keep` gives none and sends the email to Jev.
VERDICTS = {"unsubscribe": "BULK", "auto-archive": "MONITOR", "keep": None}


def sender_address(value: str) -> str:
    return parseaddr(value)[1].lower()


def load_senders(path: str | Path) -> dict[str, str]:
    """Reads the hand-edited sender table. Any bad row stops the run, so a typo never misroutes mail silently."""
    path = Path(path)
    if not path.is_file():
        raise ConfigError(f"senders file not found: {path}")
    table: dict[str, str] = {}
    with path.open(newline="") as f:
        reader = csv.DictReader(f)
        if not {"sender", "verdict"} <= set(reader.fieldnames or ()):
            raise ConfigError(f"{path.name}: the header row needs the columns sender and verdict")
        for row in reader:
            raw_sender = (row["sender"] or "").strip()
            if not raw_sender:
                continue
            verdict = (row["verdict"] or "").strip()
            if verdict not in VERDICTS:
                raise ConfigError(
                    f"{path.name} line {reader.line_num}: unknown verdict {verdict!r} (use unsubscribe, auto-archive or keep)"
                )
            sender = sender_address(raw_sender)
            if sender in table:
                raise ConfigError(f"{path.name} line {reader.line_num}: {sender} is listed twice")
            table[sender] = verdict
    return table


def decide(mail: Email, senders: dict[str, str], config: AppConfig) -> tuple[Category, str] | None:
    """The first Tier 0 rule that fires, as (category, source); None sends the email to Jev."""
    address = sender_address(mail.sender)
    verdict = senders.get(address)
    if verdict == "keep":
        return None
    local, at, _ = address.partition("@")
    rules = (
        (VERDICTS.get(verdict or ""), "census"),
        ("MONITOR" if OTP_SUBJECT.search(mail.subject) else None, "heuristic"),
        ("BULK" if mail.list_unsubscribe.strip() else None, "heuristic"),
        ("MONITOR" if at and local in NOREPLY_LOCAL_PARTS else None, "heuristic"),
    )
    by_name = {c.name: c for c in config.categories}
    for name, source in rules:
        # A rule whose category is not configured does not fire (A3).
        if name in by_name:
            return by_name[name], source
    return None
