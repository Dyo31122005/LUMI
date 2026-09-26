"""Shared-password gate for public deployments.

This is a light barrier, not authentication. It exists so a demo that carries a
real `OPENAI_API_KEY` is not open to the whole internet burning the owner's
quota. There are no accounts, no sessions on the server and no rate limiting —
do not treat it as a security boundary.

The gate is active only when `LUMI_APP_PASSWORD` is set, so local development
needs no extra setup.
"""

from __future__ import annotations

import hmac
import os

PASSWORD_ENV = "LUMI_APP_PASSWORD"
UNLOCKED_KEY = "lumi_unlocked"


def required_password() -> str:
    return os.getenv(PASSWORD_ENV, "").strip()


def is_enabled() -> bool:
    return bool(required_password())


def matches(candidate: str) -> bool:
    """Constant-time comparison so the password cannot be guessed by timing."""

    expected = required_password()
    if not expected:
        return True
    # compare_digest rejects str with non-ASCII characters, so compare bytes.
    return hmac.compare_digest(candidate.strip().encode("utf-8"), expected.encode("utf-8"))


def render(st: object) -> bool:
    """Draw the gate. Returns True when the visitor may see the app.

    `st` is passed in rather than imported so this module stays importable
    from tests and the CLI without pulling Streamlit into them.
    """

    if not is_enabled():
        return True
    if st.session_state.get(UNLOCKED_KEY):  # type: ignore[attr-defined]
        return True

    st.title("LUMI")  # type: ignore[attr-defined]
    st.caption("Bản demo này cần mật khẩu để tránh bị dùng quá hạn mức API.")  # type: ignore[attr-defined]

    with st.form("lumi_gate"):  # type: ignore[attr-defined]
        candidate = st.text_input("Mật khẩu", type="password")  # type: ignore[attr-defined]
        submitted = st.form_submit_button("Vào xem", type="primary")  # type: ignore[attr-defined]

    if submitted:
        if matches(candidate):
            st.session_state[UNLOCKED_KEY] = True  # type: ignore[attr-defined]
            st.rerun()  # type: ignore[attr-defined]
        else:
            st.error("Mật khẩu chưa đúng.")  # type: ignore[attr-defined]

    return False
