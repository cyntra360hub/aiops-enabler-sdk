"""HMAC-SHA256 request signing — must byte-for-byte match
`app.modules.agents.hmac_auth` in the backend (this SDK lives in the same
monorepo, `/backend`, as the API it's a client for).

Signing scheme (mirrored exactly — see the backend module's docstring,
`backend/app/modules/agents/hmac_auth.py`, for the canonical source of
truth; also documented in the monorepo's DECISIONS.md):

- Headers: ``X-Agent-Key-Id``, ``X-Agent-Timestamp`` (Unix seconds, as a
  string), ``X-Agent-Signature`` (lowercase hex HMAC-SHA256).
- Signed message: ``f"{timestamp}.".encode() + raw_request_body_bytes``.
- HMAC key: ``bytes.fromhex(secret_hash)``, where ``secret_hash`` is the
  SHA-256 hex digest of the agent's raw secret
  (``sha256(secret).hexdigest()``) — deterministic, so the backend (which
  only ever stores this digest, never the raw secret after issuance) and
  this SDK (which only ever has the raw secret) independently arrive at
  the same HMAC key without transmitting either the raw secret or the
  digest itself over the wire.

Parity with the backend is verified in ``tests/test_signing_parity.py`` by
importing the backend's actual ``app.modules.agents.hmac_auth.verify_signature``
function directly (a monorepo-local import — that module has zero
third-party dependencies, so this doesn't require installing the backend's
FastAPI/SQLAlchemy stack) and asserting a message signed by this module
verifies successfully against it.
"""

from __future__ import annotations

import hashlib
import hmac
import time

KEY_ID_HEADER = "X-Agent-Key-Id"
TIMESTAMP_HEADER = "X-Agent-Timestamp"
SIGNATURE_HEADER = "X-Agent-Signature"


def secret_hash(secret: str) -> str:
    """The hex-encoded SHA-256 digest of the raw agent secret — used
    directly as the HMAC key, matching ``AgentApiKey.secret_hash`` on the
    backend (see module docstring)."""
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def compute_signature(*, secret: str, timestamp: str, body: bytes) -> str:
    """Return the hex HMAC-SHA256 signature for ``body`` signed at
    ``timestamp``, using the raw agent ``secret``.

    Unlike the backend's ``hmac_auth.compute_signature`` (which takes an
    already-hashed ``secret_hash``, since the backend never has the raw
    secret after issuance), this takes the raw ``secret`` directly — the
    SDK caller has it, hashes it internally via `secret_hash`, and the two
    resulting HMAC keys are identical.
    """
    key = bytes.fromhex(secret_hash(secret))
    message = f"{timestamp}.".encode() + body
    return hmac.new(key, message, hashlib.sha256).hexdigest()


def sign_request(*, key_id: str, secret: str, body: bytes) -> dict[str, str]:
    """Build the full set of signed-request headers for ``body``."""
    timestamp = str(int(time.time()))
    signature = compute_signature(secret=secret, timestamp=timestamp, body=body)
    return {
        KEY_ID_HEADER: key_id,
        TIMESTAMP_HEADER: timestamp,
        SIGNATURE_HEADER: signature,
        "Content-Type": "application/json",
    }
