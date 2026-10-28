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


# GH-3: Tier 0 decides known senders and obvious bulk mail before Jev.

import csv  # noqa: E402
import json  # noqa: E402
import sqlite3  # noqa: E402
from unittest.mock import call  # noqa: E402

import pytest  # noqa: E402

from jev_mail.state import State  # noqa: E402

DEALS_TABLE = {"deals@example.com": "unsubscribe"}
ACCOUNT_KEY = "imap.example.com/user@example.com"


def _moving(*names: str) -> list[Category]:
    return [Category(name=n, description=n, actions=[Action(type="move", folder=n)]) for n in names]


def _gh3_config(categories: list[Category]) -> AppConfig:
    return AppConfig(
        mailbox=MailboxConfig(host="imap.example.com", username="user@example.com"),
        jev=JevSettings(default_threshold=0.6),
        categories=categories,
    )


def _deals_then_invoice() -> list[Email]:
    return [
        Email(uid=3, subject="Weekly deals", body="b", message_id="<d@example.com>", sender="Deals <deals@example.com>"),
        Email(uid=2, subject="Invoice #1", body="b", message_id="<i@example.com>", sender="ann@example.com"),
    ]


def _answering(answer: dict) -> MagicMock:
    client = MagicMock()
    client.decide.return_value = answer
    return client


def _billing_bulk_client() -> MagicMock:
    return _answering({"BILLING": 0.9, "BULK": 0.1})


def _mailbox(emails: list[Email]) -> MagicMock:
    mailbox = MagicMock()
    mailbox.fetch_unprocessed.return_value = emails
    return mailbox


def _state_rows(db) -> dict:
    rows = sqlite3.connect(db).execute("SELECT message_id, source, probabilities, actions FROM processed").fetchall()
    return {m: (source, json.loads(p), json.loads(a)) for m, source, p, a in rows}


def test_census_hit_skips_jev_and_the_state_row_records_its_source(tmp_path):
    """GH-3 S3.1"""
    mailbox = _mailbox(_deals_then_invoice())
    client = _billing_bulk_client()
    config = _gh3_config(_moving("BILLING", "BULK"))

    cli._process_unprocessed(
        mailbox, client, config, dry_run=False, account=config.mailbox, state=State(tmp_path / "state.db"), senders=DEALS_TABLE
    )

    client.decide.assert_called_once()
    assert client.decide.call_args.args[0] == _deals_then_invoice()[1].state
    assert mailbox.move.call_args_list == [call(3, "BULK"), call(2, "BILLING")]
    assert mailbox.mark_processed.call_args_list == [call(3), call(2)]
    rows = _state_rows(tmp_path / "state.db")
    assert {m: row[:2] for m, row in rows.items()} == {
        "<d@example.com>": ("census", {"BULK": 1.0}),
        "<i@example.com>": ("jev", {"BILLING": 0.9, "BULK": 0.1}),
    }


def test_heuristic_hit_skips_jev_and_records_heuristic(tmp_path):
    """GH-3 S3.2"""
    mail = Email(
        uid=4, subject="Sale", body="b", message_id="<s@example.com>", sender="shop@example.com", list_unsubscribe="<mailto:u@example.com>"
    )
    client = _billing_bulk_client()
    config = _gh3_config(_moving("BILLING", "BULK"))

    cli._process_unprocessed(
        _mailbox([mail]), client, config, dry_run=False, account=config.mailbox, state=State(tmp_path / "state.db"), senders={}
    )

    client.decide.assert_not_called()
    assert [row[0] for row in _state_rows(tmp_path / "state.db").values()] == ["heuristic"]


def test_dry_run_line_shows_the_tier0_source(capsys):
    """GH-3 S3.3"""
    config = _gh3_config(_moving("BILLING", "BULK"))

    cli._process_unprocessed(_mailbox(_deals_then_invoice()), _billing_bulk_client(), config, dry_run=True, senders=DEALS_TABLE)

    assert capsys.readouterr().out == (
        "[dry-run] 'Weekly deals': BULK (census) -> move\n" "[dry-run] 'Invoice #1': BILLING (0.90) -> move\n"
    )


def test_tier0_webhook_carries_probability_one(monkeypatch):
    """GH-3 S3.4"""
    import jev_mail.actions as actions

    posted = []
    monkeypatch.setattr(actions.httpx, "post", lambda url, json, timeout: posted.append((url, json)))
    config = _gh3_config([Category(name="BULK", description="Bulk", actions=[Action(type="webhook", url="https://hooks.example.com/x")])])
    mail = Email(uid=4, subject="Sale", body="b", list_unsubscribe="<mailto:u@example.com>")

    cli._process_unprocessed(_mailbox([mail]), MagicMock(), config, dry_run=False, senders={})

    assert posted == [("https://hooks.example.com/x", {"category": "BULK", "probability": 1.0, "subject": "Sale"})]


