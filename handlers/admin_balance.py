"""
Admin Balance Commands Handler
Provides commands for admins to manage user balances.
"""

from datetime import datetime, timedelta
from pyrogram import Client, filters
from pyrogram.types import Message
from utils.decorators import admin_only
from handlers.start import format_price_dual

@Client.on_message(filters.command("addbalance") & filters.private)
@admin_only
async def add_balance_command(client: Client, message: Message):
    """
    /addbalance <user_id> <currency: usd/inr> <amount>
    Adds to the user's main balance.
    """
    args = message.command
    if len(args) < 4:
        await message.reply("❌ **Usage:** `/addbalance [user_id] [usd/inr] [amount]`")
        return
        
    try:
        target_user_id = int(args[1])
        currency = args[2].lower()
        amount = float(args[3])
    except ValueError:
        await message.reply("❌ **Invalid arguments.** Make sure user_id is an integer and amount is a number.")
        return
        
    if currency not in ["usd", "inr"]:
        await message.reply("❌ **Invalid currency.** Supported currencies: `usd`, `inr`.")
        return
        
    if amount <= 0:
        await message.reply("❌ **Amount must be greater than zero.**")
        return
        
    mongo = client.mongo
    user = await mongo.get_user(target_user_id)
    if not user:
        await message.reply(f"❌ **User with ID {target_user_id} not found in database.**")
        return
        
    exchange_rate = await mongo.get_system_setting("exchange_rate", 100.0)
    
    if currency == "inr":
        amount_usd = amount / exchange_rate
    else:
        amount_usd = amount
        
    res = await mongo.add_balance_transaction(
        user_id=target_user_id,
        amount_usd=amount_usd,
        status="credited",
        type="admin_adjustment",
        details={
            "reason": "Admin added balance",
            "currency": currency,
            "original_amount": amount
        }
    )
    
    if res:
        # Get updated balance
        balances = await mongo.update_and_get_balance(target_user_id)
        main_str = format_price_dual(balances.get("main_balance_usd", 0.0), 3, exchange_rate)
        added_str = format_price_dual(amount_usd, 3, exchange_rate)
        
        await message.reply(
            f"✅ **Successfully added {added_str} to User {target_user_id}'s main balance.**\n"
            f"New Main Balance: {main_str}"
        )
        
        # Notify user
        try:
            await client.send_message(
                target_user_id,
                f"💰 **Admin added {added_str} to your main balance.**\n"
                f"New Main Balance: {main_str}"
            )
        except Exception:
            pass
    else:
        await message.reply("❌ **Failed to update balance in database.**")


@Client.on_message(filters.command("removebalance") & filters.private)
@admin_only
async def remove_balance_command(client: Client, message: Message):
    """
    /removebalance <user_id> <currency: usd/inr> <amount>
    Removes from the user's main balance.
    """
    args = message.command
    if len(args) < 4:
        await message.reply("❌ **Usage:** `/removebalance [user_id] [usd/inr] [amount]`")
        return
        
    try:
        target_user_id = int(args[1])
        currency = args[2].lower()
        amount = float(args[3])
    except ValueError:
        await message.reply("❌ **Invalid arguments.** Make sure user_id is an integer and amount is a number.")
        return
        
    if currency not in ["usd", "inr"]:
        await message.reply("❌ **Invalid currency.** Supported currencies: `usd`, `inr`.")
        return
        
    if amount <= 0:
        await message.reply("❌ **Amount must be greater than zero.**")
        return
        
    mongo = client.mongo
    user = await mongo.get_user(target_user_id)
    if not user:
        await message.reply(f"❌ **User with ID {target_user_id} not found in database.**")
        return
        
    exchange_rate = await mongo.get_system_setting("exchange_rate", 100.0)
    
    if currency == "inr":
        amount_usd = amount / exchange_rate
    else:
        amount_usd = amount
        
    res = await mongo.add_balance_transaction(
        user_id=target_user_id,
        amount_usd=-amount_usd,
        status="credited",
        type="admin_adjustment",
        details={
            "reason": "Admin removed balance",
            "currency": currency,
            "original_amount": amount
        }
    )
    
    if res:
        # Get updated balance
        balances = await mongo.update_and_get_balance(target_user_id)
        main_str = format_price_dual(balances.get("main_balance_usd", 0.0), 3, exchange_rate)
        removed_str = format_price_dual(amount_usd, 3, exchange_rate)
        
        await message.reply(
            f"✅ **Successfully removed {removed_str} from User {target_user_id}'s main balance.**\n"
            f"New Main Balance: {main_str}"
        )
        
        # Notify user
        try:
            await client.send_message(
                target_user_id,
                f"💸 **Admin removed {removed_str} from your main balance.**\n"
                f"New Main Balance: {main_str}"
            )
        except Exception:
            pass
    else:
        await message.reply("❌ **Failed to update balance in database.**")


