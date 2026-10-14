"""Code d'accès optionnel.

Actif seulement si un fichier `access.json` (sel + empreinte du code) se trouve
à côté de app.py. Le code n'est jamais stocké en clair. Sans ce fichier,
l'application s'ouvre librement (cas du code source public).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from pathlib import Path

import streamlit as st

ACCESS_FILE = Path(__file__).resolve().parent.parent / "access.json"
ITERATIONS = 200_000
MAX_TRIES = 5


def hash_code(code: str, salt: bytes, iterations: int = ITERATIONS) -> str:
    return hashlib.pbkdf2_hmac("sha256", code.strip().upper().encode(), salt, iterations).hex()


def make_access_file(code: str, path: Path = ACCESS_FILE) -> None:
    import os

    salt = os.urandom(16)
    path.write_text(json.dumps({
        "salt": salt.hex(), "iterations": ITERATIONS, "hash": hash_code(code, salt),
    }), encoding="utf-8")


def _check(code: str) -> bool:
    cfg = json.loads(ACCESS_FILE.read_text(encoding="utf-8"))
    expected = cfg["hash"]
    got = hash_code(code, bytes.fromhex(cfg["salt"]), cfg.get("iterations", ITERATIONS))
    return hmac.compare_digest(expected, got)


def require_access() -> None:
    """Affiche l'écran de code tant qu'il n'est pas validé, puis laisse passer."""
    if not ACCESS_FILE.exists() or st.session_state.get("access_ok"):
        return

    tries = st.session_state.get("access_tries", 0)
    st.markdown(
        """<div style="max-width:460px;margin:12vh auto 0;text-align:center">
        <p class="eyebrow">Accès protégé</p>
        <h1 class="hero-title" style="font:800 2.4rem/1.1 var(--display);margin:14px 0 10px">Code d'accès</h1>
        <p style="color:#9aa6bd;margin-bottom:24px">Saisissez le code qui vous a été remis pour utiliser l'application.</p>
        </div>""",
        unsafe_allow_html=True,
    )
    _, mid, _ = st.columns([1, 1.2, 1])
    with mid:
        if tries >= MAX_TRIES:
            st.error("Trop d'essais. Rechargez la page pour réessayer.")
            st.stop()
        with st.form("access_form"):
            code = st.text_input("Code", type="password", label_visibility="collapsed",
                                 placeholder="Code d'accès")
            ok = st.form_submit_button("Entrer", type="primary", use_container_width=True)
        if ok:
            if _check(code):
                st.session_state["access_ok"] = True
                st.rerun()
            st.session_state["access_tries"] = tries + 1
            time.sleep(1.5)
            st.error("Code incorrect.")
    st.stop()
