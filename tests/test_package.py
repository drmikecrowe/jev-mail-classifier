from pathlib import Path

PIPELINE_METHODS = ("fetch_unprocessed", "mark_processed", "add_tag", "move", "set_flag", "set_seen")
IDLE_METHODS = ("supports_idle", "idle", "idle_check", "idle_done")


def test_mailbox_package_keeps_every_import():
    """S1.1"""
    import jev_mail.mailbox
    from jev_mail.mailbox import PROCESSED_KEYWORD, Email, MailBackend, Mailbox, base, imap

    assert PROCESSED_KEYWORD == "$JevProcessed"
    assert Mailbox is imap.Mailbox
    assert Email is base.Email
    assert MailBackend is base.MailBackend
    assert not (Path(jev_mail.mailbox.__file__).parent.parent / "mailbox.py").exists()


def test_mail_backend_names_the_pipeline_methods_and_not_idle():
    """S1.2"""
    from jev_mail.mailbox import MailBackend, Mailbox

    for name in PIPELINE_METHODS:
        assert name in vars(MailBackend), name
        assert name in vars(Mailbox), name
    for name in IDLE_METHODS:
        assert name not in vars(MailBackend), name