@Client.on_message(filters.command("addholdbalance") & filters.private)
@admin_only
async def add_hold_balance_command(client: Client, message: Message):
    """
    /addholdbalance <user_id> <currency: usd/inr> <amount> [hold_days]
    Adds to the user's hold balance. Default hold is 15 days.
    """
    args = message.command
    if len(args) < 4:
        await message.reply("❌ **Usage:** `/addholdbalance [user_id] [usd/inr] [amount] [hold_days]`")
        return
        
    try:
        target_user_id = int(args[1])
        currency = args[2].lower()
        amount = float(args[3])
        hold_days = int(args[4]) if len(args) > 4 else 15
    except ValueError:
        await message.reply("❌ **Invalid arguments.** Make sure user_id/hold_days are integers and amount is a number.")
        return
        
    if currency not in ["usd", "inr"]:
        await message.reply("❌ **Invalid currency.** Supported currencies: `usd`, `inr`.")
        return
        
    if amount <= 0:
        await message.reply("❌ **Amount must be greater than zero.**")
        return
        
    mongo = client.mongo
    user = await mongo.get_user(target_user_id)
    if not user:
        await message.reply(f"❌ **User with ID {target_user_id} not found in database.**")
        return
        
    exchange_rate = await mongo.get_system_setting("exchange_rate", 100.0)
    
    if currency == "inr":
        amount_usd = amount / exchange_rate
    else:
        amount_usd = amount
        
    hold_until = datetime.utcnow() + timedelta(days=hold_days)
    
    res = await mongo.add_balance_transaction(
        user_id=target_user_id,
        amount_usd=amount_usd,
        status="hold",
        type="admin_adjustment",
        hold_until=hold_until,
        details={
            "reason": f"Admin added hold balance ({hold_days} days)",
            "currency": currency,
            "original_amount": amount
        }
    )
    
    if res:
        # Get updated balance
        balances = await mongo.update_and_get_balance(target_user_id)
        hold_str = format_price_dual(balances.get("hold_balance_usd", 0.0), 3, exchange_rate)
        added_str = format_price_dual(amount_usd, 3, exchange_rate)
        
        await message.reply(
            f"✅ **Successfully added {added_str} to User {target_user_id}'s hold balance.**\n"
            f"New Hold Balance: {hold_str}"
        )
        
        # Notify user
        try:
            await client.send_message(
                target_user_id,
                f"⏳ **Admin added {added_str} to your hold balance (held for {hold_days} days).**\n"
                f"New Hold Balance: {hold_str}"
            )
        except Exception:
            pass
    else:
        await message.reply("❌ **Failed to update hold balance in database.**")


@Client.on_message(filters.command("removeholdbalance") & filters.private)
@admin_only
async def remove_hold_balance_command(client: Client, message: Message):
    """
    /removeholdbalance <user_id> <currency: usd/inr> <amount>
    Removes from the user's hold balance.
    """
    args = message.command
    if len(args) < 4:
        await message.reply("❌ **Usage:** `/removeholdbalance [user_id] [usd/inr] [amount]`")
        return
        
    try:
        target_user_id = int(args[1])
        currency = args[2].lower()
        amount = float(args[3])
    except ValueError:
        await message.reply("❌ **Invalid arguments.** Make sure user_id is an integer and amount is a number.")
        return
        
    if currency not in ["usd", "inr"]:
        await message.reply("❌ **Invalid currency.** Supported currencies: `usd`, `inr`.")
        return
        
    if amount <= 0:
        await message.reply("❌ **Amount must be greater than zero.**")
        return
        
    mongo = client.mongo
    user = await mongo.get_user(target_user_id)
    if not user:
        await message.reply(f"❌ **User with ID {target_user_id} not found in database.**")
        return
        
    exchange_rate = await mongo.get_system_setting("exchange_rate", 100.0)
    
    if currency == "inr":
        amount_usd = amount / exchange_rate
    else:
        amount_usd = amount
        
    # We set hold_until to 15 days as well so it matches hold status, but with a negative amount
    hold_until = datetime.utcnow() + timedelta(days=15)
    
    res = await mongo.add_balance_transaction(
        user_id=target_user_id,
        amount_usd=-amount_usd,
        status="hold",
        type="admin_adjustment",
        hold_until=hold_until,
        details={
            "reason": "Admin removed hold balance",
            "currency": currency,
            "original_amount": amount
        }
    )
    
    if res:
        # Get updated balance
        balances = await mongo.update_and_get_balance(target_user_id)
        hold_str = format_price_dual(balances.get("hold_balance_usd", 0.0), 3, exchange_rate)
        removed_str = format_price_dual(amount_usd, 3, exchange_rate)
        
        await message.reply(
            f"✅ **Successfully removed {removed_str} from User {target_user_id}'s hold balance.**\n"
            f"New Hold Balance: {hold_str}"
        )
        
        # Notify user
        try:
            await client.send_message(
                target_user_id,
                f"⏳ **Admin removed {removed_str} from your hold balance.**\n"
                f"New Hold Balance: {hold_str}"
            )
        except Exception:
            pass
    else:
        await message.reply("❌ **Failed to update hold balance in database.**")


