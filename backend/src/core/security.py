"""Auth / security helpers (Phase 2 — placeholders for Stage 1).

Stage 1 ships only the password-hashing primitives so health and readiness
checks can be wired without exposing a real auth surface. JWT token issuance,
RBAC, and OAuth integration land in Phase 2.

TODO(Phase 2): JWT issue/verify, dependency for current user, role guards.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets


def hash_password(password: str, *, salt: str | None = None) -> tuple[str, str]:
    """Hash a password with PBKDF2-HMAC-SHA256.

    Stage 1 placeholder. Phase 2 should swap to Argon2id via ``argon2-cffi``.

    Args:
        password: Plain-text password.
        salt: Hex salt; if ``None`` a fresh 32-byte salt is generated.

    Returns:
        Tuple of ``(hex_digest, hex_salt)``.
    """
    if salt is None:
        salt = secrets.token_hex(32)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        bytes.fromhex(salt),
        iterations=200_000,
    )
    return digest.hex(), salt


def verify_password(password: str, *, expected_digest: str, salt: str) -> bool:
    """Constant-time check of ``password`` against ``expected_digest``."""
    actual_digest, _ = hash_password(password, salt=salt)
    return hmac.compare_digest(actual_digest, expected_digest)
