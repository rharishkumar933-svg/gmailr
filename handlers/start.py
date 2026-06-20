"""
Start Handler - User-facing Gmail Farmer menu
"""

import re
import logging
from pyrogram import Client, filters
from pyrogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from config import SUPPORT_USERNAME
from utils.decorators import admin_only

logger = logging.getLogger(__name__)

user_states = {}



def format_price_dual(usd_val: float, decimals: int, exchange_rate: float = 100.0) -> str:
    inr_val = usd_val * exchange_rate
    if inr_val == int(inr_val):
        inr_str = f"{int(inr_val)}"
    else:
        inr_str = f"{inr_val:.3f}".rstrip('0').rstrip('.')
    usd_str = f"{usd_val:.{decimals}f}"
    return f"{inr_str}₹ ~( {usd_str}$)"


def apply_constant_reward_to_text(text: str, reward_val: float, exchange_rate: float = 100.0) -> str:
    if not text:
        return text
    
    reward_str = format_price_dual(reward_val, 3, exchange_rate)
    
    range_pattern = r'get from (?:[0-9.]+(?:₹|\$)?(?:\s*~\s*\(\s*0\.\d+\s*\$\s*\))?)\s*to\s*(?:[0-9.]+(?:₹|\$)?(?:\s*~\s*\(\s*0\.\d+\s*\$\s*\))?)'
    text = re.sub(range_pattern, f"get {reward_str}", text, flags=re.IGNORECASE)
    
    credit_pattern = r'(?:[0-9.]+(?:₹|\$)?(?:\s*~\s*\(\s*0\.\d+\s*\$\s*\))?)\s*credited to hold'
    text = re.sub(credit_pattern, f"{reward_str} credited to hold", text, flags=re.IGNORECASE)
    
    return text


@Client.on_message(filters.command("start") & filters.private)
async def start_command(client: Client, message: Message):
    """Handle /start command - Show Gmail Farmer menu to users"""
    user = message.from_user
    mongo = client.mongo
    
    # Parse referral parameter
    referred_by = None
    if len(message.command) > 1:
        arg = message.command[1]
        if arg.startswith("ref_"):
            try:
                referrer_id = int(arg.split("_")[1])
                if referrer_id != user.id:
                    referred_by = referrer_id
            except (ValueError, IndexError):
                pass
                
    # Register user in database
    user_doc, is_new = await mongo.get_or_create_user(
        user_id=user.id,
        username=user.username,
        first_name=user.first_name,
        referred_by=referred_by
    )
    
    if is_new and referred_by:
        referral_reward_inr = await mongo.get_system_setting("referral_reward_inr", 0.0)
        if referral_reward_inr > 0:
            try:
                exchange_rate = await mongo.get_system_setting("exchange_rate", 100.0)
                reward_usd = referral_reward_inr / exchange_rate
                reward_str = format_price_dual(reward_usd, 3, exchange_rate)
                
                referrer_notify_text = (
                    f"🎉 **New Referral!**\n\n"
                    f"User {user.mention} (ID: `{user.id}`) joined using your referral link.\n"
                    f"💰 **You received:** {reward_str} directly to your Main Balance!"
                )
                await client.send_message(chat_id=referred_by, text=referrer_notify_text)
            except Exception as e:
                logger.error(f"Failed to notify referrer {referred_by}: {e}")
    
    reward_amount = await mongo.get_system_setting("reward_amount", 0.0)
    exchange_rate = await mongo.get_system_setting("exchange_rate", 100.0)
    rate_str = format_price_dual(reward_amount, 3, exchange_rate)
    
    welcome_text = f"""![👋](tg://emoji?id=6023985511482268644) **Welcome {user.mention}!**
![💸](tg://emoji?id=6030352469786105758) **Earn Money by Registering Gmail Accounts!**

![🎯](tg://emoji?id=6025879072368761539) Get paid for every Gmail account you create!

![💰](tg://emoji?id=6030558512252197022) **You will earn:** {rate_str} per account.

━━━━━━━━━━━━━━━━━━━━
![💡](tg://emoji?id=6019364380074843443) **How it works (Super Simple):**

![1️⃣](tg://emoji?id=6035214020577859654) Our bot will provide you with the registration details.
![2️⃣](tg://emoji?id=6032932813123098123) Copy the data and create the Gmail account on Google.
![3️⃣](tg://emoji?id=6035205087045884098) Submit the account details back to the bot and get paid instantly! ![🚀](tg://emoji?id=6021813997492246416)"""


    # User menu keyboard (Reply Keyboard)
    user_keyboard = ReplyKeyboardMarkup(
        [
            [
                KeyboardButton("➕ New Account"),
                KeyboardButton("📋 My Accounts")
            ],
            [
                KeyboardButton("💳 Balance"),
                KeyboardButton("👥 My Refferals")
            ]
        ],
        resize_keyboard=True,
        is_persistent=True
    )

    guide_enabled = await mongo.get_system_setting("guide_enabled", False)
    if guide_enabled:
        welcome_markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("❓ How to create account", callback_data="guide_view")]
        ])
        await message.reply(
            text=welcome_text,
            reply_markup=welcome_markup
        )
        await message.reply(
            text="👋 **Select an option from the menu below to get started:**",
            reply_markup=user_keyboard
        )
    else:
        await message.reply(
            text=welcome_text,
            reply_markup=user_keyboard
        )


from pyrogram.enums import ParseMode

def parse_registration_details(text: str) -> dict:
    details = {}
    
    # Extract First name
    fn_match = re.search(r'First name:\s*`?([^`\n\r]+)`?', text)
    if fn_match:
        details['first_name'] = fn_match.group(1).strip()
        
    # Extract Last name
    ln_match = re.search(r'Last name:\s*`?([^`\n\r]+)`?', text)
    if ln_match:
        details['last_name'] = ln_match.group(1).strip()
        
    # Extract Email
    email_match = re.search(r'Email:\s*`?([^`\s\n\r]+)`?@gmail\.com', text)
    if email_match:
        details['email'] = f"{email_match.group(1).strip()}@gmail.com"
    else:
        email_match = re.search(r'Email:\s*`?([^`\n\r]+)`?', text)
        if email_match:
            email_val = email_match.group(1).strip()
            if "@" not in email_val:
                email_val = f"{email_val}@gmail.com"
            details['email'] = email_val
        
    # Extract Password
    pwd_match = re.search(r'Password:\s*`?([^`\n\r]+)`?', text)
    if pwd_match:
        details['password'] = pwd_match.group(1).strip()
        
    # Extract Recovery email
    rec_match = re.search(r'(?:Recovery email|Recovery)\s*:?\s*[\r\n]*\s*`?([^\s\n\r`]+)`?', text, re.IGNORECASE)
    if rec_match:
        details['recovery_email'] = rec_match.group(1).strip()
        
    return details


