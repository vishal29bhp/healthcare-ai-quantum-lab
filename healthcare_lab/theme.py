"""Shared visual styling for the Streamlit pages: clinical colour palette, metric cards and status badges.

The base colours live in ``.streamlit/config.toml``; this module adds the pieces a theme file cannot express.
"""
from __future__ import annotations

from html import escape

import streamlit as st

TEAL = "#0E7C86"
NAVY = "#0B3D5C"

# (background, text) per verification status, light grey for "only discovered" through deep green for "validated".
STATUS_COLOURS = {
    "Discovered": ("#ECEFF1", "#455A64"),
    "Source verified": ("#E3F2FD", "#1565C0"),
    "Access verified": ("#E0F7FA", "#00838F"),
    "Downloaded": ("#E0F2F1", "#00695C"),
    "Integrity verified": ("#E8F5E9", "#2E7D32"),
    "Parsed": ("#DCEDC8", "#33691E"),
    "Preprocessing validated": ("#C8E6C9", "#1B5E20"),
}

# (background, text) per access level, green for open through red for controlled.
ACCESS_COLOURS = {
    "Open": ("#E8F5E9", "#2E7D32"),
    "Registration": ("#FFF8E1", "#8D6E00"),
    "Credentialed": ("#FFF3E0", "#E65100"),
    "Controlled": ("#FFEBEE", "#C62828"),
    "Competition": ("#F3E5F5", "#6A1B9A"),
    "Unknown": ("#ECEFF1", "#546E7A"),
}

CATEGORY_ICONS = {
    "Medical Imaging": "🩻",
    "Clinical/Tabular": "🩺",
    "Biomedical/Molecular": "🧬",
    "Physiological/Time-Series": "💓",
    "Public Health": "🌍",
    "Medical Text and Healthcare NLP": "📝",
}

_CSS = f"""
<style>
h1 {{ color: {NAVY}; }}
h2, h3 {{ color: {TEAL}; }}
.hc-banner {{
    background: linear-gradient(90deg, {NAVY} 0%, {TEAL} 60%, #26A69A 100%);
    color: #FFFFFF; border-radius: 12px; padding: 14px 20px; margin: -0.5rem 0 1rem 0;
    font-size: 0.95rem; box-shadow: 0 2px 8px rgba(11, 61, 92, 0.18);
}}
.hc-banner b {{ color: #FFFFFF; }}
div[data-testid="stMetric"] {{
    background: #FFFFFF; border: 1px solid #D4E8EB; border-left: 6px solid {TEAL};
    border-radius: 10px; padding: 10px 14px; box-shadow: 0 1px 4px rgba(14, 124, 134, 0.08);
}}
div[data-testid="stMetricLabel"] p {{ color: #3E6B73; font-weight: 600; }}
div[data-testid="stMetricValue"] {{ color: {NAVY}; }}
section[data-testid="stSidebar"] h2 {{ color: {NAVY}; }}
.hc-badge {{
    display: inline-block; border-radius: 999px; padding: 3px 12px; margin: 0 6px 6px 0;
    font-size: 0.85rem; font-weight: 600; border: 1px solid rgba(0, 0, 0, 0.06);
}}
</style>
"""


def apply_theme() -> None:
    """Inject the shared CSS. Call once per page, right after ``st.set_page_config``."""
    st.markdown(_CSS, unsafe_allow_html=True)


def banner(text: str) -> None:
    """A teal gradient strip under the page title. ``text`` may contain <b> tags; everything else is escaped."""
    safe = escape(text).replace("&lt;b&gt;", "<b>").replace("&lt;/b&gt;", "</b>")
    st.markdown(f'<div class="hc-banner">{safe}</div>', unsafe_allow_html=True)


def badge(label: str, colours: tuple[str, str]) -> str:
    background, text = colours
    return f'<span class="hc-badge" style="background:{background};color:{text}">{escape(label)}</span>'


def status_badge(status: str) -> str:
    return badge(status, STATUS_COLOURS.get(status, STATUS_COLOURS["Discovered"]))


def access_badge(access: str) -> str:
    return badge(f"Access: {access}", ACCESS_COLOURS.get(access, ACCESS_COLOURS["Unknown"]))


def cell_style(value: object, palette: dict[str, tuple[str, str]]) -> str:
    """pandas Styler CSS for one table cell coloured by ``palette``; empty for values not in it."""
    colours = palette.get(str(value))
    return f"background-color: {colours[0]}; color: {colours[1]}; font-weight: 600" if colours else ""
