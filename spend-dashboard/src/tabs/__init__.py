"""Dashboard tabs. Each module exposes render(df)."""

import streamlit as st


def section(title: str, caption: str) -> None:
    """Subheading with a one-line caption explaining what the section shows."""
    st.subheader(title)
    st.caption(caption)
