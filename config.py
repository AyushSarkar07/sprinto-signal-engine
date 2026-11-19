"""Central configuration. Every value comes from the environment (.env); nothing secret is hardcoded."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, "") or default)
    except ValueError:
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, "") or default)
    except ValueError:
        return default


@dataclass
class Settings:
    """Runtime settings. Secrets are stored here but never logged (see `describe`)."""

    anthropic_api_key: str = ""
    anthropic_model: str = "claude-opus-5-5"
    hunter_api_key: str = ""
    hunter_max_calls: int = 10
    contact_providers: list[str] = field(default_factory=lambda: ["hunter", "manual", "website"])
    gmail_client_id: str = ""
    gmail_client_secret: str = ""
    gmail_token_path: Path = ROOT / "credentials" / "token.json"
    email_backend: str = "gmail"
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_app_password: str = ""
    test_to_email: str = ""
    sender_name: str = ""
    dry_run: bool = True
    review_gate: bool = True
    log_level: str = "INFO"
    max_research_rounds: int = 2
    initial_page_budget: int = 4
    research_page_budget: int = 4
    request_delay: float = 1.0
    request_timeout: float = 15.0
    use_playwright: bool = False
    search_provider: str = ""
    serper_api_key: str = ""
    use_claude: bool = True
    output_dir: Path = ROOT / "output"
    prompts_dir: Path = ROOT / "prompts"
    contacts_csv: Path = ROOT / "data" / "contacts_override.csv"
    outcomes_csv: Path = ROOT / "data" / "outcomes.csv"
    enrichment_csv: Path = ROOT / "data" / "company_enrichment.csv"
    revenue_assumptions: Path = ROOT / "data" / "revenue_assumptions.json"

    @property
    def cache_dir(self) -> Path:
        return self.output_dir / "cache"

    @property
    def claude_enabled(self) -> bool:
        return self.use_claude and bool(self.anthropic_api_key)

    def describe(self) -> dict[str, str]:
        """Which integrations are configured — reports presence only, never values."""
        def present(v: str) -> str:
            return "configured" if v else "missing"

        return {
            "Claude API": present(self.anthropic_api_key) + (f" (model {self.anthropic_model})" if self.anthropic_api_key else ""),
            "Hunter.io": present(self.hunter_api_key),
            "Manual contacts CSV": "present" if self.contacts_csv.exists() else "missing",
            "Gmail OAuth client": present(self.gmail_client_id and self.gmail_client_secret),
            "Gmail token": "present" if self.gmail_token_path.exists() else "missing",
            "SMTP": present(self.smtp_user and self.smtp_app_password),
            "TEST_TO_EMAIL": present(self.test_to_email),
            "Search provider": self.search_provider or "none",
            "DRY_RUN": str(self.dry_run).lower(),
        }


def load_settings(env_file: Path | None = None) -> Settings:
    load_dotenv(env_file or ROOT / ".env", override=False)
    token_path = Path(os.getenv("GMAIL_TOKEN_PATH") or "credentials/token.json")
    if not token_path.is_absolute():
        token_path = ROOT / token_path
    return Settings(
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", "").strip(),
        anthropic_model=os.getenv("ANTHROPIC_MODEL", "").strip() or "claude-opus-5-5",
        hunter_api_key=os.getenv("HUNTER_API_KEY", "").strip(),
        hunter_max_calls=_int("HUNTER_MAX_CALLS_PER_RUN", 10),
        contact_providers=[p.strip() for p in (os.getenv("CONTACT_PROVIDERS") or "hunter,manual,website").split(",") if p.strip()],
        gmail_client_id=os.getenv("GMAIL_CLIENT_ID", "").strip(),
        gmail_client_secret=os.getenv("GMAIL_CLIENT_SECRET", "").strip(),
        gmail_token_path=token_path,
        email_backend=(os.getenv("EMAIL_BACKEND") or "gmail").strip().lower(),
        smtp_host=os.getenv("SMTP_HOST", "smtp.gmail.com"),
        smtp_port=_int("SMTP_PORT", 587),
        smtp_user=os.getenv("SMTP_USER", "").strip(),
        smtp_app_password=os.getenv("SMTP_APP_PASSWORD", "").strip(),
        test_to_email=os.getenv("TEST_TO_EMAIL", "").strip(),
        sender_name=os.getenv("SENDER_NAME", "").strip(),
        dry_run=_bool("DRY_RUN", True),
        review_gate=_bool("REVIEW_GATE", True),
        log_level=(os.getenv("LOG_LEVEL") or "INFO").upper(),
        max_research_rounds=min(_int("MAX_SECONDARY_RESEARCH_ROUNDS", 2), 2),
        initial_page_budget=_int("INITIAL_PAGE_BUDGET", 4),
        research_page_budget=_int("RESEARCH_PAGE_BUDGET", 4),
        request_delay=_float("REQUEST_DELAY_SECONDS", 1.0),
        request_timeout=_float("REQUEST_TIMEOUT_SECONDS", 15.0),
        use_playwright=_bool("USE_PLAYWRIGHT", False),
        search_provider=(os.getenv("SEARCH_PROVIDER") or "").strip().lower(),
        serper_api_key=os.getenv("SERPER_API_KEY", "").strip(),
        **({"output_dir": Path(os.environ["OUTPUT_DIR"])} if os.getenv("OUTPUT_DIR") else {}),
    )


class SecretRedactingFilter(logging.Filter):
    """Belt-and-braces: scrub any configured secret value that slips into a log line."""

    def __init__(self, settings: Settings):
        super().__init__()
        self.secrets = [s for s in (settings.anthropic_api_key, settings.hunter_api_key, settings.gmail_client_secret,
                                    settings.smtp_app_password, settings.serper_api_key) if s and len(s) > 6]

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        for s in self.secrets:
            if s in msg:
                record.msg = msg.replace(s, "***REDACTED***")
                record.args = ()
                msg = record.msg
        return True


def setup_logging(settings: Settings) -> None:
    settings.output_dir.mkdir(parents=True, exist_ok=True)
    handler_file = logging.FileHandler(settings.output_dir / "pipeline.log", encoding="utf-8")
    handler_console = logging.StreamHandler()
    handler_console.setLevel(logging.WARNING)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    redact = SecretRedactingFilter(settings)
    for h in (handler_file, handler_console):
        h.setFormatter(fmt)
        h.addFilter(redact)
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(settings.log_level)
    root.addHandler(handler_file)
    root.addHandler(handler_console)
    for noisy in ("urllib3", "httpx", "googleapiclient", "anthropic"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
