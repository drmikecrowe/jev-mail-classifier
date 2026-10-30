from jev_mail.mailbox.base import Email, MailBackend
from jev_mail.mailbox.gmail import GmailError, GmailMailbox
from jev_mail.mailbox.graph import GraphError, GraphMailbox
from jev_mail.mailbox.imap import PROCESSED_KEYWORD, Mailbox

__all__ = ["PROCESSED_KEYWORD", "Email", "GmailError", "GmailMailbox", "GraphError", "GraphMailbox", "MailBackend", "Mailbox"]
