"""Password hashing and email verification helpers."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import smtplib
from email.message import EmailMessage


_PASSWORD_ROUNDS = 240_000


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _PASSWORD_ROUNDS)
    return f"{salt.hex()}${digest.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        salt_hex, digest_hex = stored_hash.split("$", 1)
        expected = bytes.fromhex(digest_hex)
        actual = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), bytes.fromhex(salt_hex), _PASSWORD_ROUNDS
        )
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def create_otp() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def hash_otp(code: str) -> str:
    return hashlib.sha256(code.strip().encode()).hexdigest()


def send_otp(
    *,
    recipient: str,
    code: str,
    smtp: dict[str, str],
    subject: str = "Your Interview Coach verification code",
    message_text: str | None = None,
) -> None:
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = smtp["from_email"]
    message["To"] = recipient
    message.set_content(message_text or (
        f"Your Interview Coach verification code is {code}.\n\n"
        "It expires in 10 minutes. If you did not create this account, ignore this email."
    ))
    with smtplib.SMTP(smtp["host"], int(smtp.get("port", "587")), timeout=20) as server:
        server.starttls()
        server.login(smtp["username"], smtp["password"])
        server.send_message(message)
