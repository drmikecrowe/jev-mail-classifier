from unittest.mock import MagicMock

import jev_mail.cli as cli
from jev_mail.config import Action, AppConfig, Category, JevSettings, MailboxConfig
from jev_mail.mailbox import Email


def _config() -> AppConfig:
    return AppConfig(
        mailbox=MailboxConfig(host="imap.example.com"),
        jev=JevSettings(default_threshold=0.6),
        categories=[Category(name="invoice", description="Invoice", actions=[Action(type="tag", value="Invoice")])],
    )


def test_build_parser_defaults_and_dry_run_flag():
    parser = cli.build_parser()

    args = parser.parse_args(["run", "--dry-run"])
    assert args.command == "run"
    assert args.dry_run is True

    args = parser.parse_args(["watch"])
    assert args.command == "watch"
    assert args.dry_run is False

    args = parser.parse_args(["configure"])
    assert args.command == "configure"


def test_process_unprocessed_passes_limit_to_fetch():
    mailbox = MagicMock()
    mailbox.fetch_unprocessed.return_value = []
    client = MagicMock()

    config = _config()
    config.mailbox.max_emails_per_run = 7
    cli._process_unprocessed(mailbox, client, config, dry_run=False)

    mailbox.fetch_unprocessed.assert_called_once_with(limit=7)


def test_process_unprocessed_warns_when_limit_is_hit(capsys):
    mailbox = MagicMock()
    mailbox.fetch_unprocessed.return_value = [Email(uid=1, subject="One", body="body")]
    client = MagicMock()
    client.decide.return_value = {"invoice": 0.9}

    config = _config()
    config.mailbox.max_emails_per_run = 1
    cli._process_unprocessed(mailbox, client, config, dry_run=False)

    assert "max_emails_per_run" in capsys.readouterr().out


def test_process_unprocessed_dry_run_does_not_mutate_mailbox(capsys):
    mailbox = MagicMock()
    mailbox.fetch_unprocessed.return_value = [Email(uid=1, subject="Invoice #1", body="Please pay")]
    client = MagicMock()
    client.decide.return_value = {"invoice": 0.9}

    cli._process_unprocessed(mailbox, client, _config(), dry_run=True)

    mailbox.add_tag.assert_not_called()
    mailbox.mark_processed.assert_not_called()
    assert "dry-run" in capsys.readouterr().out


def test_process_unprocessed_applies_actions_and_marks_processed():
    mailbox = MagicMock()
    mailbox.fetch_unprocessed.return_value = [Email(uid=1, subject="Invoice #1", body="Please pay")]
    client = MagicMock()
    client.decide.return_value = {"invoice": 0.9}

    cli._process_unprocessed(mailbox, client, _config(), dry_run=False)

    mailbox.add_tag.assert_called_once_with(1, "Invoice")
    mailbox.mark_processed.assert_called_once_with(1)


def test_process_unprocessed_below_threshold_no_actions():
    mailbox = MagicMock()
    mailbox.fetch_unprocessed.return_value = [Email(uid=1, subject="Newsletter", body="...")]
    client = MagicMock()
    client.decide.return_value = {"invoice": 0.1}

    cli._process_unprocessed(mailbox, client, _config(), dry_run=False)

    mailbox.add_tag.assert_not_called()
    mailbox.mark_processed.assert_called_once_with(1)


def test_cmd_run_reports_config_error(monkeypatch, capsys):
    from jev_mail.config import ConfigError

    def raise_config_error(*a, **k):
        raise ConfigError("no config file")

    monkeypatch.setattr(cli, "load_config", raise_config_error)
    args = cli.build_parser().parse_args(["run"])
    args.dir = "."

    exit_code = cli.cmd_run(args)

    assert exit_code == 1
    assert "no config file" in capsys.readouterr().err


