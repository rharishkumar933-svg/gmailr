"""
Keyword Monitoring Bot - Configuration
All environment variables and settings
"""

import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Telegram API credentials
API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")

# MongoDB Configuration
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
DATABASE_NAME = os.getenv("DATABASE_NAME", "GmailFarmerBot")

# Bot Configuration
BOT_USERNAME = os.getenv("BOT_USERNAME", "")
TARGET_BOT_USERNAME = os.getenv("TARGET_BOT_USERNAME", "")

# Owner/Admin Configuration
OWNER_ID = int(os.getenv("OWNER_ID", "0"))
OWNER_USERNAME = os.getenv("OWNER_USERNAME", "")
SUPPORT_USERNAME = os.getenv("SUPPORT_USERNAME", "").strip() or OWNER_USERNAME
HOLD_LOG_GROUP_ID = os.getenv("HOLD_LOG_GROUP_ID", "")
if HOLD_LOG_GROUP_ID:
    try:
        HOLD_LOG_GROUP_ID = int(HOLD_LOG_GROUP_ID)
    except ValueError:
        pass

PAYOUT_LOG_GROUP_ID = os.getenv("PAYOUT_LOG_GROUP_ID", "")
if PAYOUT_LOG_GROUP_ID:
    try:
        PAYOUT_LOG_GROUP_ID = int(PAYOUT_LOG_GROUP_ID)
    except ValueError:
        pass

# Bot Settings
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
USERBOT_ACTION_DELAY = float(os.getenv("USERBOT_ACTION_DELAY", "1.0"))
MAX_USERBOT_RETRIES = int(os.getenv("MAX_USERBOT_RETRIES", "3"))