def make_registration_keyboard(reg_id: str, buttons: list, reward_amount: float = 0.0, guide_enabled: bool = False, recovery_enabled: bool = False, logout_enabled: bool = False) -> InlineKeyboardMarkup:
    keyboard_rows = []
    has_target_logout_btn = False
    has_done_btn = False
    if buttons:
        for row in buttons:
            row_buttons = []
            for btn in row:
                btn_text_lower = btn['text'].lower()
                if "how to logout" in btn_text_lower:
                    has_target_logout_btn = True
                if "done" in btn_text_lower:
                    has_done_btn = True
                # Hide how-to guides / help buttons and 2FA buttons
                if "how to create" in btn_text_lower or "how to enable" in btn_text_lower or "how to logout" in btn_text_lower or "enable 2fa" in btn_text_lower:
                    continue
                callback_data = f"reg_btn:{reg_id}:{btn['row']}:{btn['col']}"
                btn_text = btn['text'].replace("💔", "❤️")
                btn_text = re.sub(r'0\.\d+', f"{reward_amount:.3f}", btn_text)
                row_buttons.append(InlineKeyboardButton(text=btn_text, callback_data=callback_data))
            if row_buttons:
                keyboard_rows.append(row_buttons)
                
    if guide_enabled and has_done_btn:
        keyboard_rows.append([InlineKeyboardButton("❓ How to create account", callback_data="guide_view")])
        
    if recovery_enabled and has_done_btn:
        keyboard_rows.append([InlineKeyboardButton("📧 How to add recovery email", callback_data="recovery_view")])
        
    if logout_enabled and has_target_logout_btn:
        keyboard_rows.append([InlineKeyboardButton("🚪 How to logout", callback_data="logout_view")])
        
    if not keyboard_rows:
        return None
    return InlineKeyboardMarkup(keyboard_rows)


def make_history_keyboard(transactions, total_count, page, exchange_rate, per_page=5) -> InlineKeyboardMarkup:
    keyboard = []
    for tx in transactions:
        status = tx.get("status")
        tx_type = tx.get("type", "registration")
        
        if status == "hold":
            emoji = "⏳"
        elif status in ["completed", "credited", "approved"]:
            emoji = "✅"
        elif status in ["rejected", "cancelled"]:
            emoji = "❌"
        elif status == "pending":
            emoji = "🕒"
        else:
            emoji = "ℹ️"
            
        if tx_type == "payout":
            details = tx.get("details", {})
            method = details.get("method", "crypto").upper()
            amount_usd = tx.get("amount_usd", 0.0)
            abs_usd = abs(amount_usd)
            if method == "UPI":
                inr_amount = details.get("inr_amount", abs_usd * 100.0)
                inr_str = f"{int(inr_amount)}" if inr_amount == int(inr_amount) else f"{inr_amount:.2f}"
                title = f"Withdraw (UPI) - {inr_str}₹"
            else:
                title = f"Withdraw ({method}) - {abs_usd:.3f}$"
        elif tx_type == "admin_adjustment":
            amt = tx.get("amount_usd", 0.0)
            sign = "+" if amt >= 0 else ""
            title = f"Admin Adjustment - {sign}{amt:.3f}$"
        elif tx_type == "referral_commission":
            amount_usd = tx.get("amount_usd", 0.0)
            title = f"Commission - {amount_usd:.3f}$"
        elif tx_type == "referral":
            details = tx.get("details", {})
            reward_inr = details.get("reward_inr", 0.0)
            title = f"Referral Reward - {int(reward_inr)}₹"
        else:
            title = tx.get("email", "Gmail Registration")
            if title and "@" not in title:
                title = f"{title}@gmail.com"
                
        tx_id = str(tx["_id"])
        keyboard.append([InlineKeyboardButton(f"{emoji} {title}", callback_data=f"tx_view:{tx_id}:{page}")])
    
    # Pagination row
    nav_row = []
    if page > 1:
        nav_row.append(InlineKeyboardButton("⬅️ Previous", callback_data=f"tx_page:{page-1}"))
    if total_count > page * per_page:
        nav_row.append(InlineKeyboardButton("Next ➡️", callback_data=f"tx_page:{page+1}"))
    
    if nav_row:
        keyboard.append(nav_row)
        
    # Close / back button
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="tx_close")])
    return InlineKeyboardMarkup(keyboard)
 
 
def make_history_text(transactions, page, total_pages, exchange_rate) -> str:
    lines = [f"![📋](tg://emoji?id=6021435576513730578) **Your Transaction History (Page {page}/{total_pages}):**\n"]
    from datetime import timedelta
    
    for i, tx in enumerate(transactions, 1):
        status = tx.get("status")
        tx_type = tx.get("type", "registration")
        amount_usd = tx.get("amount_usd", 0.0)
        
        # Determine status emoji
        if status == "hold":
            emoji = "⏳"
        elif status in ["completed", "credited", "approved"]:
            emoji = "✅"
        elif status in ["rejected", "cancelled"]:
            emoji = "❌"
        elif status == "pending":
            emoji = "🕒"
        else:
            emoji = "ℹ️"
            
        created_ist = tx["created_at"] + timedelta(hours=5, minutes=30)
        date_str = created_ist.strftime("%Y-%m-%d %H:%M")
        
        if tx_type == "payout":
            details = tx.get("details", {})
            method = details.get("method", "UPI").upper()
            title = f"Withdraw ({method})"
            amount_str = format_price_dual(amount_usd, 3, exchange_rate)
        elif tx_type == "admin_adjustment":
            title = "Admin Adjustment"
            sign = "+" if amount_usd >= 0 else ""
            amount_str = f"{sign}{amount_usd:.3f}$"
        elif tx_type == "referral_commission":
            title = "Profit: Someone created"
            amount_str = format_price_dual(amount_usd, 3, exchange_rate)
        elif tx_type == "referral":
            details = tx.get("details", {})
            ref_id = details.get("referred_user_id", "Unknown")
            ref_uname = details.get("referred_username", "")
            user_part = f" (@{ref_uname})" if ref_uname else ""
            title = f"Referral Reward - ID {ref_id}{user_part}"
            amount_str = format_price_dual(amount_usd, 3, exchange_rate)
        else:
            title = "Gmail Registration"
            email = tx.get("email", "")
            if email:
                if "@" not in email:
                    email = f"{email}@gmail.com"
                title += f" (`{email}`)"
            amount_str = format_price_dual(amount_usd, 3, exchange_rate)
            
        item_num = (page - 1) * 5 + i
        lines.append(f"**{item_num}.** {emoji} **{title}**")
        lines.append(f"   Amount: {amount_str} | {date_str}\n")
        
    return "\n".join(lines)