def test_cmd_run_reports_connection_error_not_a_traceback(monkeypatch, capsys):
    monkeypatch.setattr(cli, "load_config", lambda *a, **k: _config())
    monkeypatch.setattr(cli, "get_jev_client", lambda *a, **k: MagicMock())

    class FakeMailbox:
        def __init__(self, mailbox_config):
            pass

        def __enter__(self):
            raise ConnectionRefusedError("[Errno 61] Connection refused")

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(cli, "Mailbox", FakeMailbox)
    args = cli.build_parser().parse_args(["run"])
    args.dir = "."

    exit_code = cli.cmd_run(args)

    err = capsys.readouterr().err
    assert exit_code == 1
    assert "Traceback" not in err
    assert "imap.example.com" in err


def test_main_auto_launches_configure_when_no_config(monkeypatch, tmp_path):
    called = {}
    monkeypatch.setattr(cli, "cmd_configure", lambda args: called.setdefault("cmd", "configure") or 0)
    monkeypatch.setattr(cli.sys, "argv", ["jev-mail", "--dir", str(tmp_path)])
    monkeypatch.setattr(cli.sys, "exit", lambda code: called.setdefault("exit", code))

    cli.main()

    assert called["cmd"] == "configure"


def test_main_auto_runs_when_config_exists(monkeypatch, tmp_path):
    (tmp_path / "config.yaml").write_text("mailbox:\n  host: x\ncategories: {}\n")
    called = {}
    monkeypatch.setattr(cli, "cmd_run", lambda args: called.setdefault("cmd", "run") or 0)
    monkeypatch.setattr(cli.sys, "argv", ["jev-mail", "--dir", str(tmp_path)])
    monkeypatch.setattr(cli.sys, "exit", lambda code: called.setdefault("exit", code))

    cli.main()

    assert called["cmd"] == "run"


def _fake_mailbox_class(emails: list[Email]):
    """A stand-in for jev_mail.cli.Mailbox that records every account it is built with."""

    class FakeMailbox:
        built: list[MailboxConfig] = []
        fetch_limits: list[int] = []
        marked: list[int] = []

        def __init__(self, account):
            FakeMailbox.built.append(account)

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def fetch_unprocessed(self, limit=None):
            FakeMailbox.fetch_limits.append(limit)
            return list(emails)

        def mark_processed(self, uid):
            FakeMailbox.marked.append(uid)

        def add_tag(self, uid, value):
            pass

        def move(self, uid, folder):
            pass

    return FakeMailbox


def _fake_client(*answers: dict):
    client = MagicMock()
    client.decide.side_effect = list(answers)
    return client


INVOICE_CATEGORIES = """
categories:
  Invoice:
    description: Invoice
    threshold: 0.6
    actions:
      - type: tag
        value: Invoice
      - type: move
        folder: Invoices
"""

TWO_ACCOUNTS = (
    "accounts:\n"
    "  - host: a.example.com\n    max_emails_per_run: 3\n"
    "  - host: b.example.com\n    max_emails_per_run: 4\n" + INVOICE_CATEGORIES
)


def _args(tmp_path, *argv: str):
    return cli.build_parser().parse_args(["--dir", str(tmp_path), *argv])


def test_real_run_marks_processed_then_writes_one_state_row(tmp_path):
    """S3.1"""
    import json
    import sqlite3
    from datetime import datetime, timedelta

    from jev_mail.state import State

    db = tmp_path / "state.db"
    rows_when_marked = []
    mailbox = MagicMock()
    mailbox.fetch_unprocessed.return_value = [
        Email(uid=1, subject="Invoice #1", body="Please pay", message_id="<a1@example.com>")
    ]
    mailbox.mark_processed.side_effect = lambda uid: rows_when_marked.append(
        sqlite3.connect(db).execute("SELECT count(*) FROM processed").fetchone()[0]
    )
    client = _fake_client({"Invoice": 0.9})
    account = MailboxConfig(host="imap.example.com", username="me@example.com")
    config = AppConfig(
        mailbox=account,
        jev=JevSettings(default_threshold=0.6),
        categories=[Category(name="Invoice", description="Invoice", actions=[Action(type="tag", value="Invoice")])],
    )

    cli._process_unprocessed(mailbox, client, config, dry_run=False, account=account, state=State(db))

    mailbox.mark_processed.assert_called_once_with(1)
    assert rows_when_marked == [0]
    rows = sqlite3.connect(db).execute(
        "SELECT account, message_id, source, probabilities, actions, processed_at FROM processed"
    ).fetchall()
    assert len(rows) == 1
    account_key, message_id, source, probabilities, actions, processed_at = rows[0]
    assert (account_key, message_id, source) == ("imap.example.com/me@example.com", "<a1@example.com>", "jev")
    assert json.loads(probabilities) == {"Invoice": 0.9}
    assert json.loads(actions) == [{"category": "Invoice", "type": "tag", "value": "Invoice"}]
    assert datetime.fromisoformat(processed_at).utcoffset() == timedelta(0)


