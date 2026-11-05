from unittest.mock import MagicMock

from jev_mail import census
from jev_mail.config import MailboxConfig
from jev_mail.mailbox import Mailbox

UNSUB = "<mailto:u@example.com>"


def test_tally_counts_per_address_and_suggests_only_new_bulk_senders():
    rows = (
        [("News <News@Example.com>", UNSUB)] * 10
        + [("deals@example.com", UNSUB)] * 12
        + [("mixed@example.com", UNSUB)] * 8
        + [("mixed@example.com", "")] * 2
        + [("noreply@example.com", "")]
        + [("", UNSUB)]
    )

    table = census.tally(rows, {"deals@example.com": "unsubscribe", "noreply@example.com": "GITHUB"})

    assert table == [
        ["deals@example.com", 12, 12, "", "unsubscribe", "BULK", ""],
        ["news@example.com", 10, 10, "", "", "BULK", "unsubscribe"],
        ["mixed@example.com", 10, 8, "", "", "", ""],
        ["noreply@example.com", 1, 0, "yes", "route", "GITHUB", ""],
    ]


def test_imap_fetch_senders_reads_headers_of_all_mail_newest_first():
    server = MagicMock()
    server.search.return_value = [3, 1, 2]
    server.fetch.return_value = {
        3: {b"BODY[HEADER.FIELDS (FROM LIST-UNSUBSCRIBE)]": f"From: a@example.com\r\nList-Unsubscribe: {UNSUB}\r\n\r\n".encode()},
        2: {b"BODY[HEADER.FIELDS (FROM LIST-UNSUBSCRIBE)]": b"From: b@example.com\r\n\r\n"},
    }

    rows = Mailbox(MailboxConfig(host="imap.example.com"), server=server).fetch_senders(limit=2)

    server.search.assert_called_once_with(["ALL"])
    server.fetch.assert_called_once_with([3, 2], ["BODY.PEEK[HEADER.FIELDS (FROM LIST-UNSUBSCRIBE)]"])
    assert rows == [("a@example.com", UNSUB), ("b@example.com", "")]
