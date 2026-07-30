"""Shared test setup.

Settings are populated from the environment *before* anything imports
``app.core.config``, so the suite runs identically on a laptop with a real
``.env`` and on CI with none. Every value here is a throwaway — no test may
depend on a real credential, and none of these reach a network.
"""
from __future__ import annotations

import os
import tempfile

# A syntactically-valid but meaningless RSA key path. Settings validates that
# *a* key source is configured, not that the key is usable, so a temp file is
# enough and keeps the suite from touching the real one.
_key = tempfile.NamedTemporaryFile(suffix=".pem", delete=False)  # noqa: SIM115
_key.write(b"-----BEGIN RSA PRIVATE KEY-----\ntest-only\n-----END RSA PRIVATE KEY-----\n")
_key.close()

os.environ.setdefault("GITHUB_APP_ID", "1")
os.environ.setdefault("GITHUB_APP_CLIENT_ID", "test-client-id")
os.environ.setdefault("GITHUB_APP_CLIENT_SECRET", "test-client-secret")
os.environ.setdefault("GITHUB_APP_WEBHOOK_SECRET", "test-webhook-secret")
os.environ.setdefault("SESSION_SECRET", "test-session-secret")
os.environ["GITHUB_APP_PRIVATE_KEY_PATH"] = _key.name
# Force the no-PAT branch by default; tests that care set it explicitly.
os.environ.setdefault("GITHUB_PAT", "")