def test_dry_run_marks_nothing_and_creates_no_state_db(tmp_path, monkeypatch):
    """S3.2"""
    (tmp_path / "config.yaml").write_text("mailbox:\n  host: imap.example.com\n" + INVOICE_CATEGORIES)
    fake = _fake_mailbox_class([Email(uid=1, subject="Invoice #1", body="b")])
    monkeypatch.setattr(cli, "Mailbox", fake)
    monkeypatch.setattr(cli, "get_jev_client", lambda *a, **k: _fake_client({"Invoice": 0.9}))

    assert cli.cmd_run(_args(tmp_path, "run", "--dry-run")) == 0

    assert fake.marked == []
    assert not (tmp_path / "state.db").exists()


def test_run_processes_each_account_in_turn(tmp_path, monkeypatch):
    """S3.3"""
    (tmp_path / "config.yaml").write_text(TWO_ACCOUNTS)
    fake = _fake_mailbox_class([])
    monkeypatch.setattr(cli, "Mailbox", fake)
    monkeypatch.setattr(cli, "get_jev_client", lambda *a, **k: _fake_client())

    assert cli.cmd_run(_args(tmp_path, "run")) == 0

    assert [account.host for account in fake.built] == ["a.example.com", "b.example.com"]
    assert fake.fetch_limits == [3, 4]
    assert (tmp_path / "state.db").exists()


def test_watch_refuses_more_than_one_account(tmp_path, monkeypatch, capsys):
    """S3.4"""
    (tmp_path / "config.yaml").write_text(TWO_ACCOUNTS)
    fake = _fake_mailbox_class([])
    monkeypatch.setattr(cli, "Mailbox", fake)
    monkeypatch.setattr(cli, "get_jev_client", lambda *a, **k: _fake_client())

    assert cli.cmd_watch(_args(tmp_path, "watch")) == 1

    err = capsys.readouterr().err
    assert "watch" in err
    assert "one account" in err
    assert fake.built == []


def test_watch_writes_a_state_row_after_the_keyword(tmp_path, monkeypatch):
    """A8: watch records each processed email, as run does."""
    import sqlite3

    (tmp_path / "config.yaml").write_text("mailbox:\n  host: imap.example.com\n" + INVOICE_CATEGORIES)
    base = _fake_mailbox_class([Email(uid=1, subject="Invoice #1", body="b", message_id="<w@example.com>")])

    class FakeMailbox(base):
        def supports_idle(self):
            raise ConnectionResetError("stop the loop")

    monkeypatch.setattr(cli, "Mailbox", FakeMailbox)
    monkeypatch.setattr(cli, "get_jev_client", lambda *a, **k: _fake_client({"Invoice": 0.9}))

    assert cli.cmd_watch(_args(tmp_path, "watch")) == 1

    assert FakeMailbox.marked == [1]
    rows = sqlite3.connect(tmp_path / "state.db").execute("SELECT message_id FROM processed").fetchall()
    assert rows == [("<w@example.com>",)]


