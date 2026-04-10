"""Tests for authentication and JWT token handling."""
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

import jwt as pyjwt

from app.config import settings
from app.core.auth import create_session_token, decode_session_token


class TestJWTCreation:
    """Tests for create_session_token."""

    def test_creates_valid_token(self):
        token = create_session_token(
            user_id=1,
            email="test@example.com",
            is_admin=False,
            capillary_token="cap-tok",
            cluster="apac2",
            base_url="https://apac2.example.com",
        )
        payload = pyjwt.decode(token, settings.session_secret, algorithms=[settings.jwt_algorithm])
        assert payload["user_id"] == 1
        assert payload["email"] == "test@example.com"
        assert payload["is_admin"] is False
        assert payload["cluster"] == "apac2"

    def test_includes_iat_claim(self):
        token = create_session_token(
            user_id=1, email="t@t.com", is_admin=False,
            capillary_token="x", cluster="eu", base_url="",
        )
        payload = pyjwt.decode(token, settings.session_secret, algorithms=[settings.jwt_algorithm])
        assert "iat" in payload
        assert "exp" in payload
        assert payload["exp"] > payload["iat"]

    def test_admin_flag_preserved(self):
        token = create_session_token(
            user_id=2, email="admin@t.com", is_admin=True,
            capillary_token="x", cluster="eu", base_url="",
        )
        payload = pyjwt.decode(token, settings.session_secret, algorithms=[settings.jwt_algorithm])
        assert payload["is_admin"] is True


class TestJWTDecoding:
    """Tests for decode_session_token."""

    def test_decodes_valid_token(self):
        token = create_session_token(
            user_id=5, email="u@t.com", is_admin=False,
            capillary_token="c", cluster="apac", base_url="",
        )
        payload = decode_session_token(token)
        assert payload["user_id"] == 5

    def test_rejects_expired_token(self):
        payload = {
            "user_id": 1, "email": "t@t.com", "is_admin": False,
            "capillary_token": "x", "cluster": "eu", "base_url": "",
            "iat": datetime.now(timezone.utc) - timedelta(hours=48),
            "exp": datetime.now(timezone.utc) - timedelta(hours=1),
        }
        token = pyjwt.encode(payload, settings.session_secret, algorithm=settings.jwt_algorithm)
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            decode_session_token(token)
        assert exc_info.value.status_code == 401

    def test_rejects_tampered_token(self):
        token = create_session_token(
            user_id=1, email="t@t.com", is_admin=False,
            capillary_token="x", cluster="eu", base_url="",
        )
        # Tamper by signing with wrong secret
        payload = pyjwt.decode(token, settings.session_secret, algorithms=[settings.jwt_algorithm])
        tampered = pyjwt.encode(payload, "wrong-secret", algorithm=settings.jwt_algorithm)

        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            decode_session_token(tampered)
        assert exc_info.value.status_code == 401

    def test_rejects_garbage_token(self):
        from fastapi import HTTPException
        with pytest.raises(HTTPException):
            decode_session_token("not.a.real.token")


class TestSecretValidation:
    """Test that production refuses default secret."""

    def test_default_secret_rejected_in_production(self):
        from pydantic import ValidationError
        from app.config import Settings

        with pytest.raises(ValidationError, match="SESSION_SECRET"):
            Settings(env="production", session_secret="change-me-in-production")

    def test_custom_secret_accepted_in_production(self):
        from app.config import Settings
        s = Settings(env="production", session_secret="a-very-strong-random-secret-abc123")
        assert s.session_secret == "a-very-strong-random-secret-abc123"
