"""The password gate protects a deployment that carries a real API key."""

from __future__ import annotations

import pytest

from core import gate


def test_gate_is_off_when_no_password_is_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(gate.PASSWORD_ENV, raising=False)
    assert not gate.is_enabled()
    assert gate.matches("bất kỳ")


def test_gate_is_on_when_a_password_is_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(gate.PASSWORD_ENV, "mở-cửa")
    assert gate.is_enabled()
    assert gate.matches("mở-cửa")
    assert gate.matches("  mở-cửa  ")
    assert not gate.matches("sai")
    assert not gate.matches("")


def test_blank_password_env_does_not_enable_the_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(gate.PASSWORD_ENV, "   ")
    assert not gate.is_enabled()


def _app(monkeypatch: pytest.MonkeyPatch, password: str | None):
    from pathlib import Path

    from streamlit.testing.v1 import AppTest

    if password is None:
        monkeypatch.delenv(gate.PASSWORD_ENV, raising=False)
    else:
        monkeypatch.setenv(gate.PASSWORD_ENV, password)
    app_file = Path(__file__).resolve().parents[1] / "app.py"
    return AppTest.from_file(str(app_file), default_timeout=60).run()


def test_gate_hides_the_app_until_the_password_is_right(monkeypatch: pytest.MonkeyPatch) -> None:
    app = _app(monkeypatch, "bí-mật-2026")
    assert app.get("text_input"), "Phải hiện ô nhập mật khẩu"
    assert not any("hành trình" in str(item.value).lower() for item in app.get("html"))

    app.text_input[0].set_value("sai")
    app.button[0].click().run()
    assert app.error
    assert not app.session_state.get(gate.UNLOCKED_KEY)


def test_correct_password_unlocks_the_app(monkeypatch: pytest.MonkeyPatch) -> None:
    app = _app(monkeypatch, "bí-mật-2026")
    app.text_input[0].set_value("bí-mật-2026")
    app.button[0].click().run()
    assert app.session_state.get(gate.UNLOCKED_KEY) is True
    assert not app.exception


def test_no_password_configured_means_no_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    app = _app(monkeypatch, None)
    assert not app.get("text_input")
    assert not app.exception
