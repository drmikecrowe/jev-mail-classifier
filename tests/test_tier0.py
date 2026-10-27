from pathlib import Path

import pytest

from jev_mail import tier0
from jev_mail.config import Action, AppConfig, Category, ConfigError, JevSettings, MailboxConfig
from jev_mail.mailbox import Email

FIVE = ("BILLING", "ACTION", "PERSONAL", "MONITOR", "BULK")
REPO = Path(__file__).resolve().parent.parent


def _config(*names: str) -> AppConfig:
    return AppConfig(
        mailbox=MailboxConfig(host="imap.example.com"),
        jev=JevSettings(default_threshold=0.6),
        categories=[Category(name=n, description=n, actions=[Action(type="move", folder=n)]) for n in names],
    )


def _decided(result):
    """(category name, source) for a hit, so the assertion names what the SPEC names."""
    return None if result is None else (result[0].name, result[1])


def test_unsubscribe_sender_goes_to_bulk():
    """S1.1"""
    config = _config(*FIVE)
    mail = Email(uid=1, subject="Hi", body="b", sender="News <News@Example.com>")

    category, source = tier0.decide(mail, {"news@example.com": "unsubscribe"}, config)

    assert category is config.categories[4]
    assert (category.name, source) == ("BULK", "census")


def test_auto_archive_sender_goes_to_monitor():
    """S1.2"""
    mail = Email(uid=1, subject="Hi", body="b", sender="News <News@Example.com>")

    assert _decided(tier0.decide(mail, {"news@example.com": "auto-archive"}, _config(*FIVE))) == ("MONITOR", "census")


def test_keep_sender_goes_to_jev_even_when_a_header_rule_fires():
    """S1.3"""
    mail = Email(
        uid=1, subject="Your verification code", body="b", sender="news@example.com", list_unsubscribe="<mailto:u@example.com>"
    )

    assert tier0.decide(mail, {"news@example.com": "keep"}, _config(*FIVE)) is None


def test_otp_subject_comes_before_list_unsubscribe():
    """S1.4"""
    mail = Email(
        uid=1,
        subject="Your verification code is 123456",
        body="b",
        sender="alerts@example.com",
        list_unsubscribe="<mailto:u@example.com>",
    )

    assert _decided(tier0.decide(mail, {}, _config(*FIVE))) == ("MONITOR", "heuristic")


def test_list_unsubscribe_comes_before_noreply():
    """S1.5"""
    mail = Email(uid=1, subject="Receipt", body="b", sender="noreply@example.com", list_unsubscribe="<mailto:u@example.com>")

    assert _decided(tier0.decide(mail, {}, _config(*FIVE))) == ("BULK", "heuristic")


@pytest.mark.parametrize("sender", ["No Reply <no-reply@example.com>", "NoReply@example.com", "donotreply@example.com"])
def test_noreply_sender_goes_to_monitor(sender):
    """S1.6"""
    mail = Email(uid=1, subject="Receipt", body="b", sender=sender)

    assert _decided(tier0.decide(mail, {}, _config(*FIVE))) == ("MONITOR", "heuristic")


def test_near_misses_go_to_jev():
    """S1.7"""
    config = _config(*FIVE)

    assert tier0.decide(Email(uid=1, subject="Code review notes", body="b", sender="noreply-billing@example.com"), {}, config) is None
    assert tier0.decide(Email(uid=2, subject="Lunch?", body="b", sender="Ann Lee <ann@example.com>"), {}, config) is None


def test_rule_for_an_unconfigured_category_does_not_fire():
    """S1.8"""
    config = _config("BULK")

    assert tier0.decide(Email(uid=1, subject="Receipt", body="b", sender="noreply@example.com"), {}, config) is None
    mail = Email(uid=2, subject="Your verification code", body="b", sender="a@example.com", list_unsubscribe="<mailto:u@example.com>")
    assert _decided(tier0.decide(mail, {}, config)) == ("BULK", "heuristic")


def test_folded_from_header_still_matches_the_table():
    """S1.9"""
    mail = Email(uid=1, subject="Hi", body="b", sender="Ann Lee\r\n <ann@example.com>")

    assert _decided(tier0.decide(mail, {"ann@example.com": "unsubscribe"}, _config(*FIVE))) == ("BULK", "census")


def test_blank_list_unsubscribe_does_not_fire():
    """S1.10"""
    mail = Email(uid=1, subject="Hi", body="b", sender="ann@example.com", list_unsubscribe="   ")

    assert tier0.decide(mail, {}, _config(*FIVE)) is None


def _senders(tmp_path, *lines: str) -> Path:
    path = tmp_path / "senders.csv"
    path.write_text("".join(f"{line}\n" for line in lines))
    return path


def test_load_senders_normalizes_and_skips_blank_senders(tmp_path):
    """S2.1"""
    path = _senders(tmp_path, "sender,verdict,count", "News@Example.com,unsubscribe,12", ",keep,1", "Ann <ann@example.com>,keep,3")

    assert tier0.load_senders(path) == {"news@example.com": "unsubscribe", "ann@example.com": "keep"}


def test_load_senders_refuses_an_unknown_verdict(tmp_path):
    """S2.2"""
    path = _senders(tmp_path, "sender,verdict", "a@example.com,keep", "b@example.com,archive")

    with pytest.raises(ConfigError) as exc:
        tier0.load_senders(path)
    assert str(exc.value) == "senders.csv line 3: unknown verdict 'archive' (use unsubscribe, auto-archive or keep)"


def test_load_senders_refuses_a_sender_listed_twice(tmp_path):
    """S2.3"""
    path = _senders(tmp_path, "sender,verdict", "a@example.com,keep", "b@example.com,keep", "A@example.com,unsubscribe")

    with pytest.raises(ConfigError) as exc:
        tier0.load_senders(path)
    assert str(exc.value) == "senders.csv line 4: a@example.com is listed twice"


def test_load_senders_refuses_a_header_without_sender(tmp_path):
    """S2.4"""
    path = _senders(tmp_path, "address,verdict", "a@example.com,keep")

    with pytest.raises(ConfigError) as exc:
        tier0.load_senders(path)
    assert str(exc.value) == "senders.csv: the header row needs the columns sender and verdict"


def test_example_senders_file_holds_only_fake_addresses():
    """S5.2"""
    table = tier0.load_senders(REPO / "senders.example.csv")

    assert table
    assert all(sender.endswith("@example.com") for sender in table)