@Client.on_message(filters.command("waittime") & filters.private)
@admin_only
async def set_waittime_command(client: Client, message: Message):
    """
    /waittime <seconds>
    Sets the registration cooldown in seconds.
    """
    args = message.command
    if len(args) < 2:
        await message.reply("❌ **Usage:** `/waittime [seconds]`")
        return
        
    try:
        seconds = int(args[1])
    except ValueError:
        await message.reply("❌ **Invalid argument.** Make sure seconds is an integer.")
        return
        
    if seconds < 0:
        await message.reply("❌ **Seconds cannot be negative.**")
        return
        
    mongo = client.mongo
    success = await mongo.set_system_setting("registration_cooldown", seconds)
    
    if success:
        minutes = seconds // 60
        sec_rem = seconds % 60
        time_str = f"{minutes}m {sec_rem}s" if minutes > 0 else f"{sec_rem}s"
        
        await message.reply(
            f"✅ **Registration cooldown successfully set to {seconds} seconds ({time_str}).**"
        )
    else:
        await message.reply("❌ **Failed to update registration cooldown in database.**")


@Client.on_message(filters.command("checkholds") & filters.private)
@admin_only
async def check_holds_command(client: Client, message: Message):
    """
    /checkholds
    Manually triggers the check of pending hold accounts.
    Generates text files for each connected userbot and sends them to admin.
    """
    await message.reply("🔄 **Starting manual verification of pending hold accounts...**")
    userbot_manager = client.userbot_manager
    try:
        raw_files = await userbot_manager.check_pending_hold_accounts(save_raw_files=True)
        if raw_files:
            await message.reply("✅ **Verification completed. Sending logs...**")
            import os
            for phone, filepath in raw_files.items():
                if os.path.exists(filepath):
                    try:
                        await message.reply_document(document=filepath, caption=f"Hold Log for Userbot {phone}")
                        os.remove(filepath)
                    except Exception as e:
                        await message.reply(f"⚠️ **Error sending file for {phone}:** `{str(e)}`")
        else:
            await message.reply("✅ **Verification completed.** No connected userbots were checked or no pages were retrieved.")
    except Exception as e:
        await message.reply(f"❌ **Error during verification:** `{str(e)}`")


@Client.on_message(filters.command("broadcast") & filters.private)
@admin_only
async def broadcast_command(client: Client, message: Message):
    """
    /broadcast (as a reply to a message)
    Broadcasts the replied message to all registered users.
    """
    if not message.reply_to_message:
        await message.reply("❌ **Usage:** Reply to a message with `/broadcast` to send it to all users.")
        return
        
    status_msg = await message.reply("🔄 **Fetching users from database...**")
    mongo = client.mongo
    
    try:
        users = await mongo.get_all_users()
        if not users:
            await status_msg.edit_text("❌ **No registered users found in the database.**")
            return
            
        total_users = len(users)
        await status_msg.edit_text(f"🔄 **Starting broadcast to {total_users} users...**")
        
        success_count = 0
        fail_count = 0
        
        broadcast_msg = message.reply_to_message
        
        import asyncio
        from pyrogram.errors import FloodWait
        
        for idx, user in enumerate(users):
            user_id = user.get("user_id")
            if not user_id:
                continue
                
            try:
                await broadcast_msg.copy(chat_id=user_id)
                success_count += 1
            except FloodWait as e:
                await asyncio.sleep(e.value)
                try:
                    await broadcast_msg.copy(chat_id=user_id)
                    success_count += 1
                except Exception:
                    fail_count += 1
            except Exception:
                fail_count += 1
                
            if (idx + 1) % 20 == 0 or (idx + 1) == total_users:
                try:
                    await status_msg.edit_text(
                        f"🔄 **Broadcasting progress...**\n\n"
                        f"Processed: {idx + 1} / {total_users}\n"
                        f"🟢 Success: {success_count}\n"
                        f"🔴 Failed: {fail_count}"
                    )
                except Exception:
                    pass
                
            await asyncio.sleep(0.05)
            
        await status_msg.edit_text(
            f"✅ **Broadcast Completed!**\n\n"
            f"👥 **Total Target:** {total_users}\n"
            f"🟢 **Successfully Sent:** {success_count}\n"
            f"🔴 **Failed/Blocked:** {fail_count}"
        )
        
    except Exception as e:
        await status_msg.edit_text(f"❌ **Error during broadcast:** `{str(e)}`")


