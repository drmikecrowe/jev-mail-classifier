import email
from unittest.mock import MagicMock

from jev_mail.config import MailboxConfig
from jev_mail.mailbox import PROCESSED_KEYWORD, Mailbox


def _raw_message(subject: str, body: str) -> bytes:
    msg = email.message.EmailMessage()
    msg["Subject"] = subject
    msg.set_content(body)
    return msg.as_bytes()


def test_fetch_unprocessed_parses_subject_and_body():
    fake_server = MagicMock()
    fake_server.search.return_value = [1]
    fake_server.fetch.return_value = {1: {b"RFC822": _raw_message("Hello", "World")}}

    with Mailbox(MailboxConfig(host="imap.example.com"), server=fake_server) as mailbox:
        emails = mailbox.fetch_unprocessed()

    fake_server.search.assert_called_once_with(["UNKEYWORD", PROCESSED_KEYWORD])
    assert len(emails) == 1
    assert emails[0].uid == 1
    assert emails[0].subject == "Hello"
    assert "World" in emails[0].body


def test_fetch_unprocessed_sorts_newest_first_before_limit():
    """IMAP UIDs increase with arrival and SEARCH returns them ascending
    (oldest first) -- a capped run must still pick up the newest mail, not
    get stuck on the oldest end of a big backlog."""
    fake_server = MagicMock()
    fake_server.search.return_value = [1, 2, 3, 4, 5]
    fake_server.fetch.return_value = {}

    with Mailbox(MailboxConfig(host="imap.example.com"), server=fake_server) as mailbox:
        mailbox.fetch_unprocessed(limit=2)

    fake_server.fetch.assert_called_once_with([5, 4], ["RFC822"])


def test_fetch_unprocessed_no_limit_still_sorts_newest_first():
    fake_server = MagicMock()
    fake_server.search.return_value = [1, 3, 2]
    fake_server.fetch.return_value = {}

    with Mailbox(MailboxConfig(host="imap.example.com"), server=fake_server) as mailbox:
        mailbox.fetch_unprocessed()

    fake_server.fetch.assert_called_once_with([3, 2, 1], ["RFC822"])


def test_fetch_unprocessed_returns_empty_when_no_uids():
    fake_server = MagicMock()
    fake_server.search.return_value = []

    with Mailbox(MailboxConfig(host="imap.example.com"), server=fake_server) as mailbox:
        emails = mailbox.fetch_unprocessed()

    assert emails == []
    fake_server.fetch.assert_not_called()


def test_mark_processed_adds_keyword():
    fake_server = MagicMock()
    with Mailbox(MailboxConfig(host="imap.example.com"), server=fake_server) as mailbox:
        mailbox.mark_processed(42)
    fake_server.add_flags.assert_called_once_with([42], [PROCESSED_KEYWORD])


def test_add_tag():
    fake_server = MagicMock()
    with Mailbox(MailboxConfig(host="imap.example.com"), server=fake_server) as mailbox:
        mailbox.add_tag(1, "Invoice")
    fake_server.add_flags.assert_called_once_with([1], ["Invoice"])


def test_move_creates_folder_if_missing():
    fake_server = MagicMock()
    fake_server.list_folders.return_value = [("\\HasNoChildren", "/", "INBOX")]

    with Mailbox(MailboxConfig(host="imap.example.com"), server=fake_server) as mailbox:
        mailbox.move(1, "Invoices")

    fake_server.create_folder.assert_called_once_with("Invoices")
    fake_server.move.assert_called_once_with([1], "Invoices")


def test_move_skips_create_when_folder_exists():
    fake_server = MagicMock()
    fake_server.list_folders.return_value = [("\\HasNoChildren", "/", "Invoices")]

    with Mailbox(MailboxConfig(host="imap.example.com"), server=fake_server) as mailbox:
        mailbox.move(1, "Invoices")

    fake_server.create_folder.assert_not_called()
    fake_server.move.assert_called_once_with([1], "Invoices")


def test_set_flag_true_and_false():
    fake_server = MagicMock()
    with Mailbox(MailboxConfig(host="imap.example.com"), server=fake_server) as mailbox:
        mailbox.set_flag(1, True)
        mailbox.set_flag(1, False)
    fake_server.add_flags.assert_called_once_with([1], [b"\\Flagged"])
    fake_server.remove_flags.assert_called_once_with([1], [b"\\Flagged"])


def test_set_seen_true_and_false():
    fake_server = MagicMock()
    with Mailbox(MailboxConfig(host="imap.example.com"), server=fake_server) as mailbox:
        mailbox.set_seen(1, True)
        mailbox.set_seen(1, False)
    fake_server.add_flags.assert_called_once_with([1], [b"\\Seen"])
    fake_server.remove_flags.assert_called_once_with([1], [b"\\Seen"])


