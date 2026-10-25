import os

import pytest

from jev_mail.config import (
    Action,
    AppConfig,
    Category,
    ConfigError,
    JevSettings,
    MailboxConfig,
    load_config,
    save_config,
    save_env,
)


def test_load_config_interpolates_env_and_parses_categories(tmp_path, monkeypatch):
    monkeypatch.setenv("IMAP_USERNAME", "me@example.com")
    monkeypatch.setenv("IMAP_PASSWORD", "secret")
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
mailbox:
  host: imap.example.com
  username: ${IMAP_USERNAME}
  password: ${IMAP_PASSWORD}
jev:
  default_threshold: 0.7
categories:
  invoice:
    description: "Invoice or billing"
    actions:
      - type: tag
        value: Invoice
"""
    )

    config = load_config(config_path, env_path=tmp_path / "does-not-exist.env")

    assert config.mailbox.username == "me@example.com"
    assert config.mailbox.password == "secret"
    assert config.jev.default_threshold == 0.7
    assert len(config.categories) == 1
    assert config.categories[0].name == "invoice"
    assert config.categories[0].actions[0].type == "tag"


def test_load_config_max_emails_per_run_defaults_and_overrides(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text('mailbox:\n  host: imap.example.com\ncategories:\n  spam:\n    description: spam\n    actions: []\n')
    config = load_config(config_path, env_path=tmp_path / "does-not-exist.env")
    assert config.mailbox.max_emails_per_run == 25

    config_path.write_text(
        "mailbox:\n  host: imap.example.com\n  max_emails_per_run: 5\n"
        "categories:\n  spam:\n    description: spam\n    actions: []\n"
    )
    config = load_config(config_path, env_path=tmp_path / "does-not-exist.env")
    assert config.mailbox.max_emails_per_run == 5


def test_load_config_empty_host_raises(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text("mailbox:\n  host: ''\ncategories:\n  spam:\n    description: spam\n    actions: []\n")
    with pytest.raises(ConfigError):
        load_config(config_path, env_path=tmp_path / "does-not-exist.env")


def test_load_config_missing_env_var_raises(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
mailbox:
  host: imap.example.com
  username: ${DEFINITELY_NOT_SET}
categories:
  spam:
    description: spam
    actions: []
"""
    )
    with pytest.raises(ConfigError):
        load_config(config_path, env_path=tmp_path / "does-not-exist.env")


def test_load_config_no_categories_raises(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text("mailbox:\n  host: imap.example.com\ncategories: {}\n")
    with pytest.raises(ConfigError):
        load_config(config_path, env_path=tmp_path / "does-not-exist.env")


def test_load_config_missing_file_raises(tmp_path):
    with pytest.raises(ConfigError):
        load_config(tmp_path / "nope.yaml")


def test_save_config_never_writes_literal_secrets(tmp_path):
    config = AppConfig(
        mailbox=MailboxConfig(host="imap.example.com", username="me@example.com", password="hunter2"),
        jev=JevSettings(),
        categories=[Category(name="urgent", description="Urgent", actions=[Action(type="flag")])],
    )
    out_path = tmp_path / "config.yaml"
    save_config(config, out_path)

    text = out_path.read_text()
    assert "hunter2" not in text
    assert "me@example.com" not in text
    assert "${IMAP_USERNAME}" in text
    assert "${IMAP_PASSWORD}" in text


def test_save_config_round_trips_through_load(tmp_path, monkeypatch):
    monkeypatch.setenv("IMAP_USERNAME", "me@example.com")
    monkeypatch.setenv("IMAP_PASSWORD", "hunter2")
    config = AppConfig(
        mailbox=MailboxConfig(host="imap.example.com", username="me@example.com", password="hunter2"),
        jev=JevSettings(default_threshold=0.5),
        categories=[
            Category(
                name="invoice",
                description="Invoice",
                threshold=0.8,
                actions=[Action(type="move", folder="Invoices")],
            )
        ],
    )
    out_path = tmp_path / "config.yaml"
    save_config(config, out_path)

    reloaded = load_config(out_path, env_path=tmp_path / "does-not-exist.env")
    assert reloaded.mailbox.host == "imap.example.com"
    assert reloaded.mailbox.username == "me@example.com"
    assert reloaded.categories[0].threshold == 0.8
    assert reloaded.categories[0].actions[0].folder == "Invoices"


def test_read_env_returns_empty_dict_for_missing_file(tmp_path):
    from jev_mail.config import read_env

    assert read_env(tmp_path / "does-not-exist.env") == {}


def test_read_env_parses_existing_file(tmp_path):
    from jev_mail.config import read_env

    env_path = tmp_path / ".env"
    env_path.write_text("OPENROUTER_API_KEY=abc123\nIMAP_USERNAME=me@example.com\n")

    assert read_env(env_path) == {"OPENROUTER_API_KEY": "abc123", "IMAP_USERNAME": "me@example.com"}


def test_save_env_merges_and_preserves_existing(tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text("EXISTING=keep\nOPENROUTER_API_KEY=old\n")

    save_env({"OPENROUTER_API_KEY": "new", "IMAP_USERNAME": "me@example.com"}, env_path)

    content = env_path.read_text()
    assert "EXISTING=keep" in content
    assert "OPENROUTER_API_KEY=new" in content
    assert "IMAP_USERNAME=me@example.com" in content


def test_save_env_removes_key_when_new_value_is_empty(tmp_path):
    """Regression: this used to silently keep the old value, so clearing a
    field in the credentials screen and hitting Continue did nothing."""
    env_path = tmp_path / ".env"
    env_path.write_text("REMOVE_ME=old\nKEEP=me\n")

    save_env({"REMOVE_ME": "", "NEW": "value"}, env_path)

    content = env_path.read_text()
    assert "REMOVE_ME" not in content
    assert "KEEP=me" in content
    assert "NEW=value" in content


def test_save_env_leaves_keys_not_passed_untouched(tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text("UNTOUCHED=still-here\n")

    save_env({"NEW": "value"}, env_path)

    content = env_path.read_text()
    assert "UNTOUCHED=still-here" in content
    assert "NEW=value" in content


def test_tls_settings_round_trip_through_save_and_load(tmp_path, monkeypatch):
    """S1.4"""
    monkeypatch.setenv("IMAP_USERNAME", "me@example.com")
    monkeypatch.setenv("IMAP_PASSWORD", "secret")
    config = AppConfig(
        mailbox=MailboxConfig(host="127.0.0.1", port=1143, tls="starttls", tls_ca_file="/tmp/bridge.pem"),
        jev=JevSettings(),
        categories=[Category(name="invoice", description="Invoice")],
    )
    config_path = tmp_path / "config.yaml"

    save_config(config, config_path)
    loaded = load_config(config_path, tmp_path / ".env")

    assert loaded.mailbox.tls == "starttls"
    assert loaded.mailbox.tls_ca_file == "/tmp/bridge.pem"


def test_unknown_tls_value_is_rejected(tmp_path):
    """S1.5"""
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
mailbox:
  host: 127.0.0.1
  tls: plain
categories:
  invoice:
    description: Invoice
"""
    )

    with pytest.raises(ConfigError) as excinfo:
        load_config(config_path, tmp_path / ".env")

    message = str(excinfo.value)
    assert "mailbox.tls" in message
    assert "ssl" in message
    assert "starttls" in message