def make_accounts_page_text(accounts, page, total, per_page=5) -> str:
    if not accounts:
        return "![📋](tg://emoji?id=6021435576513730578) **You don't have any active accounts registered in the last 10 hours.**"
        
    total_pages = (total + per_page - 1) // per_page
    if total_pages == 0:
        total_pages = 1
        
    lines = [f"![📋](tg://emoji?id=6021435576513730578) **Your Active Accounts (Page {page}/{total_pages}):**\n"]
    for acc in accounts:
        lines.append(f"`{acc['email']}`")
        lines.append(f"{acc['status']}")
        lines.append(f"Created: {acc['created_at']}\n")
        
    return "\n".join(lines)


def make_accounts_keyboard(total_count, page, per_page=5) -> InlineKeyboardMarkup:
    keyboard = []
    nav_row = []
    if page > 1:
        nav_row.append(InlineKeyboardButton("⬅️ Previous", callback_data=f"acc_page:{page-1}"))
    if total_count > page * per_page:
        nav_row.append(InlineKeyboardButton("Next ➡️", callback_data=f"acc_page:{page+1}"))
    if nav_row:
        keyboard.append(nav_row)
    
    keyboard.append([InlineKeyboardButton("🔙 Close", callback_data="acc_close")])
    return InlineKeyboardMarkup(keyboard)


async def handle_user_state_input(client: Client, message: Message):
    user_id = message.from_user.id
    state_info = user_states.get(user_id)
    if not state_info:
        return
        
    state = state_info.get("state")
    mongo = client.mongo
    
    if state == "payout_amount":
        try:
            amount = float(message.text.strip())
        except ValueError:
            await message.reply("❌ **Invalid amount.** Please enter a valid number:")
            return
            
        method = state_info.get("method")
        exchange_rate = await mongo.get_system_setting("exchange_rate", 100.0)
        balances = await mongo.update_and_get_balance(user_id)
        main_balance_usd = balances.get("main_balance_usd", 0.0)
        
        if method == "crypto":
            fee_enabled = await mongo.get_system_setting("payout_crypto_fee_enabled", False)
            fee_amount = await mongo.get_system_setting("payout_crypto_fee_amount", 0.0) if fee_enabled else 0.0
            crypto_min = await mongo.get_system_setting("payout_crypto_min", 0.1)
            
            if amount <= fee_amount:
                await message.reply(f"❌ **Requested amount must be strictly greater than the fee of {fee_amount}$.** Please enter a valid amount:")
                return
            if amount < crypto_min:
                await message.reply(f"❌ **Minimum withdraw amount is {crypto_min}$.** Please enter a valid amount:")
                return
            if main_balance_usd < amount:
                amount_str = format_price_dual(amount, 3, exchange_rate)
                bal_str = format_price_dual(main_balance_usd, 3, exchange_rate)
                await message.reply(
                    f"❌ **Insufficient balance.** You requested {amount_str}, but your main balance is {bal_str}.\n"
                    f"Please enter a smaller amount or click a menu button to cancel:"
                )
                return
            
            state_info["amount"] = amount
            state_info["state"] = "payout_address"
            network = state_info.get("network", "").upper().replace("_", " ")
            await message.reply(f"✈️ **Please enter your {network} wallet address:**")
            
        elif method == "upi":
            fee_enabled = await mongo.get_system_setting("payout_upi_fee_enabled", True)
            fee_amount = await mongo.get_system_setting("payout_upi_fee_amount", 10.0) if fee_enabled else 0.0
            upi_min = await mongo.get_system_setting("payout_upi_min", 20.0)
            
            if amount <= fee_amount:
                await message.reply(f"❌ **Requested amount must be strictly greater than the fee of {fee_amount}₹.** Please enter a valid amount:")
                return
            if amount < upi_min:
                await message.reply(f"❌ **Minimum withdraw amount is {upi_min}₹.** Please enter a valid amount:")
                return
                
            requested_usd = amount / exchange_rate
            if main_balance_usd < requested_usd:
                amount_str = f"{amount}₹"
                bal_str = format_price_dual(main_balance_usd, 3, exchange_rate)
                await message.reply(
                    f"❌ **Insufficient balance.** You requested {amount_str}, but your main balance is {bal_str}.\n"
                    f"Please enter a smaller amount or click a menu button to cancel:"
                )
                return
                
            state_info["amount"] = requested_usd
            state_info["amount_inr"] = amount
            state_info["state"] = "payout_address"
            await message.reply("💳 **Please enter your UPI ID (e.g. username@bank):**")
            
    elif state == "payout_address":
        address = message.text.strip()
        if len(address) < 4:
            await message.reply("❌ **Invalid input.** Please enter a valid withdrawal destination:")
            return
            
        method = state_info.get("method")
        amount_usd = state_info.get("amount")
        network = state_info.get("network")
        
        exchange_rate = await mongo.get_system_setting("exchange_rate", 100.0)
        
        details = {
            "method": method,
            "address": address,
        }
        if method == "crypto":
            details["network"] = network
            fee_enabled = await mongo.get_system_setting("payout_crypto_fee_enabled", False)
            fee_amount = await mongo.get_system_setting("payout_crypto_fee_amount", 0.0) if fee_enabled else 0.0
            net_usd = amount_usd - fee_amount
            details["fee_usd"] = fee_amount
            details["net_amount_usd"] = net_usd
            
            fee_str = f"{fee_amount}$ fee" if fee_enabled else "no fees"
            amount_str = format_price_dual(amount_usd, 3, exchange_rate)
            log_amount_str = f"{amount_usd:.3f}$ (Net: {net_usd:.3f}$ after {fee_amount}$ fee)" if fee_enabled else f"{amount_usd:.3f}$"
            payout_details_str = f"Crypto ({network.upper()})"
            destination_label = "Wallet Address"
        else:
            inr_amount = state_info.get("amount_inr")
            fee_enabled = await mongo.get_system_setting("payout_upi_fee_enabled", True)
            fee_amount = await mongo.get_system_setting("payout_upi_fee_amount", 10.0) if fee_enabled else 0.0
            net_inr = inr_amount - fee_amount
            details["inr_amount"] = inr_amount
            details["fee_inr"] = fee_amount
            details["net_amount_inr"] = net_inr
            
            fee_str = f"{fee_amount}₹ fee" if fee_enabled else "no fees"
            amount_str = f"{inr_amount}₹"
            log_amount_str = f"{inr_amount} INR (Net: {net_inr} INR after {fee_amount}₹ fee)" if fee_enabled else f"{inr_amount} INR"
            payout_details_str = "UPI"
            destination_label = "UPI ID"
            
        tx_id = await mongo.add_balance_transaction(
            user_id=user_id,
            amount_usd=-amount_usd,
            status="pending",
            type="payout",
            details=details
        )
        
        if not tx_id:
            await message.reply("❌ **An error occurred processing your withdrawal. Please try again later.**")
            if user_id in user_states:
                del user_states[user_id]
            return
            
        from config import PAYOUT_LOG_GROUP_ID
        if PAYOUT_LOG_GROUP_ID:
            user_mention = message.from_user.mention
            user_fullname = f"{message.from_user.first_name or ''} {message.from_user.last_name or ''}".strip() or "None"
            
            log_text = f"""💸 **New Payout Request!**
            
👤 **User:** {user_mention} (ID: `{user_id}`)
📛 **Name:** {user_fullname}
💰 **Amount:** `{log_amount_str}`
💳 **Type:** {payout_details_str}
📌 **{destination_label}:** `{address}`
🚦 **Status:** Pending Approval"""
            
            payout_keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("🟢 Approve", callback_data=f"payout_approve:{tx_id}"),
                    InlineKeyboardButton("🔴 Reject", callback_data=f"payout_reject:{tx_id}")
                ]
            ])
            
            try:
                await client.send_message(
                    chat_id=PAYOUT_LOG_GROUP_ID,
                    text=log_text,
                    reply_markup=payout_keyboard
                )
            except Exception as e:
                logger.error(f"Failed to send message to payout log group: {e}")
                
        if user_id in user_states:
            del user_states[user_id]
            
        await message.reply(
            f"✅ **Your withdrawal request of {amount_str} has been submitted successfully!**\n"
            f"It is currently pending approval. You will receive a notification once processed."
        )