@Client.on_message(filters.command("stats") & filters.private)
@admin_only
async def stats_command(client: Client, message: Message):
    """
    /stats
    Admin command to view overall system statistics.
    """
    mongo = client.mongo
    status_msg = await message.reply("📊 **Calculating system statistics...**")
    
    try:
        # Total Users
        total_users = await mongo.users.count_documents({})
        
        # Total Referrals
        total_referrals = await mongo.users.count_documents({"referred_by": {"$exists": True}})
        
        # Total Registered Accounts (all registrations)
        total_registered = await mongo.db["registrations"].count_documents({})
        
        # Total Approved Accounts (credited transactions)
        total_approved = await mongo.db["transactions"].count_documents({"status": "credited", "registration_id": {"$exists": True}})
        
        # Total Hold Accounts (hold transactions)
        total_hold = await mongo.db["transactions"].count_documents({"status": "hold", "registration_id": {"$exists": True}})
        
        # Total Rejected Accounts (rejected transactions)
        total_rejected = await mongo.db["transactions"].count_documents({"status": "rejected", "registration_id": {"$exists": True}})
        
        # Total Expired Accounts (expired transactions)
        total_expired = await mongo.db["transactions"].count_documents({"status": "expired", "registration_id": {"$exists": True}})
        
        # Total Revenue (sum of credited transactions)
        pipeline_rev = [
            {"$match": {"status": "credited"}},
            {"$group": {"_id": None, "total": {"$sum": "$amount_usd"}}}
        ]
        res_rev = await mongo.db["transactions"].aggregate(pipeline_rev).to_list(length=None)
        total_rev_usd = res_rev[0]["total"] if res_rev else 0.0
        
        # Total Hold USD (sum of hold transactions)
        pipeline_hold = [
            {"$match": {"status": "hold"}},
            {"$group": {"_id": None, "total": {"$sum": "$amount_usd"}}}
        ]
        res_hold = await mongo.db["transactions"].aggregate(pipeline_hold).to_list(length=None)
        total_hold_usd = res_hold[0]["total"] if res_hold else 0.0
        
        # Total User Main Balance (sum of all transactions where status is not hold, rejected, or cancelled)
        pipeline_main = [
            {"$match": {"status": {"$nin": ["hold", "rejected", "cancelled"]}}},
            {"$group": {"_id": None, "total": {"$sum": "$amount_usd"}}}
        ]
        res_main = await mongo.db["transactions"].aggregate(pipeline_main).to_list(length=None)
        total_main_usd = res_main[0]["total"] if res_main else 0.0
        
        # Total Payouts Completed Count and Amount
        total_payouts_count = await mongo.db["transactions"].count_documents({"status": "completed", "type": "payout"})
        pipeline_payout = [
            {"$match": {"status": "completed", "type": "payout"}},
            {"$group": {"_id": None, "total": {"$sum": "$amount_usd"}}}
        ]
        res_payout = await mongo.db["transactions"].aggregate(pipeline_payout).to_list(length=None)
        total_payout_usd = abs(res_payout[0]["total"]) if res_payout else 0.0
        
        # Connected userbots
        connected_userbots = await mongo.get_connected_userbots_count()
        total_userbots = await mongo.get_total_userbots_count()
        
        # Total referral commission paid system-wide
        pipeline_comm_total = [
            {"$match": {"type": "referral_commission", "status": "credited"}},
            {"$group": {"_id": None, "total": {"$sum": "$amount_usd"}}}
        ]
        res_comm_total = await mongo.db["transactions"].aggregate(pipeline_comm_total).to_list(length=None)
        total_comm_usd = res_comm_total[0]["total"] if res_comm_total else 0.0
        
        # Format exchange rate
        exchange_rate = await mongo.get_system_setting("exchange_rate", 100.0)
        
        stats_text = f"""📊 **System Dashboard Statistics**
        
👥 **User Statistics:**
• **Total Users:** `{total_users}`
• **Total Referred Users:** `{total_referrals}`

🤖 **Userbot Sessions:**
• **Connected Userbots:** `{connected_userbots} / {total_userbots}`

📧 **Gmail Account Statistics:**
• **Total Registered (In DB):** `{total_registered}`
• **Approved/Credited:** `{total_approved}`
• **Hold/Pending:** `{total_hold}`
• **Rejected:** `{total_rejected}`
• **Expired:** `{total_expired}`

💰 **Financial Statistics:**
• **Total User Main Balance:** `{total_main_usd:.3f}$` (~`{total_main_usd * exchange_rate:.2f}₹`)
• **Total Current Hold Amount:** `{total_hold_usd:.3f}$` (~`{total_hold_usd * exchange_rate:.2f}₹`)
• **Total Approved Earnings:** `{total_rev_usd:.3f}$` (~`{total_rev_usd * exchange_rate:.2f}₹`)
• **Total Referral Commission Paid:** `{total_comm_usd:.3f}$` (~`{total_comm_usd * exchange_rate:.2f}₹`)
• **Completed Payouts:** `{total_payouts_count} transactions` (`{total_payout_usd:.3f}$` / ~`{total_payout_usd * exchange_rate:.2f}₹`)
"""
        await status_msg.edit_text(stats_text)
    except Exception as e:
        await status_msg.edit_text(f"❌ **Error calculating statistics:** `{str(e)}`")


