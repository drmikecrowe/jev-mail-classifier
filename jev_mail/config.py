from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from dotenv import load_dotenv

_VAR_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")

ACTION_TYPES = ("tag", "move", "flag", "unflag", "mark_read", "mark_unread", "webhook")
TLS_MODES = ("ssl", "starttls")


class ConfigError(Exception):
    """Raised for a malformed or incomplete config.yaml."""


@dataclass
class Action:
    type: str
    value: str | None = None
    folder: str | None = None
    url: str | None = None

    @classmethod
    def from_dict(cls, data: dict) -> "Action":
        if data.get("type") not in ACTION_TYPES:
            raise ConfigError(f"unknown action type: {data.get('type')!r}")
        return cls(type=data["type"], value=data.get("value"), folder=data.get("folder"), url=data.get("url"))

    def to_dict(self) -> dict:
        out: dict = {"type": self.type}
        if self.value is not None:
            out["value"] = self.value
        if self.folder is not None:
            out["folder"] = self.folder
        if self.url is not None:
            out["url"] = self.url
        return out


@dataclass
class Category:
    name: str
    description: str
    threshold: float | None = None
    actions: list[Action] = field(default_factory=list)


@dataclass
class MailboxConfig:
    host: str
    port: int = 993
    username: str = ""
    password: str = ""
    folder: str = "INBOX"
    poll_interval_seconds: int = 60
    max_emails_per_run: int = 25
    tls: str = "ssl"
    tls_ca_file: str = ""


@dataclass
class JevSettings:
    provider: str = "auto"
    default_threshold: float = 0.6


@dataclass
class AppConfig:
    mailbox: MailboxConfig
    jev: JevSettings
    categories: list[Category]
    # Accounts 2 to n of an `accounts:` list. The wizard edits only `mailbox`,
    # so save_config writes these back from their raw ${VAR} entries.
    extra_accounts: list[MailboxConfig] = field(default_factory=list)
    extra_accounts_raw: list[dict] = field(default_factory=list)
    # The Tier 0 sender table, relative to the config directory; "" means no table.
    senders_file: str = ""

    @property
    def accounts(self) -> list[MailboxConfig]:
        return [self.mailbox, *self.extra_accounts]

    def category_threshold(self, category: Category) -> float:
        return category.threshold if category.threshold is not None else self.jev.default_threshold


def _interpolate(value: str, env: dict) -> str:
    def repl(match: re.Match) -> str:
        var = match.group(1)
        if var not in env:
            raise ConfigError(f"config references ${{{var}}} but it isn't set (check your .env)")
        return env[var]

    return _VAR_PATTERN.sub(repl, value) if isinstance(value, str) else value


def load_config(config_path: str | Path, env_path: str | Path | None = None) -> AppConfig:
    config_path = Path(config_path)
    load_dotenv(env_path or config_path.parent / ".env", override=False)

    if not config_path.exists():
        raise ConfigError(f"no config file at {config_path} — run `jev-mail configure` first")

    raw = yaml.safe_load(config_path.read_text()) or {}
    env = dict(os.environ)

    if "mailbox" in raw and "accounts" in raw:
        raise ConfigError("config has both mailbox: and accounts: — keep only one")
    if "accounts" in raw:
        accounts_raw = raw["accounts"] or []
        if not accounts_raw:
            raise ConfigError("accounts: is empty — list at least one account")
        if not isinstance(accounts_raw, list) or not all(isinstance(a, dict) for a in accounts_raw):
            raise ConfigError("accounts: must be a list of account blocks, each with host, username, password")
        accounts = [_load_account(a, env, f"accounts[{i}]") for i, a in enumerate(accounts_raw)]
        mailbox, extra_accounts, extra_accounts_raw = accounts[0], accounts[1:], accounts_raw[1:]
    else:
        mailbox = _load_account(raw.get("mailbox", {}), env, "mailbox")
        extra_accounts, extra_accounts_raw = [], []

    jev_raw = raw.get("jev", {})
    jev = JevSettings(
        provider=jev_raw.get("provider", "auto"),
        default_threshold=float(jev_raw.get("default_threshold", 0.6)),
    )

    categories = [
        Category(
            name=name,
            description=cat_raw.get("description", ""),
            threshold=cat_raw.get("threshold"),
            actions=[Action.from_dict(a) for a in cat_raw.get("actions", [])],
        )
        for name, cat_raw in (raw.get("categories") or {}).items()
    ]
    if not categories:
        raise ConfigError("config has no categories — run `jev-mail configure` to add some")

    return AppConfig(
        mailbox=mailbox,
        jev=jev,
        categories=categories,
        extra_accounts=extra_accounts,
        extra_accounts_raw=extra_accounts_raw,
        senders_file=str(raw.get("senders_file") or ""),
    )