# Placeholder handlers for the reply keyboard buttons
@Client.on_message(filters.text & filters.private & ~filters.command(["start", "admin", "check", "addbalance", "removebalance", "addholdbalance", "removeholdbalance", "waittime", "checkholds", "broadcast", "stats", "user", "payout", "commission", "setup", "minimumpayout", "admincommands", "login", "margin", "setmargin"]))
async def placeholder_buttons_handler(client: Client, message: Message):
    """Handle placeholder button clicks"""
    text = message.text
    mongo = client.mongo
    user_id = message.from_user.id
    
    # If a menu button is clicked, clear user state
    MENU_BUTTONS = ["➕ New Account", "📋 My Accounts", "💳 Balance", "👥 My Refferals", "💸 Payout", "📋 Balance History", "🔙 Back"]
    if text in MENU_BUTTONS:
        if user_id in user_states:
            del user_states[user_id]
    elif user_id in user_states:
        await handle_user_state_input(client, message)
        return
        
    if text == "➕ New Account":
        # Check cooldown limit since the last registration that is not cancelled
        from datetime import datetime
        cooldown_duration = await mongo.get_system_setting("registration_cooldown", 900)
        latest_reg = await mongo.get_latest_registration(message.from_user.id)
        if latest_reg and latest_reg.get("status") != "cancelled":
            ref_time = latest_reg.get("created_at") or latest_reg.get("updated_at")
            time_diff = datetime.utcnow() - ref_time
            if time_diff.total_seconds() < cooldown_duration:
                remaining_seconds = cooldown_duration - int(time_diff.total_seconds())
                minutes = remaining_seconds // 60
                seconds = remaining_seconds % 60
                time_str = f"{minutes}m {seconds}s" if minutes > 0 else f"{seconds}s"
                
                cooldown_minutes = cooldown_duration // 60
                cooldown_sec = cooldown_duration % 60
                if cooldown_minutes > 0:
                    cooldown_str = f"{cooldown_minutes} minutes" if cooldown_sec == 0 else f"{cooldown_minutes}m {cooldown_sec}s"
                else:
                    cooldown_str = f"{cooldown_sec} seconds"
                
                await message.reply(f"![⚠️](tg://emoji?id=6021319161425172520) **You can request a new account only once every {cooldown_str}. Please complete old data or wait till then.**\n\nPlease wait `{time_str}` before trying again.")
                return

        processing_msg = await message.reply("![📤](tg://emoji?id=5873225338984599714) **Processing data...**")
        userbot_manager = client.userbot_manager
        
        res = await userbot_manager.send_register_request(message.from_user.id, processing_msg.id)
        if not res.get("success"):
            support_contact = f"@{SUPPORT_USERNAME}" if SUPPORT_USERNAME else "@support"
            await processing_msg.edit_text(
                f"Please try again later in 1-2 minutes or contact {support_contact} to fix this problem.\n\n"
                f"Error: {res.get('error', 'UBNOAVAILABLE')}"
            )
    elif text == "📋 My Accounts":
        accounts, total = await mongo.get_my_accounts_page(message.from_user.id, 1)
        if not accounts:
            await message.reply("![📋](tg://emoji?id=6021435576513730578) **You don't have any active accounts registered in the last 10 hours.**")
        else:
            text_content = make_accounts_page_text(accounts, 1, total)
            reply_markup = make_accounts_keyboard(total, 1)
            await message.reply(text_content, reply_markup=reply_markup)
    elif text == "💳 Balance":
        balances = await mongo.update_and_get_balance(message.from_user.id)
        main_usd = balances.get("main_balance_usd", 0.0)
        hold_usd = balances.get("hold_balance_usd", 0.0)
        
        exchange_rate = await mongo.get_system_setting("exchange_rate", 100.0)
        main_str = format_price_dual(main_usd, 3, exchange_rate)
        hold_str = format_price_dual(hold_usd, 3, exchange_rate)
        
        balance_text = f"""![💰](tg://emoji?id=6030558512252197022) **Your Balance Dashboard**
 
![💳](tg://emoji?id=6030602393933060595) **Main Balance:** {main_str}
![⏳](tg://emoji?id=5807485774983077261) **Hold Balance:** {hold_str}
 
Hold funds will automatically be transferred to your Main Balance after the hold period expires."""
 
        balance_keyboard = ReplyKeyboardMarkup(
            [
                [
                    KeyboardButton("💸 Payout"),
                    KeyboardButton("📋 Balance History")
                ],
                [
                    KeyboardButton("🔙 Back")
                ]
            ],
            resize_keyboard=True,
            is_persistent=True
        )
        await message.reply(balance_text, reply_markup=balance_keyboard)
    elif text == "💸 Payout":
        balances = await mongo.update_and_get_balance(message.from_user.id)
        main_usd = balances.get("main_balance_usd", 0.0)
        exchange_rate = await mongo.get_system_setting("exchange_rate", 100.0)
        main_str = format_price_dual(main_usd, 3, exchange_rate)
        
        crypto_enabled = await mongo.get_system_setting("payout_crypto_enabled", True)
        upi_enabled = await mongo.get_system_setting("payout_upi_enabled", True)
        
        crypto_fee_enabled = await mongo.get_system_setting("payout_crypto_fee_enabled", False)
        crypto_fee_amount = await mongo.get_system_setting("payout_crypto_fee_amount", 0.0)
        upi_fee_enabled = await mongo.get_system_setting("payout_upi_fee_enabled", True)
        upi_fee_amount = await mongo.get_system_setting("payout_upi_fee_amount", 10.0)
        
        crypto_fee_str = f"{crypto_fee_amount}$ fee" if crypto_fee_enabled else "no fees"
        upi_fee_str = f"{upi_fee_amount}₹ fee" if upi_fee_enabled else "no fees"
        
        crypto_min = await mongo.get_system_setting("payout_crypto_min", 0.1)
        upi_min = await mongo.get_system_setting("payout_upi_min", 20.0)
        
        status_lines = []
        payout_buttons = []
        
        if crypto_enabled:
            status_lines.append(f"• **Crypto:** Min {crypto_min}$, {crypto_fee_str}")
            payout_buttons.append(InlineKeyboardButton("🪙 Crypto", callback_data="payout_method:crypto"))
        else:
            status_lines.append("• **Crypto:** Disabled 🔴")
            
        if upi_enabled:
            status_lines.append(f"• **UPI:** Min {upi_min}₹, {upi_fee_str}")
            payout_buttons.append(InlineKeyboardButton("💳 UPI", callback_data="payout_method:upi"))
        else:
            status_lines.append("• **UPI:** Disabled 🔴")
            
        payout_text = f"💸 **Withdrawal Payout Options**\n\nYour Main Balance: {main_str}\n\n" + "\n".join(status_lines) + "\n\nPlease select your payout option:"
        payout_keyboard = InlineKeyboardMarkup([payout_buttons]) if payout_buttons else None
        
        if not payout_buttons:
            payout_text = f"💸 **Withdrawal Payout Options**\n\nYour Main Balance: {main_str}\n\n⚠️ **Payout options are currently disabled by Admin.** Please try again later."
            
        await message.reply(payout_text, reply_markup=payout_keyboard)
    elif text == "📋 Balance History":
        await mongo.update_and_get_balance(message.from_user.id)
        transactions, total = await mongo.get_transactions_page(message.from_user.id, 1)
        if not transactions:
            await message.reply("![📋](tg://emoji?id=6021435576513730578) **You don't have any transaction history yet.**")
        else:
            total_pages = (total + 4) // 5
            if total_pages == 0:
                total_pages = 1
            exchange_rate = await mongo.get_system_setting("exchange_rate", 100.0)
            reply_markup = make_history_keyboard(transactions, total, 1, exchange_rate)
            text_content = make_history_text(transactions, 1, total_pages, exchange_rate)
            await message.reply(text_content, reply_markup=reply_markup)
    elif text == "🔙 Back":
        user = message.from_user
        reward_amount = await mongo.get_system_setting("reward_amount", 0.0)
        exchange_rate = await mongo.get_system_setting("exchange_rate", 100.0)
        rate_str = format_price_dual(reward_amount, 3, exchange_rate)
        
        welcome_text = f"""![👋](tg://emoji?id=6023985511482268644) **Welcome {user.mention}!**
![💸](tg://emoji?id=6030352469786105758) **Earn Money by Registering Gmail Accounts!**

![🎯](tg://emoji?id=6025879072368761539) Get paid for every Gmail account you create!

![💰](tg://emoji?id=6030558512252197022) **You will earn:** {rate_str} per account.

━━━━━━━━━━━━━━━━━━━━
![💡](tg://emoji?id=6019364380074843443) **How it works (Super Simple):**

![1️⃣](tg://emoji?id=6035214020577859654) Our bot will provide you with the registration details.
![2️⃣](tg://emoji?id=6032932813123098123) Copy the data and create the Gmail account on Google.
![3️⃣](tg://emoji?id=6035205087045884098) Submit the account details back to the bot and get paid instantly! ![🚀](tg://emoji?id=6021813997492246416)"""

        user_keyboard = ReplyKeyboardMarkup(
            [
                [
                    KeyboardButton("➕ New Account"),
                    KeyboardButton("📋 My Accounts")
                ],
                [
                    KeyboardButton("💳 Balance"),
                    KeyboardButton("👥 My Refferals")
                ]
            ],
            resize_keyboard=True,
            is_persistent=True
        )
        
        guide_enabled = await mongo.get_system_setting("guide_enabled", False)
        if guide_enabled:
            welcome_markup = InlineKeyboardMarkup([
                [InlineKeyboardButton("❓ How to create account", callback_data="guide_view")]
            ])
            await message.reply(
                text=welcome_text,
                reply_markup=welcome_markup
            )
            await message.reply(
                text="👋 **Select an option from the menu below to get started:**",
                reply_markup=user_keyboard
            )
        else:
            await message.reply(
                text=welcome_text,
                reply_markup=user_keyboard
            )
    elif text == "👥 My Refferals":
        ref_count = await mongo.users.count_documents({"referred_by": message.from_user.id})
        bot_info = await client.get_me()
        ref_link = f"https://t.me/{bot_info.username}?start=ref_{message.from_user.id}"
        
        # Calculate total referral commission earned
        pipeline_comm = [
            {"$match": {"user_id": message.from_user.id, "type": "referral_commission", "status": "credited"}},
            {"$group": {"_id": None, "total": {"$sum": "$amount_usd"}}}
        ]
        res_comm = await mongo.db["transactions"].aggregate(pipeline_comm).to_list(length=None)
        total_commission_usd = res_comm[0]["total"] if res_comm else 0.0
        
        commission_usd = await mongo.get_system_setting("referral_commission_usd", 0.4)
        exchange_rate = await mongo.get_system_setting("exchange_rate", 100.0)
        commission_str = format_price_dual(commission_usd, 3, exchange_rate)
        total_comm_str = format_price_dual(total_commission_usd, 3, exchange_rate)
        
        ref_text = (
            f"👥 **Referral Program**\n\n"
            f"Share your referral link with others to invite them to use the bot!\n\n"
            f"💰 **Commission Rate:** {commission_str} per approved account created by your referrals\n"
            f"💵 **Total Commission Earned:** {total_comm_str}\n\n"
            f"🔗 **Your Referral Link:**\n`{ref_link}`\n\n"
            f"📊 **Total Referrals:** `{ref_count}` **(Rewards are not paid on signup)**\n\n"
            f"⚠️ **Note:** Referral bonus is not paid for just joining. You will earn commission only when your referred user successfully registers a Gmail account and it gets approved by the system."
        )
        await message.reply(ref_text)


