"""Cross-package parity test: a message signed by this SDK's
`aiops_enabler.signing` module must verify successfully against the
backend's ACTUAL verifier function
(`app.modules.agents.hmac_auth.verify_signature`), imported directly from
`/backend` in this monorepo — not a hand-reimplementation merely guessed to
match. This is the strongest form of parity check available: it exercises
the real production verifier the backend's `require_agent_api_key`
dependency calls on every signed request, not a copy of its logic.

This works without installing the backend's FastAPI/SQLAlchemy/etc.
dependency set because `app.modules.agents.hmac_auth` (and every package
`__init__.py` on the import path to it: `app`, `app.modules`,
`app.modules.agents`) has zero third-party imports — stdlib
`hashlib`/`hmac`/`datetime` only. Only `sys.path` needs to include
`/backend` for the import to resolve.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType

import pytest

from aiops_enabler.signing import compute_signature, secret_hash

_BACKEND_DIR = Path(__file__).resolve().parents[3] / "backend"
_HMAC_AUTH_PATH = _BACKEND_DIR / "app" / "modules" / "agents" / "hmac_auth.py"


def _import_backend_hmac_auth() -> ModuleType:
    if not _HMAC_AUTH_PATH.exists():
        pytest.skip(
            f"backend not found at {_BACKEND_DIR!s} (expected monorepo layout with "
            "sdk/python and backend as siblings) — skipping the cross-package parity "
            "check; see this module's docstring for hand-verification notes."
        )
    if str(_BACKEND_DIR) not in sys.path:
        sys.path.insert(0, str(_BACKEND_DIR))
    from app.modules.agents import hmac_auth

    return hmac_auth


def test_sdk_signature_matches_backend_compute_signature_byte_for_byte() -> None:
    backend_hmac_auth = _import_backend_hmac_auth()

    secret = "test-agent-secret-value"
    timestamp = str(int(datetime.now(timezone.utc).timestamp()))
    body = b'{"event_type":"task_started","task_id":"abc123"}'

    sdk_signature = compute_signature(secret=secret, timestamp=timestamp, body=body)
    backend_signature = backend_hmac_auth.compute_signature(
        secret_hash=secret_hash(secret), timestamp=timestamp, body=body
    )

    assert sdk_signature == backend_signature


def test_sdk_signed_message_verifies_against_the_backends_real_verifier() -> None:
    """The strongest parity check: feed a message signed by the SDK
    straight into the backend's real `verify_signature` (the exact
    function `require_agent_api_key` calls in production) and assert it
    accepts it."""
    backend_hmac_auth = _import_backend_hmac_auth()

    secret = "another-test-secret"  # nosec B105 - test fixture literal
    timestamp = str(int(datetime.now(timezone.utc).timestamp()))
    body = (
        b'{"event_type":"task_completed","task_id":"abc123","outcome":"success","duration_ms":1420}'
    )

    signature = compute_signature(secret=secret, timestamp=timestamp, body=body)

    assert backend_hmac_auth.verify_signature(
        secret_hash=secret_hash(secret),
        timestamp=timestamp,
        body=body,
        signature=signature,
    )


def test_tampered_body_fails_the_backends_real_verifier() -> None:
    backend_hmac_auth = _import_backend_hmac_auth()

    secret = "yet-another-secret"  # nosec B105 - test fixture literal
    timestamp = str(int(datetime.now(timezone.utc).timestamp()))
    signed_body = b'{"task_id":"abc123"}'
    tampered_body = b'{"task_id":"xyz999"}'

    signature = compute_signature(secret=secret, timestamp=timestamp, body=signed_body)

    assert not backend_hmac_auth.verify_signature(
        secret_hash=secret_hash(secret),
        timestamp=timestamp,
        body=tampered_body,
        signature=signature,
    )


def test_stale_timestamp_fails_the_backends_real_verifier() -> None:
    backend_hmac_auth = _import_backend_hmac_auth()

    secret = "stale-timestamp-secret"  # nosec B105 - test fixture literal
    # 10 minutes ago — outside the backend's default 300s freshness window.
    stale_timestamp = str(int(datetime.now(timezone.utc).timestamp()) - 600)
    body = b'{"task_id":"abc123"}'

    signature = compute_signature(secret=secret, timestamp=stale_timestamp, body=body)

    assert not backend_hmac_auth.verify_signature(
        secret_hash=secret_hash(secret),
        timestamp=stale_timestamp,
        body=body,
        signature=signature,
    )


def test_secret_hash_matches_backends_agent_api_key_secret_hash_scheme() -> None:
    """`app.models.agent_api_key.AgentApiKey.secret_hash` is documented as
    `sha256(raw_secret).hexdigest()` — confirm the SDK's `secret_hash()`
    helper derives the identical value a real issued key's stored hash
    would be, independent of the HMAC signing path above."""
    import hashlib

    secret = "issued-agent-secret-abc"  # nosec B105 - test fixture literal
    assert secret_hash(secret) == hashlib.sha256(secret.encode("utf-8")).hexdigest()