@Client.on_message(filters.command("user") & filters.private)
@admin_only
async def user_details_command(client: Client, message: Message):
    """
    /user <userid>
    Admin command to view detailed profile and transactions of a user.
    """
    args = message.command
    if len(args) < 2:
        await message.reply("❌ **Usage:** `/user [user_id]`")
        return
        
    try:
        target_user_id = int(args[1])
    except ValueError:
        await message.reply("❌ **Invalid User ID.** Must be an integer.")
        return
        
    mongo = client.mongo
    user = await mongo.get_user(target_user_id)
    if not user:
        await message.reply(f"❌ **User with ID {target_user_id} not found in database.**")
        return
        
    status_msg = await message.reply("🔍 **Fetching user details...**")
    
    try:
        # Fetch balances
        balances = await mongo.update_and_get_balance(target_user_id)
        main_usd = balances.get("main_balance_usd", 0.0)
        hold_usd = balances.get("hold_balance_usd", 0.0)
        
        # Registrations count
        total_registered = await mongo.db["registrations"].count_documents({"user_id": target_user_id})
        
        # Transaction Counts
        approved_count = await mongo.db["transactions"].count_documents({"user_id": target_user_id, "status": "credited", "registration_id": {"$exists": True}})
        hold_count = await mongo.db["transactions"].count_documents({"user_id": target_user_id, "status": "hold", "registration_id": {"$exists": True}})
        rejected_count = await mongo.db["transactions"].count_documents({"user_id": target_user_id, "status": "rejected", "registration_id": {"$exists": True}})
        expired_count = await mongo.db["transactions"].count_documents({"user_id": target_user_id, "status": "expired", "registration_id": {"$exists": True}})
        
        # Referrals count
        ref_count = await mongo.users.count_documents({"referred_by": target_user_id})
        
        # Calculate total referral commission earned by user
        pipeline_comm = [
            {"$match": {"user_id": target_user_id, "type": "referral_commission", "status": "credited"}},
            {"$group": {"_id": None, "total": {"$sum": "$amount_usd"}}}
        ]
        res_comm = await mongo.db["transactions"].aggregate(pipeline_comm).to_list(length=None)
        user_comm_usd = res_comm[0]["total"] if res_comm else 0.0
        
        referred_by_id = user.get("referred_by")
        referred_by_str = "None"
        if referred_by_id:
            referred_by_user = await mongo.get_user(referred_by_id)
            if referred_by_user:
                ref_uname = referred_by_user.get("username", "No Username")
                referred_by_str = f"`{referred_by_id}` (@{ref_uname})"
            else:
                referred_by_str = f"`{referred_by_id}`"
                
        # Exchange formatting
        exchange_rate = await mongo.get_system_setting("exchange_rate", 100.0)
        from handlers.start import format_price_dual
        main_str = format_price_dual(main_usd, 3, exchange_rate)
        hold_str = format_price_dual(hold_usd, 3, exchange_rate)
        user_comm_str = format_price_dual(user_comm_usd, 3, exchange_rate)
        
        username = user.get("username")
        username_str = f"@{username}" if username else "No Username"
        first_name = user.get("first_name", "No First Name")
        last_name = user.get("last_name", "")
        fullname = f"{first_name} {last_name}".strip()
        
        created_at = user.get("created_at")
        created_str = created_at.strftime("%Y-%m-%d %H:%M:%S") if created_at else "Unknown"
        last_active = user.get("last_active")
        active_str = last_active.strftime("%Y-%m-%d %H:%M:%S") if last_active else "Unknown"
        
        profile_text = f"""👤 **User Profile Details**
        
• **User ID:** `{target_user_id}`
• **Name:** `{fullname}`
• **Username:** {username_str}
• **Joined:** `{created_str}` (UTC)
• **Last Active:** `{active_str}` (UTC)

💰 **Financial Details:**
• **Main Balance:** {main_str}
• **Hold Balance:** {hold_str}

📧 **Gmail Account Stats:**
• **Total Registered (Tasks):** `{total_registered}`
• **Approved/Credited:** `{approved_count}`
• **Current Hold:** `{hold_count}`
• **Rejected:** `{rejected_count}`
• **Expired:** `{expired_count}`

👥 **Referrals Info:**
• **Total Referrals:** `{ref_count}`
• **Total Commission Earned:** {user_comm_str}
• **Referred By:** {referred_by_str}
"""
        await status_msg.edit_text(profile_text)
    except Exception as e:
        await status_msg.edit_text(f"❌ **Error fetching details:** `{str(e)}`")