def test_dry_run_output_is_unchanged(tmp_path, monkeypatch, capsys):
    """S5.1: the expected string is the dry-run output at e393a22."""
    (tmp_path / "config.yaml").write_text("mailbox:\n  host: imap.example.com\n" + INVOICE_CATEGORIES)
    fake = _fake_mailbox_class([Email(uid=2, subject="Invoice #1", body="b"), Email(uid=1, subject="Newsletter", body="b")])
    monkeypatch.setattr(cli, "Mailbox", fake)
    monkeypatch.setattr(cli, "get_jev_client", lambda *a, **k: _fake_client({"Invoice": 0.9}, {"Invoice": 0.1}))

    assert cli.cmd_run(_args(tmp_path, "run", "--dry-run")) == 0

    assert capsys.readouterr().out == (
        "[dry-run] 'Invoice #1': Invoice (0.90) -> tag\n"
        "[dry-run] 'Invoice #1': Invoice (0.90) -> move\n"
        "[dry-run] 'Newsletter': no category matched\n"
    )


# GH-8: one ProviderError on one email does not abort the run.

from jev_mail.providers import ProviderError  # noqa: E402

PROVIDER_400 = "TypeSafe API request failed: 400 Bad Request"
ERROR_LINE = f"error: email uid 3: {PROVIDER_400} -- left unprocessed, will retry next run\n"


def _invoice_tag_config() -> AppConfig:
    return AppConfig(
        mailbox=MailboxConfig(host="imap.example.com", username="me@example.com"),
        jev=JevSettings(default_threshold=0.6),
        categories=[Category(name="Invoice", description="Invoice", actions=[Action(type="tag", value="Invoice")])],
    )


def _big_then_invoice() -> list[Email]:
    return [
        Email(uid=3, subject="Big", body="b", message_id="<big@example.com>"),
        Email(uid=2, subject="Invoice #1", body="b", message_id="<ok@example.com>"),
    ]


def _fail_then_invoice():
    return _fake_client(ProviderError(PROVIDER_400), {"Invoice": 0.9})


def test_failing_email_is_reported_and_the_next_is_processed(capsys):
    """S1.1"""
    mailbox = MagicMock()
    mailbox.fetch_unprocessed.return_value = _big_then_invoice()

    failed = cli._process_unprocessed(mailbox, _fail_then_invoice(), _invoice_tag_config(), dry_run=False)

    mailbox.mark_processed.assert_called_once_with(2)
    mailbox.add_tag.assert_called_once_with(2, "Invoice")
    assert capsys.readouterr().err == ERROR_LINE
    assert failed == 1


def test_failing_email_gets_no_state_row(tmp_path):
    """S1.2"""
    import sqlite3

    from jev_mail.state import State

    mailbox = MagicMock()
    mailbox.fetch_unprocessed.return_value = _big_then_invoice()
    config = _invoice_tag_config()

    cli._process_unprocessed(
        mailbox, _fail_then_invoice(), config, dry_run=False, account=config.mailbox, state=State(tmp_path / "state.db")
    )

    rows = sqlite3.connect(tmp_path / "state.db").execute("SELECT message_id FROM processed").fetchall()
    assert rows == [("<ok@example.com>",)]


def test_dry_run_reports_failing_email_and_prints_the_others(capsys):
    """S1.3"""
    mailbox = MagicMock()
    mailbox.fetch_unprocessed.return_value = _big_then_invoice()

    failed = cli._process_unprocessed(mailbox, _fail_then_invoice(), _invoice_tag_config(), dry_run=True)

    out, err = capsys.readouterr()
    assert out == "[dry-run] 'Invoice #1': Invoice (0.90) -> tag\n"
    assert err == ERROR_LINE
    mailbox.mark_processed.assert_not_called()
    assert failed == 1


def test_no_failure_returns_zero(capsys):
    """S1.4"""
    mailbox = MagicMock()
    mailbox.fetch_unprocessed.return_value = [Email(uid=2, subject="Invoice #1", body="b")]

    failed = cli._process_unprocessed(mailbox, _fake_client({"Invoice": 0.9}), _invoice_tag_config(), dry_run=False)

    assert failed == 0
    assert capsys.readouterr().err == ""


