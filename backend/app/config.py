import logging
import os
import socket
from pathlib import Path
from typing import Mapping
from dotenv import load_dotenv
from pydantic import BaseModel, SecretStr, field_validator

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
dotenv_path = ROOT_DIR / ".env"
if dotenv_path.exists():
    load_dotenv(dotenv_path)

logger = logging.getLogger("travel_agent_config")


def _env_flag(name: str, default: bool) -> bool:
    """Read a boolean environment flag, defaulting when unset."""
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() == "true"


class Settings(BaseModel):
    PROJECT_NAME: str = "Vietnam Travel Agent API"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"
    GITHUB_TOKEN: str = os.getenv("GITHUB_TOKEN", "")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "gpt-4o-mini")
    # Required, with no default: the endpoint is a property of the deployment,
    # not of the source. An unset value is the empty string, and the OpenAI SDK
    # keeps it as-is (it substitutes its own endpoint only when `base_url` is
    # omitted), so the first model call fails with APIConnectionError rather than
    # quietly reaching a different provider. Do not add a fallback here.
    # `.strip()` matters: whitespace becomes `%20%20%20/` in the base URL.
    GITHUB_MODELS_URL: str = os.getenv("GITHUB_MODELS_URL", "").strip()

    # Bound the provider call. The SDK default is 600s with 2 retries, and
    # `chat_endpoint` is a sync def, so an unbounded call holds an anyio
    # threadpool token for minutes and degrades every sync endpoint.
    LLM_REQUEST_TIMEOUT_SECONDS: float = float(
        os.getenv("LLM_REQUEST_TIMEOUT_SECONDS", "20")
    )
    LLM_MAX_RETRIES: int = int(os.getenv("LLM_MAX_RETRIES", "1"))

    # Authentication credentials
    LOCAL_AUTH_TOKENS_JSON: SecretStr = SecretStr(
        os.getenv("LOCAL_AUTH_TOKENS_JSON", "{}")
    )
    MAX_REQUEST_BODY_BYTES: int = int(os.getenv("MAX_REQUEST_BODY_BYTES", "1048576"))
    ALLOWED_ORIGINS: str = os.getenv(
        "ALLOWED_ORIGINS",
        os.getenv("ALLOWED_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"),
    )

    @property
    def ALLOWED_CORS_ORIGINS(self) -> str:
        """Backward-compatible alias for ALLOWED_ORIGINS."""
        return self.ALLOWED_ORIGINS

    @ALLOWED_CORS_ORIGINS.setter
    def ALLOWED_CORS_ORIGINS(self, value: str) -> None:
        self.ALLOWED_ORIGINS = value

    @field_validator("ALLOWED_ORIGINS", mode="after")
    @classmethod
    def validate_no_wildcard(cls, v: str) -> str:
        origins = [part.strip() for part in v.split(",") if part.strip()]
        if "*" in origins:
            raise ValueError("Wildcard CORS origin '*' is prohibited.")
        return v

    # PostgreSQL configuration
    DATABASE_URL: str = os.getenv("DATABASE_URL", "")
    PG_HOST: str = os.getenv("PG_HOST", "localhost")
    PG_PORT: int = int(os.getenv("PG_PORT", "5433"))
    PG_DB: str = os.getenv("PG_DB", "travel_agent")
    PG_USER: str = os.getenv("PG_USER", "travel_agent")
    PG_PASSWORD: SecretStr = SecretStr(os.getenv("POSTGRES_PASSWORD", ""))

    # Background worker configuration (ADR 0028). The worker needs its own role
    # because it must claim a cross-owner outbox queue, while the runtime role
    # must not. Keep these separate from the `PG_*` runtime parts.
    WORKER_DATABASE_URL: str = os.getenv("WORKER_DATABASE_URL", "")
    PG_WORKER_USER: str = os.getenv("PG_WORKER_USER", "travel_worker")
    PG_WORKER_PASSWORD: SecretStr = SecretStr(os.getenv("WORKER_DB_PASSWORD", ""))

    # Worker loop configuration (ADR 0029). Deliberately conservative defaults:
    # the interval and batch size are calibrated by observing a real queue, not
    # asserted from a guess. The batch size also bounds how long a shutdown can
    # take, because the loop stops between batches rather than mid-event.
    # The lease owner identity (ADR 0032). This must distinguish processes:
    # `mark_failed`, `mark_succeeded` and `cancel_events(lease_owner=…)` all key on
    # `holder == lease_owner`, so a shared value makes two replicas
    # indistinguishable and lets one replica's lease loss clear or cancel the
    # other's row. The previous default was the constant `"memory_worker_1"`, which
    # meant the defect appeared the first time the worker was scaled horizontally.
    #
    # `or ""` then `.strip()` matters twice over: `os.getenv` returns an empty
    # string for a present-but-blank variable, and an empty lease owner is worse
    # than a shared constant — every blank-configured replica would collide. A
    # configured value is honoured, so an operator may choose a stable identity and
    # owns its uniqueness.
    WORKER_ID: str = (os.getenv("WORKER_ID") or "").strip() or (
        f"{socket.gethostname()}-{os.getpid()}"
    )
    WORKER_POLL_INTERVAL_SECONDS: float = float(
        os.getenv("WORKER_POLL_INTERVAL_SECONDS", "5.0")
    )
    WORKER_BATCH_SIZE: int = int(os.getenv("WORKER_BATCH_SIZE", "10"))
    WORKER_LEASE_SECONDS: float = float(os.getenv("WORKER_LEASE_SECONDS", "30.0"))
    WORKER_MAX_ATTEMPTS: int = int(os.getenv("WORKER_MAX_ATTEMPTS", "3"))
    WORKER_BACKOFF_BASE_SECONDS: float = float(
        os.getenv("WORKER_BACKOFF_BASE_SECONDS", "2.0")
    )
    # Where the worker process publishes its heartbeat (ADR 0029: liveness is the
    # process plus a heartbeat, because the worker deliberately has no HTTP
    # surface). Unset keeps the worker as it was — the beat stays in the poll log
    # line — so existing deployments see no new file. Set, the path's mtime is
    # touched once per completed batch, and a container healthcheck reads its age
    # against one poll interval plus one batch duration. A path whose directory
    # does not exist fails startup loudly rather than degrading to "no heartbeat".
    WORKER_HEARTBEAT_PATH: str = os.getenv("WORKER_HEARTBEAT_PATH", "")

    # Basic semantic memory write pipeline feature gates (ADR 0016 / ADR 0017)
    MEMORY_WRITE_PIPELINE_ENABLED: bool = _env_flag(
        "MEMORY_WRITE_PIPELINE_ENABLED", False
    )
    MEMORY_SHADOW_EXTRACT_ENABLED: bool = _env_flag(
        "MEMORY_SHADOW_EXTRACT_ENABLED", False
    )
    # The age at which a claimable outbox event means the Memory worker is not
    # draining, in seconds. Readiness reports DEGRADED beyond it.
    #
    # Generous by default on purpose. The poll interval is 5s and an extraction is
    # an unbounded model call, so a tight threshold would fire on a healthy
    # pipeline — which is the defect this replaces, one order of magnitude down.
    # Calibrate by observing a real queue; do not assert a number.
    MEMORY_BACKLOG_STALE_SECONDS: float = float(
        os.getenv("MEMORY_BACKLOG_STALE_SECONDS", "900")
    )
    MEMORY_WRITE_EVAL_FIXTURES_PATH: str = os.getenv(
        "MEMORY_WRITE_EVAL_FIXTURES_PATH",
        "docs/evaluation/fixtures/memory/write-pipeline-hotel-atmosphere-v0.1",
    )

    # Fail-closed guard: the runtime role must not be a superuser and must
    # not bypass row-level security, otherwise FORCE RLS is decorative. Only
    # set this for throwaway local development against a superuser-owned
    # database; production and Compose deployments must leave it false and
    # connect as the least-privilege `travel_app` role instead.
    ALLOW_PRIVILEGED_DB_ROLE: bool = _env_flag("ALLOW_PRIVILEGED_DB_ROLE", False)

    def database_dsn(self) -> str:
        """Resolve the one PostgreSQL DSN used by engine, Alembic, and probes.

        `DATABASE_URL` is the single source of truth when set, so a container
        deployment can point the backend at its database host without also
        having to supply `PG_*` parts. When it is absent or blank, the DSN is
        assembled from the explicit `PG_*` settings for local development.
        """
        explicit = (self.DATABASE_URL or "").strip()
        if explicit:
            return explicit
        password = (
            self.PG_PASSWORD.get_secret_value()
            if hasattr(self.PG_PASSWORD, "get_secret_value")
            else str(self.PG_PASSWORD)
        )
        return pg_dsn(
            password=password,
            host=self.PG_HOST,
            port=self.PG_PORT,
            db=self.PG_DB,
            user=self.PG_USER,
        )

    def worker_dsn(self) -> str:
        """Resolve the DSN the background worker connects with.

        Mirrors `database_dsn()`: an explicit `WORKER_DATABASE_URL` wins,
        otherwise the DSN is assembled from the shared host/port/db parts with
        the worker role as the default user.

        The role's privileges are deliberately **not** checked here, because
        that needs a connection and this method is pure resolution.
        `assert_least_privilege_role` performs the check at startup, exactly as
        it does for the runtime DSN, so the worker cannot silently run as a
        superuser or a `BYPASSRLS` role either.
        """
        explicit = (self.WORKER_DATABASE_URL or "").strip()
        if explicit:
            return explicit
        password = (
            self.PG_WORKER_PASSWORD.get_secret_value()
            if hasattr(self.PG_WORKER_PASSWORD, "get_secret_value")
            else str(self.PG_WORKER_PASSWORD)
        )
        return pg_dsn(
            password=password,
            host=self.PG_HOST,
            port=self.PG_PORT,
            db=self.PG_DB,
            user=self.PG_WORKER_USER,
        )