@Client.on_message(filters.command("payout") & filters.private)
@admin_only
async def payout_config_command(client: Client, message: Message):
    """
    /payout - see all commands of payout
    /payout crypto on/off
    /payout crypto fees enable [amount]
    /payout crypto fees disable
    /payout upi on/off
    /payout upi fees enable [amount]
    /payout upi fees disable
    """
    args = message.command
    mongo = client.mongo
    
    help_text = (
        "💸 **Payout Configuration Commands:**\n\n"
        "• `/payout crypto on` - Turn on crypto payment method\n"
        "• `/payout crypto off` - Turn off crypto payment method\n"
        "• `/payout crypto fees enable` - Enable crypto fees\n"
        "• `/payout crypto fees enable [amount]` - Set and enable crypto fees in USD (e.g. `/payout crypto fees enable 0.5`)\n"
        "• `/payout crypto fees disable` - Disable crypto fees\n\n"
        "• `/payout upi on` - Turn on upi payment method\n"
        "• `/payout upi off` - Turn off upi payment method\n"
        "• `/payout upi fees enable` - Enable upi fees\n"
        "• `/payout upi fees enable [amount]` - Set and enable upi fees in INR (e.g. `/payout upi fees enable 10`)\n"
        "• `/payout upi fees disable` - Disable upi fees\n\n"
        "ℹ️ **Current Settings:**\n"
    )
    
    # Retrieve current settings
    crypto_enabled = await mongo.get_system_setting("payout_crypto_enabled", True)
    upi_enabled = await mongo.get_system_setting("payout_upi_enabled", True)
    crypto_fee_enabled = await mongo.get_system_setting("payout_crypto_fee_enabled", False)
    crypto_fee_amount = await mongo.get_system_setting("payout_crypto_fee_amount", 0.0)
    upi_fee_enabled = await mongo.get_system_setting("payout_upi_fee_enabled", True)
    upi_fee_amount = await mongo.get_system_setting("payout_upi_fee_amount", 10.0)
    
    current_settings = (
        f"• **Crypto:** {'🟢 ON' if crypto_enabled else '🔴 OFF'} | "
        f"**Fee:** {crypto_fee_amount}$ ({'🟢 Enabled' if crypto_fee_enabled else '🔴 Disabled'})\n"
        f"• **UPI:** {'🟢 ON' if upi_enabled else '🔴 OFF'} | "
        f"**Fee:** {upi_fee_amount}₹ ({'🟢 Enabled' if upi_fee_enabled else '🔴 Disabled'})"
    )
    
    if len(args) < 2:
        await message.reply(help_text + current_settings)
        return
        
    target = args[1].lower()
    if target not in ["crypto", "upi"]:
        await message.reply("❌ **Invalid target.** Specify `crypto` or `upi`.\n\n" + help_text + current_settings)
        return
        
    if len(args) < 3:
        await message.reply("❌ **Missing action.** Specify `on`, `off`, `fees enable`, or `fees disable`.\n\n" + help_text + current_settings)
        return
        
    action = args[2].lower()
    
    if action == "on":
        setting_key = f"payout_{target}_enabled"
        await mongo.set_system_setting(setting_key, True)
        await message.reply(f"✅ **{target.upper()} payment method has been enabled.**")
        return
        
    elif action == "off":
        setting_key = f"payout_{target}_enabled"
        await mongo.set_system_setting(setting_key, False)
        await message.reply(f"✅ **{target.upper()} payment method has been disabled.**")
        return
        
    elif action == "fees":
        if len(args) < 4:
            await message.reply(f"❌ **Missing fee action.** Specify `enable` or `disable`.\n\n" + help_text + current_settings)
            return
            
        fee_action = args[3].lower()
        if fee_action == "enable":
            amount = None
            if len(args) >= 5:
                try:
                    amount = float(args[4])
                except ValueError:
                    await message.reply("❌ **Invalid amount.** Please enter a valid number.")
                    return
                if amount < 0:
                    await message.reply("❌ **Amount cannot be negative.**")
                    return
            
            # Save fee enable status
            await mongo.set_system_setting(f"payout_{target}_fee_enabled", True)
            if amount is not None:
                await mongo.set_system_setting(f"payout_{target}_fee_amount", amount)
                unit = "$" if target == "crypto" else "₹"
                await message.reply(f"✅ **{target.upper()} fees enabled and set to {amount}{unit}.**")
            else:
                await message.reply(f"✅ **{target.upper()} fees enabled.**")
            return
            
        elif fee_action == "disable":
            await mongo.set_system_setting(f"payout_{target}_fee_enabled", False)
            await message.reply(f"✅ **{target.upper()} fees disabled.**")
            return
            
        else:
            await message.reply(f"❌ **Invalid fee action.** Use `enable` or `disable`.")
            return
            
    else:
        await message.reply("❌ **Invalid action.** Specify `on`, `off`, or `fees`.")
        return