def test_run_exits_1_when_an_email_failed(tmp_path, monkeypatch):
    """S2.1"""
    (tmp_path / "config.yaml").write_text("mailbox:\n  host: imap.example.com\n" + INVOICE_CATEGORIES)
    fake = _fake_mailbox_class(_big_then_invoice())
    monkeypatch.setattr(cli, "Mailbox", fake)
    monkeypatch.setattr(cli, "get_jev_client", lambda *a, **k: _fail_then_invoice())

    assert cli.cmd_run(_args(tmp_path, "run")) == 1

    assert fake.marked == [2]


def test_run_finishes_every_account_before_exiting_1(tmp_path, monkeypatch):
    """S2.2"""
    (tmp_path / "config.yaml").write_text(TWO_ACCOUNTS)

    class FakeMailbox(_fake_mailbox_class([])):
        def fetch_unprocessed(self, limit=None):
            uid = len(FakeMailbox.built)
            return [Email(uid=uid, subject=f"Mail {uid}", body="b")]

    monkeypatch.setattr(cli, "Mailbox", FakeMailbox)
    monkeypatch.setattr(cli, "get_jev_client", lambda *a, **k: _fail_then_invoice())

    assert cli.cmd_run(_args(tmp_path, "run")) == 1

    assert [account.host for account in FakeMailbox.built] == ["a.example.com", "b.example.com"]
    assert FakeMailbox.marked == [2]


def test_run_exits_0_when_nothing_failed(tmp_path, monkeypatch):
    """S2.3"""
    (tmp_path / "config.yaml").write_text("mailbox:\n  host: imap.example.com\n" + INVOICE_CATEGORIES)
    monkeypatch.setattr(cli, "Mailbox", _fake_mailbox_class(_big_then_invoice()))
    client = MagicMock()
    client.decide.return_value = {"Invoice": 0.9}
    monkeypatch.setattr(cli, "get_jev_client", lambda *a, **k: client)

    assert cli.cmd_run(_args(tmp_path, "run")) == 0


def test_watch_keeps_going_after_a_failing_email(tmp_path, monkeypatch, capsys):
    """S3.1"""
    (tmp_path / "config.yaml").write_text("mailbox:\n  host: imap.example.com\n" + INVOICE_CATEGORIES)
    reached = []

    class FakeMailbox(_fake_mailbox_class(_big_then_invoice())):
        def supports_idle(self):
            reached.append(True)
            raise ConnectionResetError("stop the loop")

    monkeypatch.setattr(cli, "Mailbox", FakeMailbox)
    monkeypatch.setattr(cli, "get_jev_client", lambda *a, **k: _fail_then_invoice())

    cli.cmd_watch(_args(tmp_path, "watch"))

    assert FakeMailbox.marked == [2]
    assert ERROR_LINE in capsys.readouterr().err
    assert reached == [True]


def test_startup_provider_error_still_exits_1_before_any_mailbox(tmp_path, monkeypatch, capsys):
    """M3"""
    (tmp_path / "config.yaml").write_text("mailbox:\n  host: imap.example.com\n" + INVOICE_CATEGORIES)
    fake = _fake_mailbox_class([])
    monkeypatch.setattr(cli, "Mailbox", fake)

    def no_key(*a, **k):
        raise ProviderError("no Jev API key found")

    monkeypatch.setattr(cli, "get_jev_client", no_key)

    assert cli.cmd_run(_args(tmp_path, "run")) == 1

    assert capsys.readouterr().err == "error: no Jev API key found\n"
    assert fake.built == []


def test_only_provider_error_is_caught_per_email():
    """M7"""
    import pytest

    mailbox = MagicMock()
    mailbox.fetch_unprocessed.return_value = _big_then_invoice()
    client = _fake_client(RuntimeError("a real bug"), {"Invoice": 0.9})

    with pytest.raises(RuntimeError, match="a real bug"):
        cli._process_unprocessed(mailbox, client, _invoice_tag_config(), dry_run=False)
    mailbox.mark_processed.assert_not_called()
