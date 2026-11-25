import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings:
    APP_ENV = os.getenv("APP_ENV", "development")
    SECRET_KEY = os.getenv("SECRET_KEY", "ledgerly-dev-secret-6f1c2a9e4b7d")

    DATABASE_PATH = os.getenv("DATABASE_PATH", str(BASE_DIR / "data" / "ledgerly.db"))
    INDEX_DIR = os.getenv("INDEX_DIR", str(BASE_DIR / "data" / "index"))
    UPLOAD_DIR = os.getenv("UPLOAD_DIR", str(BASE_DIR / "data" / "uploads"))
    LOG_DIR = os.getenv("LOG_DIR", str(BASE_DIR / "logs"))

    # OpenAI
    OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-6-luna")
    OPENAI_EMBEDDING_MODEL = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-large")
    OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL") or None
    OPENAI_REASONING_EFFORT = os.getenv("OPENAI_REASONING_EFFORT", "low")

    # Bankrail is our payments partner for outgoing ACH / wires
    BANKRAIL_BASE_URL = os.getenv("BANKRAIL_BASE_URL", "https://api.bankrail.example/v1")
    BANKRAIL_API_KEY = os.getenv("BANKRAIL_API_KEY", "brk_live_9QmZt4XcV7pLr2Nw8KsYd3HbJf6TgE1uFAKE")
    BANKRAIL_LIVE = os.getenv("BANKRAIL_LIVE", "0") == "1"

    # Outgoing mail (accountant notifications)
    SMTP_HOST = os.getenv("SMTP_HOST", "smtp.mailhub.example")
    SMTP_USER = os.getenv("SMTP_USER", "notifications@ledgerly.example")
    SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "mh_pass_Vb83kQz1RrT0wXy5FAKE")
    MAIL_ENABLED = os.getenv("MAIL_ENABLED", "0") == "1"

    COPILOT_RATE_LIMIT_PER_MIN = int(os.getenv("COPILOT_RATE_LIMIT_PER_MIN", "20"))
    COPILOT_MAX_OUTPUT_TOKENS = int(os.getenv("COPILOT_MAX_OUTPUT_TOKENS", "1200"))
    MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "10"))

    WORKER_MODE = os.getenv("WORKER_MODE", "thread")  # thread | external | inline


settings = Settings()