@Client.on_message(filters.command("commission") & filters.private)
@admin_only
async def set_commission_command(client: Client, message: Message):
    """
    /commission [amount_in_usd]
    Sets the referral commission in USD.
    """
    args = message.command
    if len(args) < 2:
        await message.reply("❌ **Usage:** `/commission [amount_in_usd]`")
        return
        
    try:
        amount_usd = float(args[1])
    except ValueError:
        await message.reply("❌ **Invalid argument.** Make sure amount is a number.")
        return
        
    if amount_usd < 0:
        await message.reply("❌ **Commission amount cannot be negative.**")
        return
        
    mongo = client.mongo
    success = await mongo.set_system_setting("referral_commission_usd", amount_usd)
    
    if success:
        await message.reply(
            f"✅ **Referral commission successfully set to {amount_usd:.3f}$ (USD).**"
        )
    else:
        await message.reply("❌ **Failed to update referral commission in database.**")


@Client.on_message(filters.command("setup") & filters.private)
@admin_only
async def setup_command(client: Client, message: Message):
    """
    /setup [guide/recovery/logout] - Reply to a message/video to set the guide/recovery/logout message
    /setup [guide/recovery/logout] enable - Enable the button
    /setup [guide/recovery/logout] disable - Disable the button
    """
    args = message.command
    if len(args) < 2 or args[1].lower() not in ["guide", "recovery", "logout"]:
        await message.reply(
            "⚙️ **Setup Configuration Commands:**\n\n"
            "• `/setup guide` (reply to a message/video) - Set 'How to create account' guide\n"
            "• `/setup guide enable` / `disable` - Toggle 'How to create account' button\n\n"
            "• `/setup recovery` (reply to a message/video) - Set 'How to add recovery email' guide\n"
            "• `/setup recovery enable` / `disable` - Toggle 'How to add recovery email' button\n\n"
            "• `/setup logout` (reply to a message/video) - Set 'How to logout' guide\n"
            "• `/setup logout enable` / `disable` - Toggle 'How to logout' button"
        )
        return
        
    target = args[1].lower()
    mongo = client.mongo
    
    # Helper to get descriptive labels
    labels = {
        "guide": "How to create account",
        "recovery": "How to add recovery email",
        "logout": "How to logout"
    }
    label = labels.get(target, target)
    
    # Check if there is a 3rd argument (enable/disable)
    if len(args) >= 3:
        action = args[2].lower()
        if action == "enable":
            # Check if set
            chat_id = await mongo.get_system_setting(f"{target}_chat_id")
            message_id = await mongo.get_system_setting(f"{target}_message_id")
            if not chat_id or not message_id:
                await message.reply(f"⚠️ **Please set the {target} message first by replying to a message/video with `/setup {target}`.**")
                return
            await mongo.set_system_setting(f"{target}_enabled", True)
            await message.reply(f"✅ **'{label}' button has been enabled.**")
            return
        elif action == "disable":
            await mongo.set_system_setting(f"{target}_enabled", False)
            await message.reply(f"✅ **'{label}' button has been disabled.**")
            return
        else:
            await message.reply("❌ **Invalid action.** Specify `enable` or `disable`.")
            return
            
    # Setting via reply
    if not message.reply_to_message:
        await message.reply(f"❌ **Usage:** Reply to the guide message/video/photo with `/setup {target}` to set it.")
        return
        
    replied_msg = message.reply_to_message
    
    # Save details
    await mongo.set_system_setting(f"{target}_chat_id", message.chat.id)
    await mongo.set_system_setting(f"{target}_message_id", replied_msg.id)
    await mongo.set_system_setting(f"{target}_enabled", True) # Auto-enable on set
    
    await message.reply(f"✅ **{label} message/video has been successfully set and the button has been enabled!**")


