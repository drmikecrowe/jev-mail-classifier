from __future__ import annotations

import argparse
import contextlib
import csv
import dataclasses
import imaplib
import sys
import time
from pathlib import Path

from jev_mail import census, tier0
from jev_mail.actions import run_action
from jev_mail.classify import classify, matched_categories
from jev_mail.config import AppConfig, ConfigError, MailboxConfig, load_config
from jev_mail.mailbox import GmailError, GmailMailbox, GraphError, GraphMailbox, MailBackend, Mailbox
from jev_mail.mailbox.gmail import authorize_gmail
from jev_mail.mailbox.graph import authorize_o365
from jev_mail.providers import ProviderError, get_jev_client
from jev_mail.providers.base import JevClient
from jev_mail.state import State


# The label (Proton, Gmail) or category (Office 365) you put on a BULK email after unsubscribing from its sender.
UNSUBSCRIBE_MARKER = "Unsubscribe"


def _paths(args: argparse.Namespace) -> tuple[Path, Path]:
    base = Path(args.dir)
    return base / "config.yaml", base / ".env"


def _load_senders(config_path: Path, config: AppConfig) -> dict[str, str]:
    return tier0.load_senders(config_path.parent / config.senders_file) if config.senders_file else {}


def _process_unprocessed(
    mailbox: MailBackend,
    client: JevClient,
    config: AppConfig,
    dry_run: bool,
    *,
    account: MailboxConfig | None = None,
    state: State | None = None,
    senders: dict[str, str] | None = None,
    review=None,
    summary: bool = False,
) -> int:
    """Process one batch; return the number of emails whose classify raised ProviderError.
    `review` is a csv.writer that gets one row per decided email; `summary` prints one count line at the end."""
    account = account or config.mailbox
    account_key = f"{account.host}/{account.username}"
    emails = mailbox.fetch_unprocessed(limit=account.max_emails_per_run)
    if len(emails) == account.max_emails_per_run:
        print(
            f"[jev-mail] hit max_emails_per_run ({account.max_emails_per_run}) -- "
            "there may be more unprocessed mail left for next run"
        )
    failed = tier0_count = jev_count = action_count = 0
    for mail in emails:
        hit = tier0.decide(mail, senders or {}, config)
        if hit is not None:
            tier0_count += 1
            category, source = hit
            probabilities = {category.name: 1.0}
            matched = [category]
        else:
            source = "jev"
            try:
                probabilities = classify(client, config, mail.state)
            except ProviderError as exc:
                # Left unmarked on purpose, so the next run retries it (GH-8, Decide 2).
                print(f"error: email uid {mail.uid}: {exc} -- left unprocessed, will retry next run", file=sys.stderr)
                failed += 1
                continue
            jev_count += 1
            matched = matched_categories(config, probabilities)
        if review is not None:
            review.writerow(
                [account_key, mail.uid, mail.subject, source, *(probabilities.get(c.name, "") for c in config.categories)]
            )
        # Only the first `move` among the matched categories, in config order, runs (GH-3 Decide 3, A12).
        matched_names = {c.name for c in matched}
        move_owner = next(
            (c.name for c in config.categories if c.name in matched_names and any(a.type == "move" for a in c.actions)),
            None,
        )
        moved = False
        applied = []

        if not matched and dry_run:
            print(f"[dry-run] {mail.subject!r}: no category matched")

        for category in matched:
            probability = probabilities[category.name]
            label = f"{probability:.2f}" if source == "jev" else source
            for action in category.actions:
                if action.type == "move":
                    if moved or category.name != move_owner:
                        continue
                    moved = True
                action_count += 1
                if dry_run:
                    print(f"[dry-run] {mail.subject!r}: {category.name} ({label}) -> {action.type}")
                else:
                    run_action(mailbox, mail, action, category.name, probability, account.folder_prefix)
                    applied.append({"category": category.name, **action.to_dict()})

        # Mark processed even when nothing matched -- otherwise a never-matching
        # email gets reclassified (and re-billed) on every future run.
        if not dry_run:
            mailbox.mark_processed(mail.uid)
            # The keyword stays the source of truth; the state row is only written after it.
            if state is not None:
                state.record(account_key, mail, source, probabilities, applied)
    if summary:
        print(
            f"[jev-mail] {account_key}: {len(emails)} fetched, {tier0_count} tier0, {jev_count} jev, "
            f"{action_count} actions{' (dry run)' if dry_run else ''}, {failed} failed"
        )
    return failed


def _open_mailbox(account: MailboxConfig, config_dir: Path):
    if account.backend == "gmail":
        return GmailMailbox(account, config_dir)
    if account.backend == "o365":
        return GraphMailbox(account, config_dir)
    return Mailbox(account)


