import os
from dotenv import load_dotenv

load_dotenv()


def get_secret(name):
    """Read credentials from environment variables or Streamlit Cloud Secrets."""
    value = os.getenv(name)
    if value:
        return value
    try:
        import streamlit as st
        return st.secrets.get(name)
    except Exception:
        return None

# Project settings
PROJECT_NAME = "Quiklee Sales Intelligence"

# API configuration
BRAVE_API_KEY = get_secret("BRAVE_API_KEY")
LUSHA_API_KEY = get_secret("LUSHA_API_KEY")
SIMILARWEB_API_KEY = get_secret("SIMILARWEB_API_KEY")
TABAPI_API_KEY = get_secret("TABAPI_API_KEY")

# Discovery configuration
TARGET_COUNTRY = "India"

TARGET_CATEGORIES = [
    "Beauty and Personal Care",
    "Fashion and Apparel",
    "Food and Beverages",
    "Health and Nutrition",
    "Electronics",
    "Home and Lifestyle",
    "Sports and Fitness",
    "Pet Care"
]

CATEGORIES = [
    "beauty and personal care",
    "fashion and apparel",
    "food and beverages",
    "health and nutrition",
    "electronics",
    "home and lifestyle",
    "sports and fitness",
    "pet care"
]