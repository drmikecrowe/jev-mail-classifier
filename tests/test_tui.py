from textual.containers import VerticalScroll
from textual.widgets import Checkbox, Input, Static

from jev_mail.config import load_config
from jev_mail.providers import ProviderError
from jev_mail.tui.app import JevMailConfigApp
from jev_mail.tui.screens import credentials_screen as credentials_screen_module


async def test_every_screen_scroll_area_actually_gets_space(tmp_path):
    """Regression test: a plain Horizontal defaults to height:1fr, which once
    silently broke height:auto on '.actions-dock' and squeezed the sibling
    VerticalScroll down to 1 row -- fields were still settable via `.value =`
    (bypassing layout entirely) so earlier tests didn't catch it. This checks
    real layout, not just that a value round-trips."""
    app = JevMailConfigApp(tmp_path / "config.yaml", tmp_path / ".env")
    async with app.run_test(size=(100, 50)) as pilot:
        await pilot.pause()
        for screen_name in ["credentials", "mailbox"]:
            scroll = pilot.app.screen.query_one(VerticalScroll)
            assert scroll.region.height > 10, f"{screen_name} screen's scroll area collapsed: {scroll.region}"
            if screen_name == "mailbox":
                pilot.app.screen.query_one("#host", Input).value = "imap.example.com"
            await pilot.click("#continue")
            await pilot.pause()


async def test_full_configure_flow_writes_env_and_config(tmp_path):
    config_path = tmp_path / "config.yaml"
    env_path = tmp_path / ".env"
    app = JevMailConfigApp(config_path, env_path)

    async with app.run_test(size=(100, 60)) as pilot:
        await pilot.pause()
        # Screen 1: credentials
        pilot.app.screen.query_one("#openrouter_key", Input).value = "or-test-key"
        pilot.app.screen.query_one("#imap_username", Input).value = "me@example.com"
        pilot.app.screen.query_one("#imap_password", Input).value = "hunter2"
        await pilot.click("#continue")
        await pilot.pause()

        # Screen 2: mailbox
        pilot.app.screen.query_one("#host", Input).value = "imap.example.com"
        pilot.app.screen.query_one("#folder", Input).value = "INBOX"
        await pilot.click("#continue")
        await pilot.pause()

        # Screen 3: categories -- add one
        await pilot.press("a")
        await pilot.pause()
        pilot.app.screen.query_one("#name", Input).value = "invoice"
        pilot.app.screen.query_one("#description", Input).value = "Invoice or billing"
        pilot.app.screen.query_one("#cb_tag", Checkbox).value = True
        pilot.app.screen.query_one("#tag_value", Input).value = "Invoice"
        await pilot.click("#save")

        assert len(app.config.categories) == 1
        assert app.config.categories[0].name == "invoice"

        await pilot.press("s")

    assert env_path.exists()
    assert "OPENROUTER_API_KEY=or-test-key" in env_path.read_text()
    assert "IMAP_USERNAME=me@example.com" in env_path.read_text()

    assert config_path.exists()
    reloaded = load_config(config_path, env_path)
    assert reloaded.mailbox.host == "imap.example.com"
    assert reloaded.categories[0].name == "invoice"
    assert reloaded.categories[0].actions[0].type == "tag"
    assert reloaded.categories[0].actions[0].value == "Invoice"


async def test_credentials_screen_prefills_from_existing_env(tmp_path):
    config_path = tmp_path / "config.yaml"
    env_path = tmp_path / ".env"
    env_path.write_text("OPENROUTER_API_KEY=already-saved\nIMAP_USERNAME=me@example.com\n")

    app = JevMailConfigApp(config_path, env_path)
    async with app.run_test(size=(100, 60)) as pilot:
        await pilot.pause()
        assert pilot.app.screen.query_one("#openrouter_key", Input).value == "already-saved"
        assert pilot.app.screen.query_one("#imap_username", Input).value == "me@example.com"

        # Continuing without touching anything must NOT wipe the saved key.
        await pilot.click("#continue")

    assert "OPENROUTER_API_KEY=already-saved" in env_path.read_text()


async def test_clearing_a_prefilled_field_and_saving_removes_it(tmp_path):
    config_path = tmp_path / "config.yaml"
    env_path = tmp_path / ".env"
    env_path.write_text("OPENROUTER_API_KEY=already-saved\nIMAP_USERNAME=me@example.com\n")

    app = JevMailConfigApp(config_path, env_path)
    async with app.run_test(size=(100, 60)) as pilot:
        await pilot.pause()
        pilot.app.screen.query_one("#openrouter_key", Input).value = ""
        await pilot.click("#continue")

    content = env_path.read_text()
    assert "OPENROUTER_API_KEY" not in content
    assert "IMAP_USERNAME=me@example.com" in content


async def test_test_key_button_shows_green_tick_on_success(monkeypatch, tmp_path):
    fake_client = type("FakeClient", (), {"decide": lambda self, state, categories: {"ok": 0.99}})()
    monkeypatch.setattr(credentials_screen_module, "get_jev_client", lambda settings, env: fake_client)

    app = JevMailConfigApp(tmp_path / "config.yaml", tmp_path / ".env")
    async with app.run_test(size=(100, 60)) as pilot:
        await pilot.pause()
        pilot.app.screen.query_one("#openrouter_key", Input).value = "or-test-key"
        await pilot.click("#test_key")
        await pilot.app.screen._test_worker.wait()
        await pilot.pause()

        status = pilot.app.screen.query_one("#key_test_status", Static).content
        assert "Key works" in status


