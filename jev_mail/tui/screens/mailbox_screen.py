from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Input, Label, Static

from jev_mail.config import MailboxConfig


class MailboxScreen(Screen[MailboxConfig]):
    """Second screen: which mailbox/folder to watch. Credentials already live
    in .env from the previous screen -- only non-secret settings live here."""

    def __init__(self, mailbox: MailboxConfig):
        super().__init__()
        self._mailbox = mailbox

    def compose(self) -> ComposeResult:
        yield Header()
        with Container(id="panel"):
            with VerticalScroll():
                yield Static("\U0001f4ec  Mailbox", classes="title")
                yield Static("Step 2 of 3 -- which inbox and folder should jev-mail watch?", classes="subtitle")

                yield Label("IMAP host", classes="field-label")
                yield Input(value=self._mailbox.host, placeholder="imap.gmail.com", id="host")
                yield Label("Port", classes="field-label")
                yield Input(value=str(self._mailbox.port), id="port")
                yield Label("Folder to watch", classes="field-label")
                yield Input(value=self._mailbox.folder, id="folder")
                yield Label("Poll interval in seconds (used by `watch` if the server has no IDLE support)", classes="field-label")
                yield Input(value=str(self._mailbox.poll_interval_seconds), id="poll_interval")
                yield Label("Max emails to classify per run/poll (caps cost and time on a big backlog)", classes="field-label")
                yield Input(value=str(self._mailbox.max_emails_per_run), id="max_emails_per_run")
            with Vertical(classes="actions-dock"):
                yield Static("", id="mailbox_error", classes="error")
                with Horizontal():
                    yield Button("Continue", id="continue", variant="primary")
        yield Footer()

    def on_mount(self) -> None:
        self.app.sub_title = "Step 2 of 3 · Mailbox"

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id != "continue":
            return
        host = self.query_one("#host", Input).value.strip()
        if not host:
            self.query_one("#mailbox_error", Static).update("IMAP host is required, e.g. imap.gmail.com -- see the README's IMAP section.")
            return
        self.dismiss(
            MailboxConfig(
                host=host,
                port=int(self.query_one("#port", Input).value or 993),
                username=self._mailbox.username,
                password=self._mailbox.password,
                folder=self.query_one("#folder", Input).value.strip() or "INBOX",
                poll_interval_seconds=int(self.query_one("#poll_interval", Input).value or 60),
                max_emails_per_run=int(self.query_one("#max_emails_per_run", Input).value or 25),
                tls=self._mailbox.tls,
                tls_ca_file=self._mailbox.tls_ca_file,
            )
        )
