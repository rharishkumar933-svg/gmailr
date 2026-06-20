"""
Decorators - Permission and utility decorators
"""

from functools import wraps
from pyrogram import Client
from pyrogram.types import Message, CallbackQuery

from config import OWNER_ID


def admin_only(func):
    """Decorator to restrict function to admins only"""
    @wraps(func)
    async def wrapper(client: Client, update):
        mongo = client.mongo
        
        if isinstance(update, Message):
            user_id = update.from_user.id
        elif isinstance(update, CallbackQuery):
            user_id = update.from_user.id
        else:
            return
        
        # Check if user is admin
        if user_id == OWNER_ID or await mongo.is_admin(user_id):
            return await func(client, update)
        else:
            if isinstance(update, Message):
                await update.reply("❌ This command is restricted to administrators!")
            elif isinstance(update, CallbackQuery):
                await update.answer("❌ Admin permission required!", show_alert=True)
    
    return wrapper




def rate_limit(seconds: int = 5):
    """Rate limiting decorator"""
    from datetime import datetime, timedelta
    
    user_last_use = {}
    
    def decorator(func):
        @wraps(func)
        async def wrapper(client: Client, update):
            if isinstance(update, Message):
                user_id = update.from_user.id
            elif isinstance(update, CallbackQuery):
                user_id = update.from_user.id
            else:
                return
            
            now = datetime.utcnow()
            last_use = user_last_use.get(user_id)
            
            if last_use and (now - last_use) < timedelta(seconds=seconds):
                remaining = seconds - (now - last_use).seconds
                
                if isinstance(update, CallbackQuery):
                    await update.answer(f"⏳ Please wait {remaining} seconds", show_alert=True)
                return
            
            user_last_use[user_id] = now
            return await func(client, update)
        
        return wrapper
    return decorator
