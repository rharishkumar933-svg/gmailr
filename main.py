"""
Userbot Manager Bot - Main Entry Point
Uses Pyrofork for main bot and Telethon for userbots
"""

import asyncio
import logging
from pyrogram import Client, idle
from pyrogram.errors import ApiIdInvalid, ApiIdPublishedFlood, AccessTokenInvalid

from config import API_ID, API_HASH, BOT_TOKEN, LOG_LEVEL
from database.mongoconnect import MongoDB
from services.userbot_manager import UserbotManager

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Global instances
mongo = None
userbot_manager = None


async def start_bot():
    """Initialize and start the bot"""
    global mongo, userbot_manager
    
    try:
        # Initialize MongoDB
        logger.info("Connecting to MongoDB...")
        mongo = MongoDB()
        await mongo.init_db()
        logger.info("✅ MongoDB connected successfully")
        
        # Initialize Pyrofork bot client
        logger.info("Initializing Pyrofork bot...")
        app = Client(
            "userbot_manager_bot",
            api_id=API_ID,
            api_hash=API_HASH,
            bot_token=BOT_TOKEN,
            plugins=dict(root="handlers"),
            in_memory=True
        )
        
        # Start the bot
        await app.start()
        logger.info("✅ Bot started successfully")
        
        # Get bot info
        bot_info = await app.get_me()
        logger.info(f"Bot Username: @{bot_info.username}")
        logger.info(f"Bot ID: {bot_info.id}")
        
        # Initialize services
        logger.info("Initializing Userbot Manager (Telethon)...")
        userbot_manager = UserbotManager(mongo, app)
        logger.info("✅ Userbot Manager initialized")
        
        # Auto-connect all active userbots on startup
        # logger.info("Connecting active userbots...")
        # await userbot_manager.connect_all()
        
        # Store global instances for handlers
        app.mongo = mongo
        app.userbot_manager = userbot_manager
        
        logger.info("=" * 50)
        logger.info("🚀 Userbot Manager Bot is now running!")
        logger.info("=" * 50)
        
        # Keep the bot running
        await idle()
        
        # Cleanup on exit
        await app.stop()
        
    except ApiIdInvalid:
        logger.error("❌ Invalid API_ID or API_HASH. Please check your config.")
    except ApiIdPublishedFlood:
        logger.error("❌ API_ID/API_HASH has been published and is banned.")
    except AccessTokenInvalid:
        logger.error("❌ Invalid BOT_TOKEN. Please check your config.")
    except Exception as e:
        logger.error(f"❌ Error starting bot: {e}", exc_info=True)
    finally:
        await cleanup()


async def cleanup():
    """Cleanup resources before shutdown"""
    global userbot_manager
    
    logger.info("Shutting down services...")
    
    try:
        if userbot_manager:
            await userbot_manager.disconnect_all()
            logger.info("✅ All userbots disconnected")
        
        logger.info("✅ Cleanup completed")
    except Exception as e:
        logger.error(f"Error during cleanup: {e}")


def main():
    """Main function to run the bot"""
    try:
        logger.info("Starting Userbot Manager Bot...")
        asyncio.run(start_bot())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)


if __name__ == "__main__":
    main()