def pg_dsn(password: str, host: str, port: int, db: str, user: str) -> str:
    """Build a psycopg DSN from explicit parts.

    Built through `URL.create` rather than string interpolation. A password
    containing a URL-reserved character (`@`, `:`, `/`, `?`, `#`) interpolated
    into the template silently produces a DSN that points at a different host or
    fails to parse; `URL.create` percent-encodes each component, so the DSN always
    means what the parts say.
    """
    from sqlalchemy.engine import URL

    return URL.create(
        "postgresql+psycopg",
        username=user,
        password=password,
        host=host,
        port=int(port),
        database=db,
    ).render_as_string(hide_password=False)


class CredentialIsolationError(RuntimeError):
    """A process holds a database credential that belongs to another role."""


# role -> (the key this role owns, the key it must never receive)
_ROLE_DATABASE_KEYS: dict[str, tuple[str, str]] = {
    "api": ("DATABASE_URL", "WORKER_DATABASE_URL"),
    "worker": ("WORKER_DATABASE_URL", "DATABASE_URL"),
}


def assert_credential_isolation(
    role: str,
    environ: Mapping[str, str] | None = None,
) -> None:
    """Refuse to start when this process holds the other role's credential.

    ADR 0034. ADR 0029 made the background Memory worker its own process so that
    one process would not hold two database identities, and said so in a comment
    in `docker-compose.yml`. Nothing enforced it: both services carried
    `env_file: .env`, so the worker received `DATABASE_URL` — the API's
    `travel_app` credential — and the API would have received
    `WORKER_DATABASE_URL` had it been in that file. The boundary held only
    because nobody had broken it yet.

    A Compose allow-list fixes that deployment. This guard is what makes the
    boundary hold under *every* deployment mechanism — `docker run`, systemd, a
    shell with both exported — and what makes it assertable in a test rather
    than readable only in a YAML file. It is called from the process entry points
    only, never from a constructor, so building these objects in a test does not
    require a curated environment.

    The message names the offending *key* and never a value: this is raised at
    startup and therefore logged, and a log is less protected than the database.

    Raises:
        CredentialIsolationError: The other role's database key is present.
        ValueError: `role` is not a known role. A typo must not disable the guard.
    """
    if role not in _ROLE_DATABASE_KEYS:
        known = ", ".join(sorted(_ROLE_DATABASE_KEYS))
        raise ValueError(
            f"Unknown role {role!r} for credential isolation; expected one of {known}."
        )

    _, forbidden = _ROLE_DATABASE_KEYS[role]
    source = os.environ if environ is None else environ
    if forbidden in source:
        raise CredentialIsolationError(
            f"Refusing to start as the {role} process: the environment contains "
            f"{forbidden}, which names the other role's database credential. "
            f"Each process must receive only its own. Remove {forbidden} from this "
            f"process's environment rather than disabling this check."
        )


settings = Settings()


def get_settings() -> Settings:
    """Return the global Settings instance."""
    return settings