def _tag_and_move_billing_then_bulk() -> AppConfig:
    billing = Category(
        name="BILLING", description="Bills", actions=[Action(type="tag", value="Billing"), Action(type="move", folder="BILLING")]
    )
    return _gh3_config([billing, *_moving("BULK")])


def _invoice_from_ann() -> Email:
    return Email(uid=2, subject="Invoice #1", body="b", message_id="<i@example.com>", sender="ann@example.com")


def test_only_the_first_matched_move_runs(tmp_path):
    """GH-3 S3.5"""
    mailbox = _mailbox([_invoice_from_ann()])
    config = _tag_and_move_billing_then_bulk()

    cli._process_unprocessed(
        mailbox,
        _answering({"BILLING": 0.9, "BULK": 0.9}),
        config,
        dry_run=False,
        account=config.mailbox,
        state=State(tmp_path / "state.db"),
        senders={},
    )

    mailbox.add_tag.assert_called_once_with(2, "Billing")
    mailbox.move.assert_called_once_with(2, "BILLING")
    assert _state_rows(tmp_path / "state.db")["<i@example.com>"][2] == [
        {"category": "BILLING", "type": "tag", "value": "Billing"},
        {"category": "BILLING", "type": "move", "folder": "BILLING"},
    ]


def test_dry_run_prints_no_line_for_a_skipped_move(capsys):
    """GH-3 S3.6"""
    cli._process_unprocessed(
        _mailbox([_invoice_from_ann()]),
        _answering({"BILLING": 0.9, "BULK": 0.9}),
        _tag_and_move_billing_then_bulk(),
        dry_run=True,
        senders={},
    )

    assert capsys.readouterr().out == (
        "[dry-run] 'Invoice #1': BILLING (0.90) -> tag\n" "[dry-run] 'Invoice #1': BILLING (0.90) -> move\n"
    )


def test_tier0_hit_is_marked_when_jev_fails_for_the_others(capsys):
    """GH-3 S3.7"""
    mailbox = _mailbox(_deals_then_invoice())
    client = MagicMock()
    client.decide.side_effect = ProviderError("boom")

    failed = cli._process_unprocessed(
        mailbox, client, _gh3_config(_moving("BILLING", "BULK")), dry_run=False, senders=DEALS_TABLE
    )

    mailbox.mark_processed.assert_called_once_with(3)
    assert failed == 1


def test_a_matched_category_without_move_lets_a_later_move_run():
    """GH-3 S3.9"""
    action = Category(name="ACTION", description="Act", actions=[Action(type="flag")])
    mailbox = _mailbox([Email(uid=2, subject="Call me", body="b", message_id="<c@example.com>", sender="ann@example.com")])

    cli._process_unprocessed(
        mailbox, _answering({"ACTION": 0.9, "BULK": 0.9}), _gh3_config([action, *_moving("BULK")]), dry_run=False, senders={}
    )

    mailbox.set_flag.assert_called_once_with(2, True)
    mailbox.move.assert_called_once_with(2, "BULK")


GH3_YAML = (
    "mailbox:\n  host: imap.example.com\n  username: user@example.com\n"
    "senders_file: senders.csv\n"
    "categories:\n"
    "  BILLING:\n    description: Bills\n    actions:\n      - type: move\n        folder: BILLING\n"
    "  BULK:\n    description: Bulk\n    actions:\n      - type: move\n        folder: BULK\n"
)


def _gh3_dir(tmp_path, *, senders: bool = True):
    project = tmp_path / "project"
    project.mkdir()
    (project / "config.yaml").write_text(GH3_YAML)
    if senders:
        (project / "senders.csv").write_text("sender,verdict\ndeals@example.com,unsubscribe\n")
    return project


def _recording_mailbox(emails: list[Email]):
    class FakeMailbox(_fake_mailbox_class(emails)):
        moved: list[tuple[int, str]] = []

        def move(self, uid, folder):
            FakeMailbox.moved.append((uid, folder))

    return FakeMailbox


def test_missing_senders_file_stops_the_run_before_any_mailbox(tmp_path, monkeypatch, capsys):
    """GH-3 S2.6"""
    project = _gh3_dir(tmp_path, senders=False)
    fake = _fake_mailbox_class([])
    monkeypatch.setattr(cli, "Mailbox", fake)
    monkeypatch.setattr(cli, "get_jev_client", lambda *a, **k: _billing_bulk_client())

    assert cli.cmd_run(_args(project, "run")) == 1

    assert capsys.readouterr().err == f"error: senders file not found: {project}/senders.csv\n"
    assert fake.built == []


