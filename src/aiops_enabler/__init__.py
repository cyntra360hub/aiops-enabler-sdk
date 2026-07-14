"""aiops-enabler — Python SDK for AiOps Enabler.

Wraps the events (``POST /api/v1/events``, F4) and ratings
(``POST /api/v1/ratings``, F3) HTTP APIs behind a tiny, ergonomic client::

    from aiops_enabler import AiOpsClient

    client = AiOpsClient(agent_key_id="...", agent_secret="...")
    client.task_started(task_id="abc123")
    client.task_completed(task_id="abc123", outcome="success", duration_ms=1420)

See ``aiops_enabler.signing`` for the HMAC request-signing scheme, which
mirrors the backend's ``app.modules.agents.hmac_auth`` module
byte-for-byte (parity verified in this package's own test suite,
``tests/test_signing_parity.py``, against the backend's real verifier).
"""

from aiops_enabler.client import AiOpsClient, AiOpsError

__all__ = ["AiOpsClient", "AiOpsError"]
__version__ = "0.1.0"
