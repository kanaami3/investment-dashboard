"""Streamlit Cloud entry point with password gate.

Streamlit Community Cloud looks for ``streamlit_app.py`` at the repo root.
This wrapper:

1. Adds ``python/`` to ``sys.path`` so ``from stock_tools.* import ...`` works.
2. Imports ``stock_tools.dashboard`` (which calls ``st.set_page_config``
   exactly once as its first Streamlit-side-effect).
3. Renders a password prompt backed by ``st.secrets["app_password"]``.
4. Delegates to ``dashboard.main()`` on success.

Local usage (no password set in secrets) prints a warning and still gates.
Run locally with:

    streamlit run streamlit_app.py
"""

from __future__ import annotations

import hmac
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "python"))

import streamlit as st

# Importing the dashboard module triggers st.set_page_config — this must be
# the first Streamlit call in the script.
from stock_tools import dashboard as _dash  # noqa: E402


def _expected_password() -> str:
    """Read ``app_password`` from secrets; '' if the file/key is absent."""
    try:
        return st.secrets.get("app_password", "") or ""
    except Exception:
        return ""


def _password_gate() -> bool:
    """Return True once the user has typed the password from secrets."""
    expected = _expected_password()
    if not expected:
        st.error(
            "🛑 Server misconfiguration: `app_password` is not set in "
            "`.streamlit/secrets.toml` (or in the Streamlit Cloud secrets UI). "
            "Refusing to render the dashboard."
        )
        return False

    if st.session_state.get("_authed"):
        return True

    def _on_submit() -> None:
        entered = st.session_state.get("_pw_input", "")
        if hmac.compare_digest(str(entered), str(expected)):
            st.session_state["_authed"] = True
            st.session_state.pop("_pw_input", None)
            st.session_state.pop("_pw_error", None)
        else:
            st.session_state["_pw_error"] = "wrong password"

    st.title("🔒 Stock TA Dashboard")
    st.caption("Enter the shared password to continue.")
    st.text_input(
        "Password",
        type="password",
        key="_pw_input",
        on_change=_on_submit,
    )
    if st.session_state.get("_pw_error"):
        st.error(st.session_state["_pw_error"])
    return False


if not _password_gate():
    st.stop()

_dash.main()
