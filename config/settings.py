import os
from dotenv import load_dotenv

load_dotenv()

# Project settings
PROJECT_NAME = "Quiklee Sales Intelligence"

# API configuration
BRAVE_API_KEY = os.getenv("BRAVE_API_KEY")
LUSHA_API_KEY = os.getenv("LUSHA_API_KEY")
SIMILARWEB_API_KEY = os.getenv("SIMILARWEB_API_KEY")
TABAPI_API_KEY = os.getenv("TABAPI_API_KEY")

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