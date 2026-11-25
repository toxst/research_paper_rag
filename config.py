import os
import streamlit as st

MB = 1024 * 1024

MAX_ZIP_SIZE = 100 * MB
MAX_TOTAL_PDF_BYTES = 250 * MB
MAX_PDF_SIZE = 25 * MB
MAX_PDF_COUNT = 50
MAX_COMPRESSION_RATIO = 20

# Limit the number of entries inspected in a ZIP archive.
MAX_ZIP_ENTRIES = 1000


def _get_r2_setting(name: str) -> str:
    """Get R2 setting from st.secrets (Streamlit) or environment variable."""
    # Try Streamlit secrets first
    try:
        value = st.secrets.get(name)
        if value:
            return str(value).strip()
    except (KeyError, FileNotFoundError, AttributeError):
        pass
    # Fall back to environment variable
    value = os.environ.get(name)
    if value:
        return value.strip()
    return ""


# R2 Storage Configuration (loaded from st.secrets or environment variables)
R2_ACCOUNT_ID = _get_r2_setting("R2_ACCOUNT_ID")
R2_ACCESS_KEY_ID = _get_r2_setting("R2_ACCESS_KEY_ID")
R2_SECRET_ACCESS_KEY = _get_r2_setting("R2_SECRET_ACCESS_KEY")
R2_BUCKET_NAME = _get_r2_setting("R2_BUCKET_NAME")
R2_ENDPOINT_URL = _get_r2_setting("R2_ENDPOINT_URL")

R2_CONFIG = {
    "R2_ACCOUNT_ID": R2_ACCOUNT_ID,
    "R2_ACCESS_KEY_ID": R2_ACCESS_KEY_ID,
    "R2_SECRET_ACCESS_KEY": R2_SECRET_ACCESS_KEY,
    "R2_BUCKET_NAME": R2_BUCKET_NAME,
    "R2_ENDPOINT_URL": R2_ENDPOINT_URL,
}