last_reg_button_clicks = {}


@Client.on_callback_query(filters.regex(r"^reg_btn:"))
async def reg_button_click_handler(client: Client, callback: CallbackQuery):
    """Handle clicking on registration flow buttons"""
    data = callback.data.split(":")
    if len(data) < 4:
        await callback.answer("❌ Invalid callback data", show_alert=True)
        return
        
    reg_id = data[1]
    row = int(data[2])
    col = int(data[3])
    
    # Extract button text to uniquely identify this button
    button_text = ""
    if callback.message and callback.message.reply_markup:
        try:
            for r in callback.message.reply_markup.inline_keyboard:
                for b in r:
                    if b.callback_data == callback.data:
                        button_text = b.text
                        break
                if button_text:
                    break
        except Exception:
            pass
            
    if not button_text:
        button_text = f"btn_{row}_{col}"
        
    user_id = callback.from_user.id
    message_id = callback.message.id if callback.message else 0
    click_key = (user_id, message_id, button_text)
    
    from datetime import datetime
    now = datetime.utcnow()
    if click_key in last_reg_button_clicks:
        time_diff = (now - last_reg_button_clicks[click_key]).total_seconds()
        if time_diff < 15.0:
            remaining = int(15.0 - time_diff)
            if remaining < 1:
                remaining = 1
            await callback.answer(f"Please avoid multiple or fast clicks. Please wait {remaining}s before clicking again.", show_alert=True)
            return

    last_reg_button_clicks[click_key] = now
    
    mongo = client.mongo
    userbot_manager = client.userbot_manager
    
    # Resolve phone and msg_id from DB using reg_id
    from bson import ObjectId
    from datetime import datetime, timedelta
    try:
        registration = await mongo.db["registrations"].find_one({"_id": ObjectId(reg_id)})
    except Exception:
        registration = None
        
    if not registration:
        await callback.answer("❌ Registration session not found.", show_alert=True)
        return
        
    # Check if registration is older than 10 hours
    reg_time = registration.get("created_at") or registration.get("updated_at")
    if datetime.utcnow() - reg_time > timedelta(hours=10):
        await callback.message.edit_text("![⚠️](tg://emoji?id=6021319161425172520) **This task is last too long use new data**")
        await callback.answer()
        return
        
    await callback.answer("📤 Processing...")
        
    phone = registration.get("phone")
    msg_id = registration.get("msg_id")
    
    # Execute the click via the userbot
    res = await userbot_manager.click_register_button(phone, msg_id, row, col)
    if not res.get("success"):
        await callback.answer(f"❌ Failed: {res.get('error')}", show_alert=True)