def test_context_manager_logs_out():
    fake_server = MagicMock()
    with Mailbox(MailboxConfig(host="imap.example.com"), server=fake_server):
        pass
    fake_server.logout.assert_called_once()


def _call_names(client: MagicMock) -> list[str]:
    return [name for name, _, _ in client.method_calls]


def test_starttls_with_ca_file_upgrades_before_login(monkeypatch):
    """S1.1: Bridge serves plain IMAP on 1143; the connection must upgrade
    with STARTTLS, verified against Bridge's exported cert, before login."""
    imap_client = MagicMock()
    monkeypatch.setattr("jev_mail.mailbox.imap.IMAPClient", imap_client)
    sentinel_context = object()
    create_context = MagicMock(return_value=sentinel_context)
    monkeypatch.setattr("ssl.create_default_context", create_context)
    config = MailboxConfig(host="127.0.0.1", port=1143, tls="starttls", tls_ca_file="/tmp/bridge.pem")

    Mailbox(config).__enter__()

    imap_client.assert_called_once_with("127.0.0.1", port=1143, use_uid=True, ssl=False)
    create_context.assert_called_once_with(cafile="/tmp/bridge.pem")
    client = imap_client.return_value
    client.starttls.assert_called_once_with(ssl_context=sentinel_context)
    names = _call_names(client)
    assert names.index("starttls") < names.index("login")


def test_starttls_without_ca_file_uses_default_context(monkeypatch):
    """S1.2: no tls_ca_file means imapclient's own default verification."""
    imap_client = MagicMock()
    monkeypatch.setattr("jev_mail.mailbox.imap.IMAPClient", imap_client)
    config = MailboxConfig(host="127.0.0.1", port=1143, tls="starttls")

    Mailbox(config).__enter__()

    client = imap_client.return_value
    client.starttls.assert_called_once_with(ssl_context=None)
    names = _call_names(client)
    assert names.index("starttls") < names.index("login")


def test_config_without_tls_keys_connects_with_implicit_tls(tmp_path, monkeypatch):
    """S1.3 / M2: an existing config.yaml with no tls keys behaves as before."""
    from jev_mail.config import load_config

    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
mailbox:
  host: imap.example.com
categories:
  invoice:
    description: Invoice
"""
    )
    imap_client = MagicMock()
    monkeypatch.setattr("jev_mail.mailbox.imap.IMAPClient", imap_client)

    config = load_config(config_path, tmp_path / ".env")
    Mailbox(config.mailbox).__enter__()

    assert config.mailbox.tls == "ssl"
    assert config.mailbox.tls_ca_file == ""
    imap_client.assert_called_once_with("imap.example.com", port=993, use_uid=True, ssl=True)
    imap_client.return_value.starttls.assert_not_called()


def test_fetch_unprocessed_reads_message_id_sender_and_list_unsubscribe():
    """S1.4"""
    raw = (
        b"Message-ID: <a1@example.com>\r\n"
        b"From: =?utf-8?q?Ann_Lee?= <ann@example.com>\r\n"
        b"List-Unsubscribe: <mailto:unsub@example.com>\r\n"
        b"Subject: Hello\r\n"
        b"\r\n"
        b"World\r\n"
    )
    fake_server = MagicMock()
    fake_server.search.return_value = [1]
    fake_server.fetch.return_value = {1: {b"RFC822": raw}}

    with Mailbox(MailboxConfig(host="imap.example.com"), server=fake_server) as mailbox:
        (mail,) = mailbox.fetch_unprocessed()

    assert mail.message_id == "<a1@example.com>"
    assert mail.sender == "Ann Lee <ann@example.com>"
    assert mail.list_unsubscribe == "<mailto:unsub@example.com>"


def test_missing_headers_are_empty_strings():
    """S1.5"""
    from jev_mail.mailbox import Email

    fake_server = MagicMock()
    fake_server.search.return_value = [1]
    fake_server.fetch.return_value = {1: {b"RFC822": b"Subject: Hello\r\n\r\nWorld\r\n"}}

    with Mailbox(MailboxConfig(host="imap.example.com"), server=fake_server) as mailbox:
        (mail,) = mailbox.fetch_unprocessed()

    assert (mail.message_id, mail.sender, mail.list_unsubscribe) == ("", "", "")
    bare = Email(uid=1, subject="x", body="y")
    assert (bare.message_id, bare.sender, bare.list_unsubscribe) == ("", "", "")