def test_watch_uses_the_sender_table_and_has_no_review_option(tmp_path, monkeypatch):
    """GH-3 S3.8"""
    project = _gh3_dir(tmp_path)

    class FakeMailbox(_recording_mailbox(_deals_then_invoice())):
        def supports_idle(self):
            raise ConnectionResetError("stop the loop")

    client = _billing_bulk_client()
    monkeypatch.setattr(cli, "Mailbox", FakeMailbox)
    monkeypatch.setattr(cli, "get_jev_client", lambda *a, **k: client)

    cli.cmd_watch(_args(project, "watch"))

    client.decide.assert_called_once()
    assert client.decide.call_args.args[0] == _deals_then_invoice()[1].state
    assert (3, "BULK") in FakeMailbox.moved
    with pytest.raises(SystemExit) as exc:
        cli.build_parser().parse_args(["watch", "--review", "x.csv"])
    assert exc.value.code == 2


def _review_run(tmp_path, monkeypatch, client, *argv: str):
    project = _gh3_dir(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    fake = _fake_mailbox_class(_deals_then_invoice())
    monkeypatch.setattr(cli, "Mailbox", fake)
    monkeypatch.setattr(cli, "get_jev_client", lambda *a, **k: client)
    paths = {"outside": str(outside / "review.csv"), "inside": str(project / "review.csv")}
    code = cli.cmd_run(_args(project, "run", *(paths.get(a, a) for a in argv)))
    return code, project, outside, fake


def _review_rows(path) -> list[list[str]]:
    with open(path, newline="") as f:
        return list(csv.reader(f))


def test_review_csv_has_one_row_per_email_with_source_and_probabilities(tmp_path, monkeypatch):
    """GH-3 S4.1"""
    code, _, outside, _ = _review_run(tmp_path, monkeypatch, _billing_bulk_client(), "--dry-run", "--review", "outside")

    assert code == 0
    assert _review_rows(outside / "review.csv") == [
        ["account", "uid", "subject", "source", "BILLING", "BULK"],
        [ACCOUNT_KEY, "3", "Weekly deals", "census", "", "1.0"],
        [ACCOUNT_KEY, "2", "Invoice #1", "jev", "0.9", "0.1"],
    ]


def test_review_is_refused_without_dry_run(tmp_path, monkeypatch, capsys):
    """GH-3 S4.2"""
    code, _, outside, fake = _review_run(tmp_path, monkeypatch, _billing_bulk_client(), "--review", "outside")

    assert code == 1
    assert capsys.readouterr().err == "error: --review needs --dry-run\n"
    assert fake.built == []
    assert not (outside / "review.csv").exists()


def test_review_is_refused_inside_the_project_directory(tmp_path, monkeypatch, capsys):
    """GH-3 S4.3"""
    code, project, _, fake = _review_run(tmp_path, monkeypatch, _billing_bulk_client(), "--dry-run", "--review", "inside")

    assert code == 1
    assert capsys.readouterr().err == (
        f"error: --review path must be outside {project.resolve()} -- its rows hold real subjects\n"
    )
    assert fake.built == []
    assert not (project / "review.csv").exists()


def test_review_csv_has_no_row_for_a_failed_email(tmp_path, monkeypatch):
    """GH-3 S4.4"""
    client = _fake_client(ProviderError("boom"))
    code, _, outside, _ = _review_run(tmp_path, monkeypatch, client, "--dry-run", "--review", "outside")

    assert code == 1
    assert _review_rows(outside / "review.csv") == [
        ["account", "uid", "subject", "source", "BILLING", "BULK"],
        [ACCOUNT_KEY, "3", "Weekly deals", "census", "", "1.0"],
    ]


def test_review_defaults_to_none(tmp_path, monkeypatch):
    """GH-3 S4.5"""
    assert cli.build_parser().parse_args(["run"]).review is None

    (tmp_path / "config.yaml").write_text(GH3_YAML)
    seen = {}
    monkeypatch.setattr(cli, "cmd_run", lambda args: seen.setdefault("review", args.review) or 0)
    monkeypatch.setattr(cli.sys, "argv", ["jev-mail", "--dir", str(tmp_path)])
    monkeypatch.setattr(cli.sys, "exit", lambda code: None)

    cli.main()

    assert "review" in seen and seen["review"] is None


GMAIL_YAML = "mailbox:\n  backend: gmail\n  username: me@example.com\n" + INVOICE_CATEGORIES


class _FakeFlow:
    built_with: tuple = ()

    @classmethod
    def from_client_secrets_file(cls, path, scopes):
        cls.built_with = (path, scopes)
        return cls()

    def run_local_server(self, port):
        assert port == 0
        return MagicMock(to_json=lambda: '{"token": "t"}')


def test_auth_gmail_writes_an_owner_only_token(tmp_path, monkeypatch, capsys):
    """GH-4 S4.1"""
    import stat

    import google_auth_oauthlib.flow

    (tmp_path / "client_secrets.json").write_text("{}")
    monkeypatch.setattr(google_auth_oauthlib.flow, "InstalledAppFlow", _FakeFlow)

    assert cli.cmd_auth_gmail(_args(tmp_path, "auth-gmail")) == 0

    token = tmp_path / "gmail-token.json"
    assert _FakeFlow.built_with == (str(tmp_path / "client_secrets.json"), ["https://www.googleapis.com/auth/gmail.modify"])
    assert token.read_text() == '{"token": "t"}'
    assert stat.S_IMODE(token.stat().st_mode) == 0o600
    out = capsys.readouterr().out
    assert str(token) in out
    assert '"token": "t"' not in out


def test_auth_gmail_without_client_secrets_names_the_file(tmp_path, capsys):
    """GH-4 S4.2"""
    assert cli.cmd_auth_gmail(_args(tmp_path, "auth-gmail")) == 1

    err = capsys.readouterr().err
    assert str(tmp_path / "client_secrets.json") in err
    assert "Desktop OAuth client" in err
    assert "Gmail API" in err
    assert not (tmp_path / "gmail-token.json").exists()


def test_run_without_a_gmail_token_names_auth_gmail(tmp_path, monkeypatch, capsys):
    """GH-4 S4.3"""
    import googleapiclient.discovery

    (tmp_path / "config.yaml").write_text(GMAIL_YAML)
    monkeypatch.setattr(cli, "get_jev_client", lambda *a, **k: _fake_client())
    build = MagicMock()
    monkeypatch.setattr(googleapiclient.discovery, "build", build)

    assert cli.cmd_run(_args(tmp_path, "run")) == 1

    assert capsys.readouterr().err == f"error: no Gmail token at {tmp_path}/gmail-token.json -- run `jev-mail auth-gmail`\n"
    build.assert_not_called()


def test_run_reports_a_gmail_error_not_a_traceback(tmp_path, monkeypatch, capsys):
    """GH-4 S4.5"""
    from jev_mail.mailbox import GmailError

    (tmp_path / "config.yaml").write_text(GMAIL_YAML)
    monkeypatch.setattr(cli, "get_jev_client", lambda *a, **k: _fake_client())

    class FailingGmail:
        def __init__(self, account, config_dir):
            pass

        def __enter__(self):
            raise GmailError("invalid_grant")

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(cli, "GmailMailbox", FailingGmail)

    assert cli.cmd_run(_args(tmp_path, "run")) == 1

    assert capsys.readouterr().err == "error: Gmail API error for me@example.com -- invalid_grant\n"


def test_run_opens_the_backend_each_account_names(tmp_path, monkeypatch):
    """GH-4 S5.1"""
    (tmp_path / "config.yaml").write_text(
        "accounts:\n  - host: imap.example.com\n  - backend: gmail\n    username: me@example.com\n" + INVOICE_CATEGORIES
    )
    imap = _fake_mailbox_class([])
    entered = []

    class FakeGmail(_fake_mailbox_class([])):
        built_with: list = []

        def __init__(self, account, config_dir):
            FakeGmail.built_with.append((account, config_dir))

        def __enter__(self):
            entered.append("gmail")
            return self

    monkeypatch.setattr(cli, "Mailbox", imap)
    monkeypatch.setattr(cli, "GmailMailbox", FakeGmail)
    monkeypatch.setattr(cli, "get_jev_client", lambda *a, **k: _fake_client())

    assert cli.cmd_run(_args(tmp_path, "run", "--dry-run")) == 0

    assert [(a.backend, a.host) for a in imap.built] == [("imap", "imap.example.com")]
    assert [(a.backend, d) for a, d in FakeGmail.built_with] == [("gmail", tmp_path)]
    assert entered == ["gmail"]


def test_watch_polls_a_gmail_account(tmp_path, monkeypatch):
    """GH-4 S5.2"""
    (tmp_path / "config.yaml").write_text(GMAIL_YAML.replace("username:", "poll_interval_seconds: 7\n  username:"))
    slept = []

    class FakeGmail(_fake_mailbox_class([])):
        def __init__(self, account, config_dir):
            pass

        def supports_idle(self):
            return False

        def idle(self):
            raise AssertionError("idle on Gmail")

    def fake_sleep(seconds):
        slept.append(seconds)
        raise KeyboardInterrupt

    monkeypatch.setattr(cli, "GmailMailbox", FakeGmail)
    monkeypatch.setattr(cli, "get_jev_client", lambda *a, **k: _fake_client())
    monkeypatch.setattr(cli.time, "sleep", fake_sleep)

    with pytest.raises(KeyboardInterrupt):
        cli.cmd_watch(_args(tmp_path, "watch", "--dry-run"))

    assert slept == [7]