async def test_test_key_button_shows_error_on_failure(monkeypatch, tmp_path):
    def raise_provider_error(settings, env):
        raise ProviderError("no Jev API key found")

    monkeypatch.setattr(credentials_screen_module, "get_jev_client", raise_provider_error)

    app = JevMailConfigApp(tmp_path / "config.yaml", tmp_path / ".env")
    async with app.run_test(size=(100, 60)) as pilot:
        await pilot.pause()
        await pilot.click("#test_key")
        await pilot.app.screen._test_worker.wait()
        await pilot.pause()

        status = pilot.app.screen.query_one("#key_test_status", Static).content
        assert "no Jev API key found" in status


async def test_delete_category(tmp_path):
    from jev_mail.config import Action, AppConfig, Category, JevSettings, MailboxConfig

    config = AppConfig(
        mailbox=MailboxConfig(host="imap.example.com"),
        jev=JevSettings(),
        categories=[Category(name="spam", description="Spam", actions=[Action(type="move", folder="Spam")])],
    )
    app = JevMailConfigApp(tmp_path / "config.yaml", tmp_path / ".env", config)

    async with app.run_test(size=(100, 60)) as pilot:
        await pilot.pause()
        await pilot.click("#continue")  # credentials -> mailbox
        await pilot.click("#continue")  # mailbox -> categories

        list_view = pilot.app.screen.query_one("#category_list")
        list_view.index = 0
        await pilot.press("d")

        assert app.config.categories == []


async def test_cancel_edit_does_not_add_category(tmp_path):
    app = JevMailConfigApp(tmp_path / "config.yaml", tmp_path / ".env")

    async with app.run_test(size=(100, 60)) as pilot:
        await pilot.pause()
        await pilot.click("#continue")
        await pilot.pause()
        pilot.app.screen.query_one("#host", Input).value = "imap.example.com"
        await pilot.click("#continue")

        await pilot.press("a")
        await pilot.click("#cancel")

        assert app.config.categories == []


async def test_mailbox_screen_rejects_empty_host(tmp_path):
    app = JevMailConfigApp(tmp_path / "config.yaml", tmp_path / ".env")

    async with app.run_test(size=(100, 60)) as pilot:
        await pilot.pause()
        await pilot.click("#continue")  # credentials -> mailbox
        await pilot.pause()

        await pilot.click("#continue")  # host still blank

        assert pilot.app.screen.query_one("#host", Input) is not None
        assert "required" in pilot.app.screen.query_one("#mailbox_error", Static).content

        # Button's press-animation guard ignores a second click on the same
        # button within ~0.2s (Textual's `active_effect_duration`) -- wait it out.
        await pilot.pause(0.3)
        pilot.app.screen.query_one("#host", Input).value = "imap.example.com"
        await pilot.click("#continue")
        await pilot.pause()

        assert app.config.mailbox.host == "imap.example.com"


async def test_wizard_keeps_hand_set_tls_settings(tmp_path):
    """S1.6: the wizard has no tls widgets, so a save must not erase them."""
    config_path = tmp_path / "config.yaml"
    env_path = tmp_path / ".env"
    config_path.write_text(
        """
mailbox:
  host: 127.0.0.1
  port: 1143
  tls: starttls
  tls_ca_file: /tmp/bridge.pem
categories:
  invoice:
    description: Invoice
"""
    )
    app = JevMailConfigApp(config_path, env_path, load_config(config_path, env_path))

    async with app.run_test(size=(100, 60)) as pilot:
        await pilot.pause()
        await pilot.click("#continue")  # credentials, fields unchanged
        await pilot.pause()
        await pilot.click("#continue")  # mailbox, no field changed
        await pilot.pause()
        await pilot.press("s")  # categories: Save & exit

    written = config_path.read_text()
    assert "tls: starttls" in written
    assert "tls_ca_file: /tmp/bridge.pem" in written


async def test_wizard_keeps_the_gmail_backend(tmp_path):
    """GH-4 S3.5"""
    config_path = tmp_path / "config.yaml"
    env_path = tmp_path / ".env"
    env_path.write_text("IMAP_USERNAME=me@example.com\n")
    config_path.write_text(
        """
mailbox:
  backend: gmail
  username: ${IMAP_USERNAME}
categories:
  invoice:
    description: Invoice
"""
    )
    app = JevMailConfigApp(config_path, env_path, load_config(config_path, env_path))

    async with app.run_test(size=(100, 60)) as pilot:
        await pilot.pause()
        await pilot.click("#continue")  # credentials, fields unchanged
        await pilot.pause()
        await pilot.click("#continue")  # mailbox, no field changed
        await pilot.pause()
        await pilot.press("s")  # categories: Save & exit

    import yaml

    assert yaml.safe_load(config_path.read_text())["mailbox"]["backend"] == "gmail"