def _load_account(mb_raw: dict, env: dict, label: str) -> MailboxConfig:
    mailbox = MailboxConfig(
        host=_interpolate(mb_raw.get("host", ""), env),
        port=int(mb_raw.get("port", 993)),
        username=_interpolate(mb_raw.get("username", ""), env),
        password=_interpolate(mb_raw.get("password", ""), env),
        folder=mb_raw.get("folder", "INBOX"),
        poll_interval_seconds=int(mb_raw.get("poll_interval_seconds", 60)),
        max_emails_per_run=int(mb_raw.get("max_emails_per_run", 25)),
        tls=mb_raw.get("tls", "ssl"),
        tls_ca_file=mb_raw.get("tls_ca_file", ""),
    )
    if mailbox.tls not in TLS_MODES:
        raise ConfigError(f"{label}.tls must be one of {', '.join(TLS_MODES)}, got {mailbox.tls!r}")
    if not mailbox.host:
        raise ConfigError(f"{label}.host is empty — run `jev-mail configure` and fill in the IMAP host")
    return mailbox


def save_config(config: AppConfig, config_path: str | Path) -> None:
    """Writes config.yaml. Mailbox credentials are always written as ${VAR}
    references, never as literal secrets, regardless of what's loaded in memory."""
    mailbox = {
        "host": config.mailbox.host,
        "port": config.mailbox.port,
        "username": "${IMAP_USERNAME}",
        "password": "${IMAP_PASSWORD}",
        "folder": config.mailbox.folder,
        "poll_interval_seconds": config.mailbox.poll_interval_seconds,
        "max_emails_per_run": config.mailbox.max_emails_per_run,
        "tls": config.mailbox.tls,
        "tls_ca_file": config.mailbox.tls_ca_file,
    }
    raw = {
        **(
            {"accounts": [mailbox, *config.extra_accounts_raw]}
            if config.extra_accounts_raw
            else {"mailbox": mailbox}
        ),
        "jev": {
            "provider": config.jev.provider,
            "default_threshold": config.jev.default_threshold,
        },
        **({"senders_file": config.senders_file} if config.senders_file else {}),
        "categories": {
            cat.name: {
                "description": cat.description,
                **({"threshold": cat.threshold} if cat.threshold is not None else {}),
                "actions": [a.to_dict() for a in cat.actions],
            }
            for cat in config.categories
        },
    }
    Path(config_path).write_text(yaml.safe_dump(raw, sort_keys=False, default_flow_style=False))


def read_env(env_path: str | Path) -> dict[str, str]:
    """Parses a .env file into a plain dict, or {} if it doesn't exist yet."""
    env_path = Path(env_path)
    values: dict[str, str] = {}
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            values[key.strip()] = val.strip()
    return values


def save_env(values: dict[str, str], env_path: str | Path) -> None:
    """Merges `values` into the .env file at `env_path`: a non-empty value
    sets that key, an empty value removes it. Keys not present in `values`
    at all are left untouched. (The credentials screen pre-fills every field
    from the existing .env, so an empty field here means the user actually
    cleared it -- not "didn't get around to typing anything.")"""
    env_path = Path(env_path)
    existing = read_env(env_path)
    for key, value in values.items():
        if value:
            existing[key] = value
        else:
            existing.pop(key, None)
    env_path.write_text("".join(f"{k}={v}\n" for k, v in existing.items()))
