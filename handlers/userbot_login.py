"""
Userbot Login Handler - Login flow for adding userbots
"""

from pyrogram import Client, filters
from pyrogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import ListenerTimeout
from telethon import TelegramClient, utils, errors
from telethon.sessions import StringSession
from telethon.errors import (
    PhoneCodeInvalidError,
    SessionPasswordNeededError,
    PhoneNumberInvalidError,
    FloodWaitError
)

from config import API_ID, API_HASH
from keyboards.admin_keyboards import AdminKeyboards


@Client.on_callback_query(filters.regex("^userbot_login_start$"))
async def userbot_login_start_callback(client: Client, callback: CallbackQuery):
    """Start userbot login flow"""
    mongo = client.mongo
    user_id = callback.from_user.id
    
    if not await mongo.is_admin(user_id):
        await callback.answer("❌ Admin only!", show_alert=True)
        return
    
    await callback.message.edit_text(
        "📱 **Bot Login**\n\n"
        "Please enter the phone number in international format:\n\n"
        "**Format:** Without + sign, without spaces\n"
        "**Example:** 8613800138000\n"
        "(where 86 is the country code)\n\n"
        "Send /cancel to cancel"
    )
    await callback.answer()
    
    await process_login(client, user_id, callback.message)


async def process_login(client: Client, user_id: int, original_message: Message):
    """Process the login flow"""
    mongo = client.mongo
    
    try:
        # Get phone number
        phone_response = await client.ask(chat_id=user_id, text="", timeout=300)
        
        if phone_response.text == "/cancel":
            await phone_response.reply(
                "Login cancelled.",
                reply_markup=AdminKeyboards.userbot_menu()
            )
            return
        
        phone = utils.parse_phone(phone_response.text)
        
        if not phone:
            await phone_response.reply(
                "![❌](tg://emoji?id=5807651380332076999) Invalid phone number format!\n\nPlease use format: 8613800138000",
                reply_markup=AdminKeyboards.userbot_menu()
            )
            return
        
        # Check if phone already exists
        if await mongo.is_phone_number_exists(user_id, phone):
            await phone_response.reply(
                "![❌](tg://emoji?id=5807651380332076999) This phone number is already logged in!",
                reply_markup=AdminKeyboards.userbot_menu()
            )
            return
        
        # Create Telethon client
        account_client = TelegramClient(StringSession(), API_ID, API_HASH)
        
        try:
            await account_client.connect()
            
            sending_msg = await phone_response.reply("![📤](tg://emoji?id=5873225338984599714) Sending verification code...")
            
            try:
                result = await account_client.send_code_request(phone, force_sms=False)
                phone_code_hash = result.phone_code_hash
                await sending_msg.delete()
                
            except PhoneNumberInvalidError:
                await sending_msg.edit_text("![❌](tg://emoji?id=5807651380332076999) Invalid phone number!")
                await account_client.disconnect()
                return
            except FloodWaitError as e:
                await sending_msg.edit_text(f"![❌](tg://emoji?id=5807651380332076999) Too many requests! Please wait {e.seconds} seconds")
                await account_client.disconnect()
                return
            
            # Ask for OTP
            await phone_response.reply(
                "![🔒](tg://emoji?id=5945145850551343409) **Enter Verification Code**\n\n"
                "Please enter the verification code, separated by spaces:\n"
                "**Example:** If the code is 56346, enter: `5 6 3 4 6`\n\n"
                "Send /cancel to cancel"
            )
            
            otp_response = await client.ask(chat_id=user_id, text="", timeout=300)
            
            if otp_response.text == "/cancel":
                await otp_response.reply("Login cancelled.", reply_markup=AdminKeyboards.userbot_menu())
                await account_client.disconnect()
                return
            
            # Parse OTP
            otp_code = ''.join(otp_response.text.split())
            
            try:
                await account_client.sign_in(phone=phone, code=otp_code, phone_code_hash=phone_code_hash)
                
                # Login successful
                session_string = account_client.session.save()
                await mongo.save_session(user_id, phone, session_string)
                
                await otp_response.reply(
                    f"![✅](tg://emoji?id=6026228223145154159) **Login Successful!**\n\n"
                    f"📱 Phone Number: `{phone}`\n\n"
                    f"Bot added. Use 'Connect One' to activate it.",
                    reply_markup=AdminKeyboards.userbot_menu()
                )
                
                await account_client.disconnect()
                return
                
            except PhoneCodeInvalidError:
                # Try once more
                await otp_response.reply(
                    "![❌](tg://emoji?id=5807651380332076999) Invalid verification code! Please try again:\n\n"
                    "Enter the code with spaces: `5 6 3 4 6`\n\n"
                    "Send /cancel to cancel"
                )
                
                retry_response = await client.ask(chat_id=user_id, text="", timeout=300)
                
                if retry_response.text == "/cancel":
                    await retry_response.reply("Login cancelled.", reply_markup=AdminKeyboards.userbot_menu())
                    await account_client.disconnect()
                    return
                
                retry_otp = ''.join(retry_response.text.split())
                
                try:
                    await account_client.sign_in(phone=phone, code=retry_otp, phone_code_hash=phone_code_hash)
                    
                    session_string = account_client.session.save()
                    await mongo.save_session(user_id, phone, session_string)
                    
                    await retry_response.reply(
                        f"![✅](tg://emoji?id=6026228223145154159) **Login Successful!**\n\n📱 Phone Number: `{phone}`",
                        reply_markup=AdminKeyboards.userbot_menu()
                    )
                    await account_client.disconnect()
                    return
                    
                except SessionPasswordNeededError:
                    # Handle 2FA
                    await handle_2fa(client, user_id, phone, account_client, mongo)
                    return
                    
                except Exception as e:
                    await retry_response.reply(f"![❌](tg://emoji?id=5807651380332076999) Error: {str(e)[:100]}", reply_markup=AdminKeyboards.userbot_menu())
                    await account_client.disconnect()
                    return
                    
            except SessionPasswordNeededError:
                # Handle 2FA
                await handle_2fa(client, user_id, phone, account_client, mongo)
                return
                
            except Exception as e:
                await otp_response.reply(f"![❌](tg://emoji?id=5807651380332076999) Error: {str(e)[:100]}", reply_markup=AdminKeyboards.userbot_menu())
                await account_client.disconnect()
                return
                
        except Exception as e:
            await phone_response.reply(f"![❌](tg://emoji?id=5807651380332076999) Connection Error: {str(e)[:100]}", reply_markup=AdminKeyboards.userbot_menu())
            try:
                await account_client.disconnect()
            except:
                pass
            return
            
    except ListenerTimeout:
        await original_message.reply("![⏰](tg://emoji?id=6034898821517940846) Login Timeout!", reply_markup=AdminKeyboards.userbot_menu())