@Client.on_callback_query(filters.regex("^main_menu$"))
@admin_only
async def main_menu_callback(client: Client, callback: CallbackQuery):
    """Return to main menu for admin panels"""
    user = callback.from_user
    
    welcome_text = f"""![👋](tg://emoji?id=6023985511482268644) **Welcome to Userbot Manager Bot!**

Hello **{user.first_name}**! 

Send the **/admin** command to access the Userbot Management panel."""

    await callback.message.edit_text(text=welcome_text)
    await callback.answer()


@Client.on_callback_query(filters.regex("^noop$"))
async def noop_callback(client: Client, callback: CallbackQuery):
    """Handle no-operation buttons"""
    await callback.answer()


@Client.on_callback_query(filters.regex(r"^tx_page:"))
async def tx_page_callback(client: Client, callback: CallbackQuery):
    """Handle transaction history pagination"""
    try:
        data = callback.data.split(":")
        page = int(data[1])
        mongo = client.mongo
        user_id = callback.from_user.id
        
        await mongo.update_and_get_balance(user_id)
        transactions, total = await mongo.get_transactions_page(user_id, page)
        if not transactions:
            await callback.answer("No transactions on this page.", show_alert=True)
            return
            
        total_pages = (total + 4) // 5
        if total_pages == 0:
            total_pages = 1
        exchange_rate = await mongo.get_system_setting("exchange_rate", 100.0)
        reply_markup = make_history_keyboard(transactions, total, page, exchange_rate)
        text_content = make_history_text(transactions, page, total_pages, exchange_rate)
        await callback.message.edit_text(text_content, reply_markup=reply_markup)
        await callback.answer()
    except Exception as e:
        await callback.answer(f"Error: {e}", show_alert=True)


@Client.on_callback_query(filters.regex(r"^tx_view:"))
async def tx_view_callback(client: Client, callback: CallbackQuery):
    """Handle viewing detailed transaction log"""
    try:
        data = callback.data.split(":")
        tx_id = data[1]
        page = int(data[2])
        mongo = client.mongo
        user_id = callback.from_user.id
        
        await mongo.update_and_get_balance(user_id)
        tx = await mongo.get_transaction(tx_id)
        if not tx:
            await callback.answer("Transaction details not found.", show_alert=True)
            return
            
        from datetime import timedelta
        created_ist = tx["created_at"] + timedelta(hours=5, minutes=30)
        created_str = created_ist.strftime("%Y-%m-%d %H:%M:%S IST")
        
        tx_type = tx.get("type", "registration")
        status_raw = tx.get("status", "")
        amount_usd = tx.get("amount_usd", 0.0)
        status_str = status_raw.capitalize()
        
        if status_raw == "hold":
            if amount_usd < 0:
                status_str = "Removed from Hold 📉"
            else:
                status_str = "Hold ⏳"
        elif status_raw == "credited":
            if amount_usd < 0:
                status_str = "Deducted 📉" if tx_type == "admin_adjustment" else "Debited 📉"
            else:
                status_str = "Credited ✅"
        elif status_raw == "pending":
            status_str = "Pending Approval 🕒"
        elif status_raw == "completed":
            status_str = "Completed ✅"
        elif status_raw == "rejected":
            status_str = "Rejected ❌"
            
        exchange_rate = await mongo.get_system_setting("exchange_rate", 100.0)
        
        if tx_type == "admin_adjustment":
            sign = "+" if amount_usd >= 0 else ""
            amount_str = f"{sign}{amount_usd:.3f}$"
        else:
            amount_str = format_price_dual(amount_usd, 3, exchange_rate)
        
        if tx_type == "payout":
            details = tx.get("details", {})
            method = details.get("method", "crypto").upper()
            address_label = "UPI ID" if method == "UPI" else "Address"
            address = details.get("address", "")
            network_str = f" ({details.get('network', '').upper()})" if details.get("network") else ""
            
            text = f"""![💸](tg://emoji?id=6030352469786105758) **Withdrawal Payout Details**
            
🚦 **Status:** {status_str}
💳 **Method:** {method}{network_str}
![💰](tg://emoji?id=6030558512252197022) **Amount:** {amount_str}
📌 **{address_label}:** `{address}`
![📅](tg://emoji?id=6023880246128810031) **Requested At:** `{created_str}`"""
        elif tx_type == "admin_adjustment":
            details = tx.get("details", {})
            reason = details.get("reason", "Admin balance adjustment")
            text = f"""⚙️ **Admin Balance Adjustment**

🚦 **Status:** {status_str}
![💰](tg://emoji?id=6030558512252197022) **Amount:** {amount_str}
📝 **Reason:** {reason}
![📅](tg://emoji?id=6023880246128810031) **Date:** `{created_str}`"""
        elif tx_type == "referral":
            details = tx.get("details", {})
            ref_id = details.get("referred_user_id", "Unknown")
            ref_uname = details.get("referred_username", "No Username")
            reward_inr = details.get("reward_inr", 0.0)
            text = f"""🎉 **Referral Reward Details**

🚦 **Status:** {status_str}
![💰](tg://emoji?id=6030558512252197022) **Amount:** {amount_str} (Value: {reward_inr}₹)
👤 **Referred User ID:** `{ref_id}`
📛 **Username:** @{ref_uname}
![📅](tg://emoji?id=6023880246128810031) **Date:** `{created_str}`"""
        else:
            # Gmail registration
            hold_until_str = "N/A"
            if tx.get("hold_until"):
                hold_until_ist = tx["hold_until"] + timedelta(hours=5, minutes=30)
                hold_until_str = hold_until_ist.strftime("%Y-%m-%d %H:%M:%S IST")
                
            if tx.get("credited_at"):
                credited_ist = tx["credited_at"] + timedelta(hours=5, minutes=30)
                credited_str = credited_ist.strftime("%Y-%m-%d %H:%M:%S IST")
            else:
                credited_str = "Not yet credited"
                
            email = tx.get('email', '')
            if email and "@" not in email:
                email = f"{email}@gmail.com"
                
            text = f"""![📄](tg://emoji?id=6021547434641987535) **Transaction Log Details**

📧 **Email:** `{email}`
![💰](tg://emoji?id=6030558512252197022) **Amount:** {amount_str}
🚦 **Status:** {status_str}

![📅](tg://emoji?id=6023880246128810031) **Created At (Hold Start):** `{created_str}`
![⏳](tg://emoji?id=5807485774983077261) **Hold Until:** `{hold_until_str}`
![✅](tg://emoji?id=6026228223145154159) **Credited At:** `{credited_str}`"""

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Back", callback_data=f"tx_page:{page}")]
        ])
        
        await callback.message.edit_text(text, reply_markup=keyboard)
        await callback.answer()
    except Exception as e:
        await callback.answer(f"Error: {e}", show_alert=True)


