import time
import re
from datetime import datetime, timedelta
import asyncio
import logging
from typing import Dict, List, Optional
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import (
    PhoneNumberInvalidError, FloodWaitError, ChannelPrivateError,
    UserBannedInChannelError, UserAlreadyParticipantError,
    InviteHashExpiredError, InviteHashInvalidError
)
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.tl.functions.messages import ImportChatInviteRequest
from telethon import events
from pyrogram.enums import ParseMode
from config import API_ID, API_HASH, BOT_USERNAME, TARGET_BOT_USERNAME, HOLD_LOG_GROUP_ID
from database.mongoconnect import MongoDB

logger = logging.getLogger(__name__)


class UserbotManager:
    def __init__(self, mongo: MongoDB, app=None):
        self.mongo = mongo
        self.app = app
        self.clients: Dict[str, TelegramClient] = {}
        self.client_status: Dict[str, bool] = {}
        self.flood_cooldowns: Dict[str, datetime] = {}
        self.busy_clients: set = set()
        self.semaphores: Dict[str, asyncio.Semaphore] = {}
        self.registration_history: Dict[str, List[datetime]] = {}
        self.pending_registrations: Dict[str, Dict] = {}
        self.checking_futures: Dict[str, asyncio.Future] = {}
        self.checking_txs: Dict[str, Dict] = {}
        self.checking_data: Dict[str, List[str]] = {}
        self.last_run_date = None
        
        # Start daily hold account status verification loop
        asyncio.create_task(self.start_hold_verification_loop())
    
    async def _connect_userbot(self, phone: str, session_string: str) -> bool:
        try:
            client = TelegramClient(StringSession(session_string), API_ID, API_HASH)
            await client.connect()
            
            if not await client.is_user_authorized():
                logger.warning(f"Userbot {phone} is not authorized")
                await self.mongo.update_userbot_status(phone, False, "Unauthorized")
                await client.disconnect()
                return False
            
            me = await client.get_me()
            logger.info(f"Connected userbot: {phone} ({me.first_name})")
            
            # Send /start to Target Bot if target bot is configured
            if TARGET_BOT_USERNAME:
                try:
                    logger.info(f"Sending /start to target bot: {TARGET_BOT_USERNAME}")
                    await client.send_message(TARGET_BOT_USERNAME, "/start")
                except Exception as e:
                    logger.error(f"Failed to send /start to target bot {TARGET_BOT_USERNAME}: {e}")
            
            await self._register_event_handlers(phone, client)
            
            self.clients[phone] = client
            self.client_status[phone] = True
            await self.mongo.update_userbot_status(phone, True, "Connected successfully")
            
            return True
            
        except PhoneNumberInvalidError:
            await self.mongo.update_userbot_status(phone, False, "Invalid phone number")
            return False
        except Exception as e:
            logger.error(f"Error connecting userbot {phone}: {e}")
            await self.mongo.update_userbot_status(phone, False, str(e))
            return False
            
    async def _register_event_handlers(self, phone: str, client: TelegramClient):
        """Register event listeners for target bot messages on userbot"""
        
        async def check_and_auto_click(message) -> bool:
            auto_click_patterns = [
                "pre-confirm-registration-true-",
                "pre_cancel-2fa-false-true-",
                "cancel-2fa-false-true-"
            ]
            if message.buttons:
                for row in message.buttons:
                    for btn in row:
                        if btn.data:
                            try:
                                data_str = btn.data.decode('utf-8', errors='ignore')
                                for pattern in auto_click_patterns:
                                    if pattern in data_str:
                                        logger.info(f"Auto-clicking intermediate button on userbot {phone} via event: text='{btn.text}'")
                                        from telethon.errors import FloodWaitError
                                        for click_retry in range(5):
                                            try:
                                                await btn.click()
                                                break
                                            except FloodWaitError as e:
                                                logger.warning(f"Got FloodWaitError when auto-clicking on {phone}: sleeping {e.seconds}s...")
                                                await asyncio.sleep(e.seconds)
                                        return True
                            except Exception as e:
                                logger.error(f"Error checking/auto-clicking: {e}")
            return False
        
        @client.on(events.MessageEdited(chats=TARGET_BOT_USERNAME))
        async def on_message_edited(event):
            try:
                if phone in self.checking_futures:
                    if await self._handle_verification_message(phone, event.message):
                        return
                if await check_and_auto_click(event.message):
                    return
                await self._handle_target_message_update(phone, event.message)
            except Exception as e:
                logger.error(f"Error handling message edit on {phone}: {e}")

        @client.on(events.NewMessage(chats=TARGET_BOT_USERNAME))
        async def on_new_message(event):
            try:
                if phone in self.checking_futures:
                    if await self._handle_verification_message(phone, event.message):
                        return
                text = event.message.text
                if text and ("registration canceled" in text.lower() or "registration cancelled" in text.lower()):
                    import re
                    email_match = re.search(r'([a-zA-Z0-9._%+-]+@gmail\.com)', text)
                    if email_match:
                        email = email_match.group(1).strip()
                        cutoff = datetime.utcnow() - timedelta(hours=10)
                        registration = await self.mongo.db["registrations"].find_one({
                            "phone": phone,
                            "email": email,
                            "status": {"$ne": "cancelled"},
                            "$or": [
                                {"created_at": {"$gt": cutoff}},
                                {"updated_at": {"$gt": cutoff}}
                            ]
                        })
                        if registration:
                            await self.mongo.update_registration_status(phone, registration["msg_id"], "cancelled")
                            user_id = registration.get("user_id")
                            bot_msg_id = registration.get("bot_msg_id")
                            if user_id and bot_msg_id:
                                try:
                                    await self.app.send_message(
                                        chat_id=user_id,
                                        text=text,
                                        reply_to_message_id=bot_msg_id,
                                        parse_mode=ParseMode.MARKDOWN
                                    )
                                    logger.info(f"Forwarded cancellation message for {email} to user {user_id} on main bot.")
                                except Exception as e:
                                    logger.error(f"Error notifying user of cancellation: {e}")
                            return

                pending = self.pending_registrations.get(phone)
                if pending:
                    self.pending_registrations.pop(phone, None)
                    from handlers.start import parse_registration_details
                    details = parse_registration_details(event.message.text)
                    await self.mongo.save_registration(
                        user_id=pending["user_id"],
                        phone=phone,
                        msg_id=event.message.id,
                        details=details,
                        bot_msg_id=pending["bot_msg_id"]
                    )
                    if await check_and_auto_click(event.message):
                        return
                    await self._handle_target_message_update(phone, event.message)
                    return

                if await check_and_auto_click(event.message):
                    return
                if event.message.reply_to:
                    replied_msg_id = event.message.reply_to.reply_to_msg_id
                    await self._handle_target_reply_message(phone, event.message, replied_msg_id)
            except Exception as e:
                logger.error(f"Error handling new message on {phone}: {e}")
    
    async def connect_all(self):
        sessions = await self.mongo.get_all_sessions()
        for session_data in sessions:
            phone = session_data.get('phone')
            session_string = session_data.get('session_string')
            
            if phone in self.clients and self.client_status.get(phone):
                continue
            
            try:
                await self._connect_userbot(phone, session_string)
                await asyncio.sleep(1)
            except Exception as e:
                logger.error(f"Failed to connect userbot {phone}: {e}")
        
        logger.info("Finished connecting all userbots")
    
    async def disconnect_all(self):
        for phone, client in list(self.clients.items()):
            try:
                if client.is_connected():
                    await client.disconnect()
                self.client_status[phone] = False
                await self.mongo.update_userbot_status(phone, False, "Manually disconnected")
            except Exception as e:
                logger.error(f"Error disconnecting {phone}: {e}")
        
        self.clients.clear()
        logger.info("All userbots disconnected")
    
    async def connect_single_userbot(self, phone: str) -> Dict:
        if phone in self.clients and self.clients[phone].is_connected():
            return {"success": True, "message": "Connected", "already_connected": True}
        
        session_data = await self.mongo.get_session(phone)
        if not session_data:
            return {"success": False, "message": "Userbot not found"}
        
        success = await self._connect_userbot(phone, session_data['session_string'])
        if success:
            return {"success": True, "message": "Connected successfully"}
        return {"success": False, "message": "Connection failed"}
    
    async def disconnect_single_userbot(self, phone: str) -> Dict:
        if phone not in self.clients:
            return {"success": False, "message": "Userbot not connected"}
        
        try:
            client = self.clients[phone]
            if client.is_connected():
                await client.disconnect()
            
            self.client_status[phone] = False
            await self.mongo.update_userbot_status(phone, False, "Manually disconnected")
            del self.clients[phone]
            
            return {"success": True, "message": "Disconnected successfully"}
        except Exception as e:
            return {"success": False, "message": str(e)}
    
    async def get_available_userbots(self) -> List[Dict]:
        available = []
        for phone, client in self.clients.items():
            try:
                if client.is_connected() and await client.is_user_authorized():
                    available.append({'phone': phone, 'client': client})
            except:
                self.client_status[phone] = False
        return available
    
    async def check_all_connections(self) -> Dict:
        all_sessions = await self.mongo.get_all_sessions()
        connected, disconnected = 0, 0
        
        for session_data in all_sessions:
            phone = session_data.get('phone')
            try:
                if phone in self.clients:
                    client = self.clients[phone]
                    if client.is_connected() and await client.is_user_authorized():
                        connected += 1
                        await self.mongo.update_userbot_status(phone, True, "Connected")
                    else:
                        disconnected += 1
                        await self.mongo.update_userbot_status(phone, False, "Not connected")
                else:
                    disconnected += 1
                    await self.mongo.update_userbot_status(phone, False, "Not loaded")
            except Exception as e:
                disconnected += 1
                await self.mongo.update_userbot_status(phone, False, str(e))
        
        return {'connected': connected, 'disconnected': disconnected, 'total': connected + disconnected}
    
    async def join_channel(self, phone: str, channel_input: str) -> Dict:
        if phone not in self.clients:
            return {"success": False, "message": "Userbot not connected"}
        
        client = self.clients[phone]
        try:
            if "/+" in channel_input or "/joinchat/" in channel_input:
                invite_hash = channel_input.split("/+")[-1] if "/+" in channel_input else channel_input.split("/joinchat/")[-1]
                await client(ImportChatInviteRequest(invite_hash.strip()))
            else:
                channel_username = channel_input.split("t.me/")[-1].strip("/") if "t.me/" in channel_input else channel_input.lstrip("@")
                await client(JoinChannelRequest(channel_username))
            
            return {"success": True, "message": "Joined successfully"}
        except UserAlreadyParticipantError:
            return {"success": True, "message": "Already a member"}
        except (InviteHashExpiredError, InviteHashInvalidError):
            return {"success": False, "message": "Invalid or expired invite link"}
        except (ChannelPrivateError, UserBannedInChannelError):
            return {"success": False, "message": "Cannot access channel"}
        except FloodWaitError as e:
            return {"success": False, "message": f"FloodWait: {e.seconds}s"}
        except Exception as e:
            return {"success": False, "message": str(e)}
    
    async def leave_channel(self, phone: str, channel_username: str) -> Dict:
        if phone not in self.clients:
            return {"success": False, "message": "Userbot not connected"}
        
        try:
            client = self.clients[phone]
            channel = await client.get_entity(channel_username)
            await client.delete_dialog(channel)
            return {"success": True, "message": "Left successfully"}
        except Exception as e:
            return {"success": False, "message": str(e)}
    
    async def remove_userbot(self, phone: str) -> bool:
        if phone in self.clients:
            try:
                if self.clients[phone].is_connected():
                    await self.clients[phone].disconnect()
            except:
                pass
            del self.clients[phone]
        
        if phone in self.client_status:
            del self.client_status[phone]
        
        return await self.mongo.remove_userbot(phone)
    
    async def remove_disconnected_userbots(self) -> int:
        phone_numbers, deleted_count = await self.mongo.remove_disconnected_userbots()
        for phone in phone_numbers:
            self.clients.pop(phone, None)
            self.client_status.pop(phone, None)
        return deleted_count
    
    async def get_userbot_info(self, phone: str) -> Optional[Dict]:
        if phone not in self.clients or not self.clients[phone].is_connected():
            return None
        
        try:
            me = await self.clients[phone].get_me()
            return {
                'phone': phone, 'user_id': me.id, 'first_name': me.first_name,
                'last_name': me.last_name, 'username': me.username, 'is_connected': True
            }
        except:
            return None

    async def send_register_request(self, user_id: int, bot_msg_id: int) -> dict:
        """Select a free userbot and send '➕ Register a new Gmail' to target bot, locking the session to prevent duplicate data mixups"""
        for retry in range(5):
            sessions = await self.mongo.get_all_sessions()
            connected_phones = [s['phone'] for s in sessions if s.get('is_connected')]
            
            now = datetime.utcnow()
            
            # Filter out clients currently under FloodWait cooldown, busy, or rate limited (max 2 per minute)
            available_phones = []
            for phone in connected_phones:
                if phone in self.clients:
                    # Skip busy userbots
                    if phone in self.busy_clients:
                        continue
                    # Skip if registration rate limited (max 2 per 60 seconds)
                    if self._is_registration_rate_limited(phone):
                        continue
                    cooldown = self.flood_cooldowns.get(phone)
                    if cooldown and cooldown > now:
                        continue
                    available_phones.append(phone)
                    
            if not available_phones:
                # If all are busy, wait 0.2 seconds and retry, otherwise fail
                if retry < 4:
                    await asyncio.sleep(0.2)
                    continue
                return {"success": False, "error": "No available/connected userbots at the moment (all busy or on cooldown)."}
                
            for phone in available_phones:
                client = self.clients[phone]
                
                # Check busy status again in real-time
                if phone in self.busy_clients:
                    continue
                
                # Re-check cooldown in real-time
                cooldown = self.flood_cooldowns.get(phone)
                if cooldown and cooldown > datetime.utcnow():
                    continue
                    
                # Re-check registration rate limit in real-time
                if self._is_registration_rate_limited(phone):
                    continue
                    
                # Lock the client so no concurrent task can use it
                self.busy_clients.add(phone)
                
                try:
                    logger.info(f"Using userbot {phone} to send registration request...")
                    
                    # Store pending metadata for the event handlers
                    self.pending_registrations[phone] = {
                        "user_id": user_id,
                        "bot_msg_id": bot_msg_id
                    }
                    
                    await client.send_message(TARGET_BOT_USERNAME, "➕ Register a new Gmail")
                    
                    # Record the timestamp of this registration request
                    self.registration_history.setdefault(phone, []).append(datetime.utcnow())
                    
                    return {
                        "success": True,
                        "phone": phone
                    }
                    
                except FloodWaitError as e:
                    logger.warning(f"Userbot {phone} got FloodWait for {e.seconds} seconds.")
                    # Clear pending metadata
                    self.pending_registrations.pop(phone, None)
                    # Mark as flood blocked in memory and update database status
                    self.flood_cooldowns[phone] = datetime.utcnow() + timedelta(seconds=e.seconds)
                    await self.mongo.update_userbot_status(phone, True, f"FloodWait: {e.seconds}s")
                    # Retry with next client
                    continue
                except Exception as e:
                    logger.error(f"Failed to send request with userbot {phone}: {e}")
                    self.pending_registrations.pop(phone, None)
                    continue
                finally:
                    # Release lock on this userbot
                    self.busy_clients.discard(phone)
                    
        return {"success": False, "error": "All available userbots failed or were rate limited."}

    def _is_registration_rate_limited(self, phone: str) -> bool:
        """Check if the userbot has sent 2 or more registration requests in the last 60 seconds"""
        if phone not in self.registration_history:
            return False
            
        now = datetime.utcnow()
        # Keep only timestamps within the last 60 seconds
        self.registration_history[phone] = [
            t for t in self.registration_history[phone]
            if (now - t).total_seconds() < 60.0
        ]
        
        return len(self.registration_history[phone]) >= 2

    async def click_register_button(self, phone: str, msg_id: int, row: int, col: int) -> dict:
        """Click a button on a registration message with concurrency limits and FloodWait retries"""
        if phone not in self.clients or not self.client_status.get(phone):
            return {"success": False, "error": "Userbot is not currently connected."}
        
        client = self.clients[phone]
        sem = self.semaphores.setdefault(phone, asyncio.Semaphore(3))
        
        async with sem:
            for retry in range(5):  # Try up to 5 times if encountering FloodWait
                now = datetime.utcnow()
                cooldown = self.flood_cooldowns.get(phone)
                if cooldown and cooldown > now:
                    wait_secs = (cooldown - now).total_seconds()
                    logger.info(f"Userbot {phone} is cooling down. Waiting {wait_secs:.1f}s before click retry...")
                    await asyncio.sleep(wait_secs)
                
                try:
                    # Fetch message
                    message = await client.get_messages(TARGET_BOT_USERNAME, ids=msg_id)
                    if not message:
                        return {"success": False, "error": "Message not found on target bot"}
                    
                    # Click the button
                    if message.buttons and row < len(message.buttons) and col < len(message.buttons[row]):
                        from telethon.errors import FloodWaitError
                        for click_retry in range(5):
                            try:
                                await message.buttons[row][col].click()
                                break
                            except FloodWaitError as e:
                                logger.warning(f"Got FloodWaitError when clicking registration button on {phone}: sleeping {e.seconds}s...")
                                await asyncio.sleep(e.seconds)
                        return {"success": True}
                    else:
                        return {"success": False, "error": "Button not found on target message"}
                        
                except FloodWaitError as e:
                    logger.warning(f"Userbot {phone} got FloodWait for {e.seconds} seconds on button click. Retrying...")
                    self.flood_cooldowns[phone] = datetime.utcnow() + timedelta(seconds=e.seconds)
                    await self.mongo.update_userbot_status(phone, True, f"FloodWait: {e.seconds}s")
                    await asyncio.sleep(e.seconds)
                    continue
                except Exception as e:
                    logger.error(f"Error clicking button on userbot {phone}: {e}")
                    return {"success": False, "error": str(e)}
                    
            return {"success": False, "error": "Failed to click button due to persistent FloodWait."}

    async def _handle_target_message_update(self, phone: str, message):
        """Handle real-time updates (edits/new messages) from target bot on userbots"""
        if not self.app:
            logger.warning("Pyrogram client app is not set in UserbotManager")
            return
            
        msg_id = message.id
        # Look up active registration in MongoDB (only within the last 10 hours)
        cutoff = datetime.utcnow() - timedelta(hours=10)
        registration = await self.mongo.db["registrations"].find_one({
            "phone": phone, 
            "msg_id": msg_id,
            "$or": [
                {"created_at": {"$gt": cutoff}},
                {"updated_at": {"$gt": cutoff}}
            ]
        })
        if not registration:
            logger.debug(f"Received message edit from target bot for msg_id {msg_id} on {phone}, but no active registration found or expired (10h cutoff).")
            return
            
        user_id = registration.get("user_id")
        bot_msg_id = registration.get("bot_msg_id")
        if not user_id or not bot_msg_id:
            return
            
        reg_id = str(registration["_id"])
        
        # Extract response text and buttons
        response_text = message.text
        buttons = []
        if message.buttons:
            for r_idx, row in enumerate(message.buttons):
                row_buttons = []
                for c_idx, btn in enumerate(row):
                    row_buttons.append({
                        "text": btn.text,
                        "row": r_idx,
                        "col": c_idx
                    })
                buttons.append(row_buttons)
                
        # Parse new registration details and save to DB
        from handlers.start import parse_registration_details, apply_constant_reward_to_text, make_registration_keyboard
        details = parse_registration_details(response_text)
        if details:
            await self.mongo.save_registration(user_id, phone, msg_id, details)
            
        # Check and add transaction if success message
        await self._check_and_add_hold_transaction(user_id, phone, response_text, registration)
        
        if "registration cancelled" in response_text.lower():
            await self.mongo.update_registration_status(phone, msg_id, "cancelled")
            
        reward_amount = await self.mongo.get_system_setting("reward_amount", 0.0)
        exchange_rate = await self.mongo.get_system_setting("exchange_rate", 100.0)
        adjusted_text = apply_constant_reward_to_text(response_text, reward_amount, exchange_rate)
        adjusted_text = adjusted_text.replace("🔐", "🔒").replace("🔒", "![🔒](tg://emoji?id=5945145850551343409)")
        
        guide_enabled = await self.mongo.get_system_setting("guide_enabled", False)
        recovery_enabled = await self.mongo.get_system_setting("recovery_enabled", False)
        logout_enabled = await self.mongo.get_system_setting("logout_enabled", False)
        reply_markup = make_registration_keyboard(reg_id, buttons, reward_amount, guide_enabled, recovery_enabled, logout_enabled)
        
        # Edit the message on our main bot in real-time
        
        try:
            await self.app.edit_message_text(
                chat_id=user_id,
                message_id=bot_msg_id,
                text=adjusted_text,
                reply_markup=reply_markup,
                parse_mode=ParseMode.MARKDOWN
            )
            logger.info(f"Successfully updated message {bot_msg_id} for user {user_id} in real-time.")
        except Exception as e:
            logger.error(f"Error editing main bot message {bot_msg_id} for user {user_id}: {e}")

    async def _handle_target_reply_message(self, phone: str, message, replied_msg_id: int):
        """Handle real-time new messages from target bot that reply to a registration message"""
        if not self.app:
            logger.warning("Pyrogram client app is not set in UserbotManager")
            return
            
        # Look up active registration in MongoDB where the target bot replied to msg_id (only within the last 10 hours)
        cutoff = datetime.utcnow() - timedelta(hours=10)
        registration = await self.mongo.db["registrations"].find_one({
            "phone": phone, 
            "msg_id": replied_msg_id,
            "$or": [
                {"created_at": {"$gt": cutoff}},
                {"updated_at": {"$gt": cutoff}}
            ]
        })
        if not registration:
            return
            
        user_id = registration.get("user_id")
        bot_msg_id = registration.get("bot_msg_id")
        if not user_id or not bot_msg_id:
            return
            
        # Extract reply text
        reply_text = message.text
        
        # Check and add transaction if success message
        await self._check_and_add_hold_transaction(user_id, phone, reply_text, registration)
        
        if "registration canceled" in reply_text.lower() or "registration cancelled" in reply_text.lower():
            await self.mongo.update_registration_status(phone, registration["msg_id"], "cancelled")
        
        # Apply rate margin and format lock symbols
        from handlers.start import apply_constant_reward_to_text
        reward_amount = await self.mongo.get_system_setting("reward_amount", 0.0)
        exchange_rate = await self.mongo.get_system_setting("exchange_rate", 100.0)
        adjusted_text = apply_constant_reward_to_text(reply_text, reward_amount, exchange_rate)
        adjusted_text = adjusted_text.replace("🔐", "🔒").replace("🔒", "![🔒](tg://emoji?id=5945145850551343409)")
        
        # Send a new message on main bot replying to the original bot_msg_id
        from pyrogram.enums import ParseMode
        try:
            await self.app.send_message(
                chat_id=user_id,
                text=adjusted_text,
                reply_to_message_id=bot_msg_id,
                parse_mode=ParseMode.MARKDOWN
            )
            logger.info(f"Forwarded reply message to user {user_id} on main bot.")
        except Exception as e:
            logger.error(f"Error sending reply message on main bot to user {user_id}: {e}")

    async def _check_and_add_hold_transaction(self, user_id: int, phone: str, text: str, registration: dict):
        """Check if target bot text indicates hold credit, and log it to db"""
        if "credited to hold" in text and "transferred" in text:
            try:
                # Check if transaction already exists for this registration
                existing_tx = await self.mongo.db["transactions"].find_one({"registration_id": registration["_id"]})
                if not existing_tx:
                    import re
                    # Parse hold amount and days
                    usd_amount = None
                    hold_days = 3
                    
                    # Scan lines for "credited to hold"
                    for line in text.split('\n'):
                        if "credited to hold" in line:
                            match = re.search(r'(\d+\.\d+)\s*\$', line)
                            if not match:
                                match = re.search(r'\$\s*(\d+\.\d+)', line)
                            if not match:
                                match = re.search(r'(\d+(?:\.\d+)?)\s*\$', line)
                            if not match:
                                match = re.search(r'\$\s*(\d+(?:\.\d+)?)', line)
                            if not match:
                                match = re.search(r'(\d+(?:\.\d+)?)', line)
                            if match:
                                try:
                                    usd_amount = float(match.group(1))
                                except ValueError:
                                    pass
                            break
                    
                    days_match = re.search(r'(\d+)-day\s+hold', text, re.IGNORECASE)
                    if not days_match:
                        days_match = re.search(r'after\s+(\d+)\s+day', text, re.IGNORECASE)
                    if days_match:
                        try:
                            hold_days = int(days_match.group(1))
                        except ValueError:
                            pass
                    
                    if usd_amount is not None:
                        reward_amount = await self.mongo.get_system_setting("reward_amount", 0.0)
                        email = registration.get("email", "Unknown Email")
                        
                        await self.mongo.add_transaction(
                            user_id=user_id,
                            email=email,
                            phone=phone,
                            amount_usd=reward_amount,
                            hold_days=hold_days,
                            registration_id=registration["_id"]
                        )
                        await self.mongo.update_registration_status(phone, registration["msg_id"], "completed")
                        logger.info(f"Added hold transaction for user {user_id}: email={email}, amount={reward_amount}$, days={hold_days}")
                        
                        if HOLD_LOG_GROUP_ID:
                             try:
                                 reg_email = registration.get("email", "")
                                 password = registration.get("password", "")
                                 recovery_email = registration.get("recovery_email", "")
                                 log_text = f"`{reg_email}:{password}:{recovery_email}`"
                                 await self.app.send_message(chat_id=HOLD_LOG_GROUP_ID, text=log_text)
                                 logger.info(f"Successfully sent credentials to HOLD_LOG_GROUP_ID: {HOLD_LOG_GROUP_ID}")
                             except Exception as ex:
                                 logger.error(f"Failed to send credentials to HOLD_LOG_GROUP_ID: {ex}")
            except Exception as e:
                logger.error(f"Error checking/adding hold transaction: {e}")

    async def start_hold_verification_loop(self):
        """Start the background loop checking every 30 seconds for IST midnight"""
        # Sleep for a bit initially to let services start
        await asyncio.sleep(30)
        while True:
            try:
                now = datetime.utcnow()
                # Convert to IST (UTC + 5:30)
                ist_now = now + timedelta(hours=5, minutes=30)
                if ist_now.hour == 0 and ist_now.minute == 0:
                    if self.last_run_date != ist_now.date():
                        logger.info(f"IST Midnight reached ({ist_now}). Starting daily hold verification...")
                        self.last_run_date = ist_now.date()
                        await self.check_pending_hold_accounts()
            except Exception as e:
                logger.error(f"Error in hold verification loop: {e}")
            await asyncio.sleep(30)

    async def check_pending_hold_accounts(self, save_raw_files=False) -> dict:
        """
        Check the status of pending 'hold' accounts on the target bot daily.
        Queries all 'hold' transactions in the database from the last 5 days.
        """
        logger.info("Starting hold accounts verification...")
        now = datetime.utcnow()
        cutoff_date = now - timedelta(days=5)
        
        # Get all transactions that are in 'hold' status and created in the last 5 days
        hold_txs = await self.mongo.db["transactions"].find({
            "status": "hold",
            "created_at": {"$gte": cutoff_date}
        }).to_list(length=None)
        
        if not hold_txs:
            logger.info("No pending hold transactions found in the last 4 days.")
            return {}
            
        logger.info(f"Found {len(hold_txs)} pending hold transactions to verify.")
        
        # Group transactions by phone number
        txs_by_phone = {}
        for tx in hold_txs:
            phone = tx.get("phone")
            if phone:
                txs_by_phone.setdefault(phone, []).append(tx)
                
        raw_files = {}
        
        for phone, txs in txs_by_phone.items():
            if phone not in self.clients or not self.client_status.get(phone):
                logger.warning(f"Userbot {phone} is not connected. Skipping verification for its {len(txs)} accounts.")
                continue
                
            client = self.clients[phone]
            pending_emails = {tx["email"].lower().strip(): tx for tx in txs if tx.get("email")}
            
            logger.info(f"Verifying {len(pending_emails)} accounts for userbot {phone}...")
            
            # Setup checking states
            fut = asyncio.get_running_loop().create_future()
            self.checking_futures[phone] = fut
            self.checking_txs[phone] = pending_emails
            if save_raw_files:
                self.checking_data[phone] = []
                
            # Set busy, send message, then release busy immediately
            self.busy_clients.add(phone)
            try:
                from telethon.errors import FloodWaitError
                try:
                    await client.send_message(TARGET_BOT_USERNAME, "📋 My accounts")
                except FloodWaitError as e:
                    logger.warning(f"Got FloodWaitError when sending '📋 My accounts' on {phone}: sleeping {e.seconds}s...")
                    await asyncio.sleep(e.seconds)
                    await client.send_message(TARGET_BOT_USERNAME, "📋 My accounts")
            except Exception as e:
                logger.error(f"Failed to send '📋 My accounts' on {phone}: {e}")
                self.busy_clients.discard(phone)
                self.checking_futures.pop(phone, None)
                self.checking_txs.pop(phone, None)
                self.checking_data.pop(phone, None)
                continue
            self.busy_clients.discard(phone)
            
            # Wait for verification to complete (up to 20 minutes per userbot)
            try:
                await asyncio.wait_for(fut, timeout=1200)
                logger.info(f"Verification completed for userbot {phone}.")
            except asyncio.TimeoutError:
                logger.warning(f"Timeout waiting for verification response on userbot {phone}.")
                await self._process_expired_transactions(phone)
            finally:
                self.checking_futures.pop(phone, None)
                self.checking_txs.pop(phone, None)
                
            # Save raw file data if requested
            if save_raw_files and phone in self.checking_data:
                pages_text = self.checking_data.pop(phone, [])
                if pages_text:
                    import os
                    os.makedirs("downloads", exist_ok=True)
                    date_str = datetime.utcnow().strftime("%Y-%m-%d_%H-%M-%S")
                    filename = f"downloads/account_{phone}_{date_str}.txt"
                    with open(filename, "w", encoding="utf-8") as f:
                        f.write(f"--- HOLD VERIFICATION DATA FOR {phone} ({date_str}) ---\n\n")
                        for idx, page in enumerate(pages_text):
                            f.write(f"=== PAGE {idx+1} ===\n")
                            f.write(page)
                            f.write("\n\n")
                    raw_files[phone] = filename
                    
        return raw_files

    async def _handle_verification_message(self, phone: str, message) -> bool:
        """
        Handle a message from the target bot during verification.
        Returns True if the message was handled as verification data.
        """
        text = getattr(message, "text", "") or ""
        if not text or not ("@gmail.com" in text or "registration" in text.lower() or "created:" in text.lower()):
            return False
            
        logger.info(f"Verification handler caught message on {phone}.")
        
        # Save raw text if collecting data
        if phone in self.checking_data:
            self.checking_data[phone].append(text)
            
        # Parse current page
        now = datetime.utcnow()
        pending = self.checking_txs.get(phone, {})
        
        # Parse emails and statuses on current page
        matches = list(re.finditer(r'([a-zA-Z0-9._%+-]+@gmail\.com)', text))
        
        stop_checking = False
        for i, match in enumerate(matches):
            email = match.group(1).lower().strip()
            start_pos = match.end()
            end_pos = matches[i+1].start() if i + 1 < len(matches) else len(text)
            block_text = text[start_pos:end_pos].strip()
            
            # Check date header
            date_match = re.search(r'Created:\s*(\d{2})\.(\d{2})\.(\d{2}),\s*(\d{2}):(\d{2})', block_text)
            if date_match:
                d, m, y, hh, mm = map(int, date_match.groups())
                try:
                    created_dt = datetime(2000 + y, m, d, hh, mm)
                    if (now - created_dt).days > 4:
                        logger.info(f"Account {email} created on {created_dt} is older than 4 days. Stopping verification.")
                        stop_checking = True
                        break
                except Exception as ex:
                    logger.error(f"Error parsing date {date_match.group(0)}: {ex}")
            
            if email in pending:
                tx = pending[email]
                block_lower = block_text.lower()
                status = None
                
                if "🟢" in block_text or "✅" in block_text or "credited" in block_lower or "accepted" in block_lower:
                    status = "credited"
                elif "🔴" in block_text or "rejected" in block_lower or "cancel" in block_lower:
                    status = "rejected"
                elif "🟠" in block_text or "in the hold" in block_lower:
                    status = "hold"
                    
                if status and status != "hold":
                    # Status has changed, update in DB
                    success = await self.mongo.update_transaction_status(str(tx["_id"]), status)
                    if success:
                        logger.info(f"Updated tx {tx['_id']} for {email} to status: {status}")
                        pending.pop(email, None)
                        
                        # Send notification to user
                        user_id = tx.get("user_id")
                        reward_amount = tx.get("amount_usd", 0.0)
                        exchange_rate = await self.mongo.get_system_setting("exchange_rate", 100.0)
                        from handlers.start import format_price_dual
                        amount_str = format_price_dual(reward_amount, 3, exchange_rate)
                        
                        if status == "credited":
                            notification = f"🎉 **Account Approved!**\n\n📧 **Email:** `{email}`\n💰 **Credited:** {amount_str} to your Main Balance."
                        else:
                            notification = f"❌ **Account Rejected/Cancelled!**\n\n📧 **Email:** `{email}`\n⚠️ The target bot marked this registration as rejected or cancelled."
                            
                        try:
                            await self.app.send_message(chat_id=user_id, text=notification)
                        except Exception as e:
                            logger.error(f"Failed to notify user {user_id} of status change for {email}: {e}")
                            
        # If stop_checking is True or there is no Next button, we finish
        next_btn = None
        if not stop_checking:
            buttons = getattr(message, "buttons", None)
            if buttons:
                for row in buttons:
                    for btn in row:
                        if btn.text and ("next" in btn.text.lower() or ">>" in btn.text):
                            next_btn = btn
                            break
                    if next_btn:
                        break
                        
        if stop_checking or not next_btn:
            # Done checking. Process expired ones
            await self._process_expired_transactions(phone)
            # Set future result
            fut = self.checking_futures.get(phone)
            if fut and not fut.done():
                fut.set_result(True)
            return True
            
        # Click the next button
        try:
            logger.info(f"Clicking 'Next' button to load next page for {phone}...")
            from telethon.errors import FloodWaitError
            for click_retry in range(5):
                try:
                    await next_btn.click()
                    break
                except FloodWaitError as e:
                    logger.warning(f"Got FloodWaitError when clicking next button on {phone}: sleeping {e.seconds}s...")
                    await asyncio.sleep(e.seconds)
        except Exception as e:
            logger.error(f"Failed to click next button on {phone}: {e}")
            await self._process_expired_transactions(phone)
            fut = self.checking_futures.get(phone)
            if fut and not fut.done():
                fut.set_result(True)
                
        return True

    async def _process_expired_transactions(self, phone: str):
        """Mark remaining pending transactions whose hold_until date has reached as expired"""
        now = datetime.utcnow()
        pending = self.checking_txs.get(phone, {})
        expired_emails = []
        for email, tx in list(pending.items()):
            hold_until = tx.get("hold_until")
            if hold_until and hold_until <= now:
                success = await self.mongo.update_transaction_status(str(tx["_id"]), "expired")
                if success:
                    logger.info(f"Hold period expired for {email}. Marked as expired.")
                    pending.pop(email, None)
                    expired_emails.append(email)