async def handle_2fa(client: Client, user_id: int, phone: str, account_client: TelegramClient, mongo):
    """Handle 2FA password input"""
    await client.send_message(
        user_id,
        "![🔒](tg://emoji?id=5945145850551343409) **2FA Required**\n\n"
        "Two-factor authentication is enabled for this account.\n\n"
        "Please enter your 2FA password:\n\n"
        "Send /cancel to cancel"
    )
    
    try:
        password_response = await client.ask(chat_id=user_id, text="", timeout=300)
        
        if password_response.text == "/cancel":
            await password_response.reply("Login cancelled.", reply_markup=AdminKeyboards.userbot_menu())
            await account_client.disconnect()
            return
        
        password = password_response.text
        
        try:
            await account_client.sign_in(password=password)
            
            session_string = account_client.session.save()
            await mongo.save_session(user_id, phone, session_string)
            
            await password_response.reply(
                f"![✅](tg://emoji?id=6026228223145154159) **Login Successful!**\n\n📱 Phone Number: `{phone}`",
                reply_markup=AdminKeyboards.userbot_menu()
            )
            
        except errors.PasswordHashInvalidError:
            await password_response.reply("![❌](tg://emoji?id=5807651380332076999) 2FA Password Incorrect!", reply_markup=AdminKeyboards.userbot_menu())
            
        except Exception as e:
            await password_response.reply(f"![❌](tg://emoji?id=5807651380332076999) Error: {str(e)[:100]}", reply_markup=AdminKeyboards.userbot_menu())
            
        finally:
            await account_client.disconnect()
            
    except ListenerTimeout:
        await client.send_message(user_id, "![⏰](tg://emoji?id=6034898821517940846) Timeout!", reply_markup=AdminKeyboards.userbot_menu())
        await account_client.disconnect()


@Client.on_message(filters.command("login") & filters.private)
async def login_command(client: Client, message: Message):
    """Handle /login command for admins"""
    mongo = client.mongo
    user_id = message.from_user.id
    
    if not await mongo.is_admin(user_id):
        await message.reply("![❌](tg://emoji?id=5807651380332076999) This command is restricted to administrators!")
        return
    
    await message.reply(
        "📱 **Bot Login**\n\n"
        "Please enter the phone number in international format:\n\n"
        "**Format:** Without + sign, without spaces\n"
        "**Example:** 8613800138000\n\n"
        "Send /cancel to cancel"
    )
    
    await process_login(client, user_id, message)