@Client.on_callback_query(filters.regex(r"^tx_close$"))
async def tx_close_callback(client: Client, callback: CallbackQuery):
    """Close the history inline window"""
    try:
        await callback.message.delete()
        await callback.answer()
    except Exception:
        await callback.answer()


@Client.on_callback_query(filters.regex(r"^acc_page:"))
async def acc_page_callback(client: Client, callback: CallbackQuery):
    """Handle active accounts list pagination"""
    try:
        data = callback.data.split(":")
        page = int(data[1])
        mongo = client.mongo
        user_id = callback.from_user.id
        
        accounts, total = await mongo.get_my_accounts_page(user_id, page)
        if not accounts:
            await callback.answer("No accounts on this page.", show_alert=True)
            return
            
        text_content = make_accounts_page_text(accounts, page, total)
        reply_markup = make_accounts_keyboard(total, page)
        await callback.message.edit_text(text_content, reply_markup=reply_markup)
        await callback.answer()
    except Exception as e:
        await callback.answer(f"Error: {e}", show_alert=True)


@Client.on_callback_query(filters.regex(r"^acc_close$"))
async def acc_close_callback(client: Client, callback: CallbackQuery):
    """Close active accounts list window"""
    try:
        await callback.message.delete()
        await callback.answer()
    except Exception:
        await callback.answer()


@Client.on_callback_query(filters.regex(r"^payout_method:"))
async def payout_method_callback(client: Client, callback: CallbackQuery):
    """Handle choosing Crypto or UPI payout method"""
    user_id = callback.from_user.id
    method = callback.data.split(":")[1]
    mongo = client.mongo
    
    if method == "crypto":
        enabled = await mongo.get_system_setting("payout_crypto_enabled", True)
        if not enabled:
            await callback.answer("❌ Crypto payouts are currently disabled.", show_alert=True)
            return
        payout_crypto_keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("USDT BEP20", callback_data="payout_crypto:usdt_bep20"),
                InlineKeyboardButton("TON", callback_data="payout_crypto:ton")
            ]
        ])
        await callback.message.edit_text(
            "🪙 **Select Crypto Network:**",
            reply_markup=payout_crypto_keyboard
        )
    elif method == "upi":
        enabled = await mongo.get_system_setting("payout_upi_enabled", True)
        if not enabled:
            await callback.answer("❌ UPI payouts are currently disabled.", show_alert=True)
            return
        user_states[user_id] = {"state": "payout_amount", "method": "upi"}
        
        fee_enabled = await mongo.get_system_setting("payout_upi_fee_enabled", True)
        fee_amount = await mongo.get_system_setting("payout_upi_fee_amount", 10.0) if fee_enabled else 0.0
        fee_text = f"{fee_amount}₹ fee applies" if fee_enabled else "no fees"
        upi_min = await mongo.get_system_setting("payout_upi_min", 20.0)
        
        await callback.message.edit_text(
            "💳 **UPI Withdrawal**\n\n"
            f"Please enter the amount in INR (₹) you want to withdraw (Minimum {upi_min}₹, {fee_text}):"
        )
    await callback.answer()


@Client.on_callback_query(filters.regex(r"^payout_crypto:"))
async def payout_crypto_callback(client: Client, callback: CallbackQuery):
    """Handle choosing Crypto network (USDT BEP20 or TON)"""
    user_id = callback.from_user.id
    network = callback.data.split(":")[1]
    mongo = client.mongo
    
    user_states[user_id] = {"state": "payout_amount", "method": "crypto", "network": network}
    
    network_name = network.upper().replace("_", " ")
    
    fee_enabled = await mongo.get_system_setting("payout_crypto_fee_enabled", False)
    fee_amount = await mongo.get_system_setting("payout_crypto_fee_amount", 0.0) if fee_enabled else 0.0
    fee_text = f"{fee_amount}$ fee applies" if fee_enabled else "no fees"
    crypto_min = await mongo.get_system_setting("payout_crypto_min", 0.1)
    
    await callback.message.edit_text(
        f"🪙 **Crypto Withdrawal ({network_name})**\n\n"
        f"Please enter the amount in USD ($) you want to withdraw (Minimum {crypto_min}$, {fee_text}):"
    )
    await callback.answer()