def _mailbox_error_message(exc: Exception, account: MailboxConfig) -> str:
    if isinstance(exc, ConfigError):
        return str(exc)
    if isinstance(exc, GmailError):
        return f"Gmail API error for {account.username} -- {exc}"
    if isinstance(exc, GraphError):
        return f"Microsoft Graph error for {account.username} -- {exc}"
    if isinstance(exc, OSError):
        return f"couldn't connect to {account.host}:{account.port} -- {exc}"
    return f"IMAP error talking to {account.host} -- {exc}"


def cmd_configure(args: argparse.Namespace) -> int:
    from jev_mail.tui.app import JevMailConfigApp

    config_path, env_path = _paths(args)
    try:
        config = load_config(config_path, env_path)
    except ConfigError:
        config = None

    JevMailConfigApp(config_path, env_path, config).run()
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    config_path, env_path = _paths(args)
    if args.review:
        if not args.dry_run:
            print("error: --review needs --dry-run", file=sys.stderr)
            return 1
        base = Path(args.dir).resolve()
        if Path(args.review).resolve().is_relative_to(base):
            print(f"error: --review path must be outside {base} -- its rows hold real subjects", file=sys.stderr)
            return 1
    try:
        config = load_config(config_path, env_path)
        senders = _load_senders(config_path, config)
        client = get_jev_client(config.jev)
    except (ConfigError, ProviderError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    with open(args.review, "w", newline="") if args.review else contextlib.nullcontext() as review_file:
        review = None
        if review_file is not None:
            review = csv.writer(review_file)
            review.writerow(["account", "uid", "subject", "source", *(c.name for c in config.categories)])
        state = None
        failed = 0
        for account in config.accounts:
            try:
                with _open_mailbox(account, config_path.parent) as mailbox:
                    # Opened only after a connection succeeds, and never on a dry run.
                    if state is None and not args.dry_run:
                        state = State(config_path.parent / "state.db")
                    failed += _process_unprocessed(
                        mailbox,
                        client,
                        config,
                        args.dry_run,
                        account=account,
                        state=state,
                        senders=senders,
                        review=review,
                        summary=True,
                    )
            except (OSError, imaplib.IMAP4.error, ConfigError, GmailError, GraphError) as exc:
                # One account down (say, Proton Bridge not running) must not skip the others (GH-6).
                print(f"error: {_mailbox_error_message(exc, account)}", file=sys.stderr)
                failed += 1
    return 1 if failed else 0


def cmd_watch(args: argparse.Namespace) -> int:
    config_path, env_path = _paths(args)
    try:
        config = load_config(config_path, env_path)
        senders = _load_senders(config_path, config)
        client = get_jev_client(config.jev)
    except (ConfigError, ProviderError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if len(config.accounts) > 1:
        print("error: watch handles one account only -- use `run` for an accounts: list", file=sys.stderr)
        return 1

    print(f"watching {config.mailbox.folder}@{config.mailbox.host} (ctrl-c to stop)...")
    try:
        with _open_mailbox(config.mailbox, config_path.parent) as mailbox:
            state = None if args.dry_run else State(config_path.parent / "state.db")
            _process_unprocessed(mailbox, client, config, args.dry_run, state=state, senders=senders)
            while True:
                if mailbox.supports_idle():
                    mailbox.idle()
                    mailbox.idle_check(timeout=min(config.mailbox.poll_interval_seconds, 600))
                    mailbox.idle_done()
                else:
                    time.sleep(config.mailbox.poll_interval_seconds)
                _process_unprocessed(mailbox, client, config, args.dry_run, state=state, senders=senders)
    except (OSError, imaplib.IMAP4.error, ConfigError, GmailError, GraphError) as exc:
        print(f"error: {_mailbox_error_message(exc, config.mailbox)}", file=sys.stderr)
        return 1


def cmd_census(args: argparse.Namespace) -> int:
    config_path, env_path = _paths(args)
    try:
        config = load_config(config_path, env_path)
        senders = _load_senders(config_path, config)
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    rows: list[tuple[str, str]] = []
    for account in config.accounts:
        if args.folder and account.backend == "imap":
            account = dataclasses.replace(account, folder=args.folder)
        try:
            with _open_mailbox(account, config_path.parent) as mailbox:
                found = mailbox.fetch_senders(args.limit)
        except (OSError, imaplib.IMAP4.error, ConfigError, GmailError, GraphError) as exc:
            print(f"error: {_mailbox_error_message(exc, account)}", file=sys.stderr)
            return 1
        print(f"[census] {account.host}/{account.username}: {len(found)} emails")
        rows += found

    table = census.tally(rows, senders)
    out = config_path.parent / "sender-census.csv"
    with out.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(census.COLUMNS)
        writer.writerows(table)
    suggested = sum(1 for row in table if row[-1])
    print(f"[census] wrote {len(table)} senders to {out}; {suggested} suggested for unsubscribe")
    return 0


def cmd_clean(args: argparse.Namespace) -> int:
    """Trashes every BULK email from a sender with at least one BULK email carrying the UNSUBSCRIBE_MARKER label."""
    config_path, env_path = _paths(args)
    try:
        config = load_config(config_path, env_path)
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    bulk = next((c for c in config.categories if c.name == "BULK"), None)
    folder = next((a.folder for a in bulk.actions if a.type == "move"), None) if bulk else None
    if not folder:
        print("error: clean needs a BULK category with a move action", file=sys.stderr)
        return 1

    failed = 0
    for account in config.accounts:
        bulk_folder = account.folder_prefix + folder
        try:
            with _open_mailbox(account, config_path.parent) as mailbox:
                mail = mailbox.folder_mail(bulk_folder, UNSUBSCRIBE_MARKER)
                marked = {tier0.sender_address(sender) for _, sender, is_marked in mail if is_marked} - {""}
                doomed = [(uid, tier0.sender_address(sender)) for uid, sender, _ in mail if tier0.sender_address(sender) in marked]
                for address in sorted(marked):
                    count = sum(1 for _, a in doomed if a == address)
                    print(f"[{'dry-run' if args.dry_run else 'clean'}] {address}: {count} emails in {bulk_folder} -> Trash")
                if doomed and not args.dry_run:
                    mailbox.trash(bulk_folder, [uid for uid, _ in doomed])
        except (OSError, imaplib.IMAP4.error, ConfigError, GmailError, GraphError) as exc:
            print(f"error: {_mailbox_error_message(exc, account)}", file=sys.stderr)
            failed += 1
            continue
        print(f"[clean] {account.host}/{account.username}: {len(marked)} senders, {len(doomed)} emails")
    return 1 if failed else 0


def cmd_auth_gmail(args: argparse.Namespace) -> int:
    try:
        token = authorize_gmail(Path(args.dir))
    except (ConfigError, GmailError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"saved the Gmail token to {token}")
    return 0


def cmd_auth_o365(args: argparse.Namespace) -> int:
    try:
        token = authorize_o365(Path(args.dir))
    except GraphError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"saved the Office 365 token to {token}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="jev-mail", description="Classify your inbox with Jev.")
    parser.add_argument("--dir", default=".", help="directory holding config.yaml / .env (default: cwd)")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("configure", help="open the TUI to build/edit config.yaml")

    run_parser = subparsers.add_parser("run", help="classify unprocessed mail once and exit")
    run_parser.add_argument("--dry-run", action="store_true", help="classify and print, without applying any action")
    run_parser.add_argument("--review", help="with --dry-run, write one CSV row per email to this path")

    watch_parser = subparsers.add_parser("watch", help="keep classifying new mail as it arrives")
    watch_parser.add_argument("--dry-run", action="store_true", help="classify and print, without applying any action")

    census_parser = subparsers.add_parser("census", help="count each sender's mail from headers, no Jev call, into sender-census.csv")
    census_parser.add_argument("--limit", type=int, default=2000, help="newest emails to read per account (default: 2000)")
    census_parser.add_argument("--folder", help="IMAP folder to read in place of the account's folder, e.g. 'All Mail'")

    clean_parser = subparsers.add_parser(
        "clean", help=f"trash BULK mail from every sender you marked with the {UNSUBSCRIBE_MARKER!r} label"
    )
    clean_parser.add_argument("--dry-run", action="store_true", help="list what would be trashed, without moving anything")

    subparsers.add_parser("auth-gmail", help="sign in to Gmail once and save the token beside config.yaml")
    subparsers.add_parser("auth-o365", help="sign in to Office 365 once and save the token beside config.yaml")

    return parser


def main() -> None:
    args = build_parser().parse_args()
    config_path, _ = _paths(args)

    if args.command is None:
        args.command = "configure" if not config_path.exists() else "run"
        if args.command == "run":
            args.dry_run = False
            args.review = None

    commands = {
        "configure": cmd_configure,
        "run": cmd_run,
        "watch": cmd_watch,
        "census": cmd_census,
        "clean": cmd_clean,
        "auth-gmail": cmd_auth_gmail,
        "auth-o365": cmd_auth_o365,
    }
    sys.exit(commands[args.command](args))


if __name__ == "__main__":
    main()