@Client.on_message(filters.command("minimumpayout") & filters.private)
@admin_only
async def set_minimum_payout_command(client: Client, message: Message):
    """
    /minimumpayout upi [amount_in_inr]
    /minimumpayout crypto [amount_in_usd]
    """
    args = message.command
    if len(args) < 3 or args[1].lower() not in ["upi", "crypto"]:
        await message.reply(
            "⚙️ **Minimum Payout Configuration:**\n\n"
            "• `/minimumpayout upi [amount]` - Set minimum payout for UPI in INR\n"
            "• `/minimumpayout crypto [amount]` - Set minimum payout for Crypto in USD"
        )
        return
        
    target = args[1].lower()
    try:
        amount = float(args[2])
    except ValueError:
        await message.reply("❌ **Invalid amount.** Please enter a valid number.")
        return
        
    if amount < 0:
        await message.reply("❌ **Amount cannot be negative.**")
        return
        
    mongo = client.mongo
    setting_key = f"payout_{target}_min"
    success = await mongo.set_system_setting(setting_key, amount)
    
    if success:
        unit = "₹ (INR)" if target == "upi" else "$ (USD)"
        await message.reply(f"✅ **Minimum payout for {target.upper()} successfully set to {amount}{unit}.**")
    else:
        await message.reply("❌ **Failed to update minimum payout in database.**")


@Client.on_message(filters.command("check") & filters.private)
@admin_only
async def check_email_command(client: Client, message: Message):
    """
    /check [email] - Check if an email exists in registered accounts database
    """
    args = message.command
    if len(args) < 2:
        await message.reply("❌ **Usage:** `/check [email]`")
        return
        
    email = args[1].lower().strip()
    if "@" not in email:
        email = f"{email}@gmail.com"
        
    mongo = client.mongo
    reg = await mongo.db["registrations"].find_one({"email": email})
    
    if reg:
        tx = await mongo.db["transactions"].find_one({"registration_id": reg["_id"]})
        status_str = "Unknown"
        if tx:
            status_str = tx.get("status", "Unknown").title()
        elif reg.get("status") == "cancelled":
            status_str = "Cancelled"
        else:
            status_str = reg.get("status", "Incomplete").title()
            
        user_id = reg.get("user_id")
        created_at = reg.get("created_at") or reg.get("updated_at")
        created_str = created_at.strftime("%Y-%m-%d %H:%M:%S") if created_at else "Unknown"
        
        reply_text = (
            f"🔍 **Email Registration Found!**\n\n"
            f"📧 **Email:** `{email}`\n"
            f"👤 **User ID:** `{user_id}`\n"
            f"⚡ **Status:** `{status_str}`\n"
            f"📅 **Created At:** `{created_str}` (UTC)\n"
            f"🔑 **Password:** `{reg.get('password', 'N/A')}`\n"
            f"🔄 **Recovery:** `{reg.get('recovery_email', 'N/A')}`"
        )
        await message.reply(reply_text)
    else:
        await message.reply(f"❌ **Email `{email}` was not found in the registration database.**")


@Client.on_message(filters.command("admincommands") & filters.private)
@admin_only
async def admin_commands_list_command(client: Client, message: Message):
    """
    /admincommands - displays all available admin commands
    """
    admin_help = (
        "🛠️ **Admin Commands List:**\n\n"
        "• `/stats` - View overall system statistics\n"
        "• `/user [user_id]` - Check detailed user details and balances\n"
        "• `/check [email]` - Check if an email is registered in the database\n"
        "• `/addbalance [user_id] [usd/inr] [amount]` - Add balance to user's main balance\n"
        "• `/removebalance [user_id] [usd/inr] [amount]` - Remove balance from user's main balance\n"
        "• `/addholdbalance [user_id] [usd/inr] [amount] [hold_days]` - Add hold balance to user\n"
        "• `/removeholdbalance [user_id] [usd/inr] [amount]` - Remove hold balance from user\n"
        "• `/checkholds` - Manually trigger check of pending hold accounts\n"
        "• `/waittime [seconds]` - Set the registration cooldown duration\n"
        "• `/commission [amount_usd]` - Set referral commission reward in USD\n"
        "• `/minimumpayout [upi/crypto] [amount]` - Set minimum payout threshold\n"
        "• `/setup [guide/recovery/logout]` - Setup guide/recovery/logout instructions and toggle buttons\n"
        "• `/broadcast` - Broadcast a message to all users (reply to a message)\n"
        "• `/payout` - View and manage payout payment methods and fees\n"
        "• `/admincommands` - List all admin commands"
    )
    await message.reply(admin_help)
