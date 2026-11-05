"""`census`: count each sender's mail from headers alone, with no Jev call, to grow the sender table."""

from __future__ import annotations

from collections import Counter

from jev_mail.tier0 import NOREPLY_LOCAL_PARTS, VERDICTS, sender_address

# A sender is suggested for `unsubscribe` at MIN_SEEN emails or more, BULK_SHARE of them with List-Unsubscribe.
MIN_SEEN = 10
BULK_SHARE = 0.9
COLUMNS = ("sender", "seen", "list_unsubscribe", "noreply", "verdict", "category", "suggest")


def row(address: str, count: int, unsubscribe: int, senders: dict[str, str]) -> list:
    """One COLUMNS row. `verdict` and `category` are the sender's table entry, or for a sender not
    in the table, the suggested category; `suggest` is filled only for a sender not in the table."""
    entry = senders.get(address, "")
    if entry in VERDICTS:
        verdict, category = entry, VERDICTS[entry] or ""
    else:
        # load_senders stores a route row as its category name.
        verdict, category = ("route", entry) if entry else ("", "")
    bulk = not entry and count >= MIN_SEEN and unsubscribe >= BULK_SHARE * count
    noreply = address.partition("@")[0] in NOREPLY_LOCAL_PARTS
    return [address, count, unsubscribe, "yes" if noreply else "", verdict, "BULK" if bulk else category, "unsubscribe" if bulk else ""]


def tally(rows: list[tuple[str, str]], senders: dict[str, str]) -> list[list]:
    """(From, List-Unsubscribe) pairs -> one COLUMNS row per sender address, most mail first."""
    seen: Counter[str] = Counter()
    unsubscribe: Counter[str] = Counter()
    for sender, list_unsubscribe in rows:
        address = sender_address(sender)
        if not address:
            continue
        seen[address] += 1
        if list_unsubscribe.strip():
            unsubscribe[address] += 1
    return [row(address, count, unsubscribe[address], senders) for address, count in seen.most_common()]