@Client.on_callback_query(filters.regex(r"^payout_approve:"))
async def payout_approve_callback(client: Client, callback: CallbackQuery):
    """Handle admin approval of a payout"""
    admin_id = callback.from_user.id
    mongo = client.mongo
    
    # Check if caller is admin
    if not await mongo.is_admin(admin_id):
        await callback.answer("❌ You are not authorized to perform this action.", show_alert=True)
        return
        
    tx_id = callback.data.split(":")[1]
    tx = await mongo.get_transaction(tx_id)
    if not tx:
        await callback.answer("❌ Transaction not found.", show_alert=True)
        return
        
    if tx.get("status") != "pending":
        await callback.answer(f"❌ This withdrawal is already {tx.get('status')}.", show_alert=True)
        return
        
    # Approve transaction
    success = await mongo.update_transaction_status(tx_id, "completed", {"approved_by": admin_id})
    if success:
        # Notify user
        target_user_id = tx.get("user_id")
        amount_usd = tx.get("amount_usd", 0.0)
        pos_amount = abs(amount_usd)
        
        exchange_rate = await mongo.get_system_setting("exchange_rate", 100.0)
        
        details = tx.get("details", {})
        method = details.get("method", "crypto")
        if method == "upi":
            inr_amount = details.get("inr_amount", 0.0)
            net_inr = details.get("net_amount_inr", 0.0)
            fee_inr = details.get("fee_inr", 0.0)
            if fee_inr > 0:
                amount_str = f"{inr_amount}₹ (Net: {net_inr}₹ after {fee_inr}₹ fee)"
            else:
                amount_str = f"{inr_amount}₹"
        else:
            fee_usd = details.get("fee_usd", 0.0)
            net_usd = details.get("net_amount_usd", pos_amount)
            if fee_usd > 0:
                amount_str = f"{pos_amount:.3f}$ (Net: {net_usd:.3f}$ after {fee_usd}$ fee)"
            else:
                amount_str = f"{pos_amount:.3f}$"
            
        try:
            await client.send_message(
                target_user_id,
                f"✅ **Your payout request of {amount_str} has been approved! Payment has been sent.**"
            )
        except Exception as e:
            logger.error(f"Failed to notify user {target_user_id} of approved payout: {e}")
            
        # Edit admin log message
        admin_mention = callback.from_user.mention
        original_text = callback.message.text
        updated_text = original_text.replace("🚦 **Status:** Pending Approval", f"🚦 **Status:** Approved 🟢\n👤 **Approved By:** {admin_mention}")
        await callback.message.edit_text(updated_text, reply_markup=None)
        await callback.answer("✅ Withdrawal Approved", show_alert=True)
    else:
        await callback.answer("❌ Failed to update transaction status.", show_alert=True)


@Client.on_callback_query(filters.regex(r"^guide_view$"))
async def guide_view_callback(client: Client, callback: CallbackQuery):
    """Handle clicking on 'How to create account' button"""
    mongo = client.mongo
    user_id = callback.from_user.id
    
    guide_chat_id = await mongo.get_system_setting("guide_chat_id")
    guide_message_id = await mongo.get_system_setting("guide_message_id")
    
    if not guide_chat_id or not guide_message_id:
        await callback.answer("⚠️ No guide has been setup yet by admin.", show_alert=True)
        return
        
    await callback.answer("📤 Sending guide...")
    try:
        await client.copy_message(
            chat_id=user_id,
            from_chat_id=guide_chat_id,
            message_id=guide_message_id
        )
    except Exception as e:
        logger.error(f"Failed to copy guide message to {user_id}: {e}")
        try:
            await client.send_message(
                chat_id=user_id,
                text="❌ **Failed to send the guide.** Please contact support or try again later."
            )
        except Exception:
            pass


@Client.on_callback_query(filters.regex(r"^recovery_view$"))
async def recovery_view_callback(client: Client, callback: CallbackQuery):
    """Handle clicking on 'How to add recovery email' button"""
    mongo = client.mongo
    user_id = callback.from_user.id
    
    recovery_chat_id = await mongo.get_system_setting("recovery_chat_id")
    recovery_message_id = await mongo.get_system_setting("recovery_message_id")
    
    if not recovery_chat_id or not recovery_message_id:
        await callback.answer("⚠️ No recovery guide has been setup yet by admin.", show_alert=True)
        return
        
    await callback.answer("📤 Sending guide...")
    try:
        await client.copy_message(
            chat_id=user_id,
            from_chat_id=recovery_chat_id,
            message_id=recovery_message_id
        )
    except Exception as e:
        logger.error(f"Failed to copy recovery guide message to {user_id}: {e}")
        try:
            await client.send_message(
                chat_id=user_id,
                text="❌ **Failed to send the recovery guide.** Please contact support or try again later."
            )
        except Exception:
            pass


@Client.on_callback_query(filters.regex(r"^logout_view$"))
async def logout_view_callback(client: Client, callback: CallbackQuery):
    """Handle clicking on 'How to logout' button"""
    mongo = client.mongo
    user_id = callback.from_user.id
    
    logout_chat_id = await mongo.get_system_setting("logout_chat_id")
    logout_message_id = await mongo.get_system_setting("logout_message_id")
    
    if not logout_chat_id or not logout_message_id:
        await callback.answer("⚠️ No logout guide has been setup yet by admin.", show_alert=True)
        return
        
    await callback.answer("📤 Sending guide...")
    try:
        await client.copy_message(
            chat_id=user_id,
            from_chat_id=logout_chat_id,
            message_id=logout_message_id
        )
    except Exception as e:
        logger.error(f"Failed to copy logout guide message to {user_id}: {e}")
        try:
            await client.send_message(
                chat_id=user_id,
                text="❌ **Failed to send the logout guide.** Please contact support or try again later."
            )
        except Exception:
            pass


@Client.on_callback_query(filters.regex(r"^payout_reject:"))
async def payout_reject_callback(client: Client, callback: CallbackQuery):
    """Handle admin rejection of a payout"""
    admin_id = callback.from_user.id
    mongo = client.mongo
    
    # Check if caller is admin
    if not await mongo.is_admin(admin_id):
        await callback.answer("❌ You are not authorized to perform this action.", show_alert=True)
        return
        
    tx_id = callback.data.split(":")[1]
    tx = await mongo.get_transaction(tx_id)
    if not tx:
        await callback.answer("❌ Transaction not found.", show_alert=True)
        return
        
    if tx.get("status") != "pending":
        await callback.answer(f"❌ This withdrawal is already {tx.get('status')}.", show_alert=True)
        return
        
    # Reject transaction
    success = await mongo.update_transaction_status(tx_id, "rejected", {"rejected_by": admin_id})
    if success:
        # Notify user
        target_user_id = tx.get("user_id")
        amount_usd = tx.get("amount_usd", 0.0)
        pos_amount = abs(amount_usd)
        
        exchange_rate = await mongo.get_system_setting("exchange_rate", 100.0)
        
        details = tx.get("details", {})
        method = details.get("method", "crypto")
        if method == "upi":
            inr_amount = details.get("inr_amount", 0.0)
            amount_str = f"{inr_amount}₹"
        else:
            amount_str = f"{pos_amount:.3f}$"
            
        try:
            await client.send_message(
                target_user_id,
                f"❌ **Your payout request of {amount_str} has been rejected. The funds have been returned to your balance.**"
            )
        except Exception as e:
            logger.error(f"Failed to notify user {target_user_id} of rejected payout: {e}")
            
        # Edit admin log message
        admin_mention = callback.from_user.mention
        original_text = callback.message.text
        updated_text = original_text.replace("🚦 **Status:** Pending Approval", f"🚦 **Status:** Rejected 🔴\n👤 **Rejected By:** {admin_mention}")
        await callback.message.edit_text(updated_text, reply_markup=None)
        await callback.answer("🔴 Withdrawal Rejected", show_alert=True)
    else:
        await callback.answer("❌ Failed to update transaction status.", show_alert=True)