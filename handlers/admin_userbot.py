"""
Admin Userbot Handler - Userbot management for admins
"""

from pyrogram import Client, filters
from pyrogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import ListenerTimeout, MessageNotModified

from keyboards.admin_keyboards import AdminKeyboards
from utils.decorators import admin_only


@Client.on_message(filters.command("admin") & filters.private)
@admin_only
async def admin_command(client: Client, message: Message):
    """Handle /admin command"""
    mongo = client.mongo
    total = await mongo.get_total_userbots_count()
    connected = await mongo.get_connected_userbots_count()
    
    text = f"""🤖 **Userbot Management**

![📊](tg://emoji?id=6026121742315952530) **Status:**
• Total Userbots: {total}
• Connected: {connected}
• Disconnected: {total - connected}

━━━━━━━━━━━━━━━━━━━━

Select an action:"""

    await message.reply(
        text=text,
        reply_markup=AdminKeyboards.userbot_menu()
    )


@Client.on_callback_query(filters.regex("^userbot_management$"))
async def userbot_management_callback(client: Client, callback: CallbackQuery):
    """Show userbot management menu"""
    mongo = client.mongo
    user_id = callback.from_user.id
    
    if not await mongo.is_admin(user_id):
        await callback.answer("❌ Admin only!", show_alert=True)
        return
    
    total = await mongo.get_total_userbots_count()
    connected = await mongo.get_connected_userbots_count()
    
    text = f"""🤖 **Userbot Management**

![📊](tg://emoji?id=6026121742315952530) **Status:**
• Total Userbots: {total}
• Connected: {connected}
• Disconnected: {total - connected}

━━━━━━━━━━━━━━━━━━━━

Select an action:"""

    await callback.message.edit_text(
        text=text,
        reply_markup=AdminKeyboards.userbot_menu()
    )
    await callback.answer()


@Client.on_callback_query(filters.regex("^ub_add$"))
async def userbot_add_callback(client: Client, callback: CallbackQuery):
    """Add userbot - redirect to login"""
    await callback.message.edit_text(
        "![➕](tg://emoji?id=5807642902066634351) **Add Userbot**\n\n"
        "To add a new Userbot, please use the login process.\n\n"
        "This will send an OTP to the phone number and create a session.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📱 Start Login", callback_data="userbot_login_start")],
            [InlineKeyboardButton("🔙 Back", callback_data="userbot_management")]
        ])
    )
    await callback.answer()


@Client.on_callback_query(filters.regex(r"^ub_list(?:_(\d+))?$"))
async def userbot_list_callback(client: Client, callback: CallbackQuery):
    """List all userbots with pagination"""
    mongo = client.mongo
    
    # Check if page is provided
    page = 0
    if callback.matches[0].lastindex and callback.matches[0].group(1):
        page = int(callback.matches[0].group(1))
    
    sessions = await mongo.get_all_sessions()
    
    if not sessions:
        await callback.answer("No Userbots found!", show_alert=True)
        return
    
    limit = 5
    total_count = len(sessions)
    total_pages = max(1, (total_count + limit - 1) // limit)
    
    start_idx = page * limit
    end_idx = start_idx + limit
    current_sessions = sessions[start_idx:end_idx]
    
    text = f"![📋](tg://emoji?id=6021435576513730578) **Userbot List** (Page {page + 1}/{total_pages})\n\n"
    
    for i, session in enumerate(current_sessions, 1):
        phone = session.get("phone", "Unknown")
        is_connected = session.get("is_connected", False)
        status = "🟢" if is_connected else "🔴"
        reason = session.get("status_reason", "")[:30]
        
        actual_index = start_idx + i
        text += f"{actual_index}. {status} `{phone}`\n"
        if reason:
            text += f"   └ {reason}\n"
    
    text += f"\n![📊](tg://emoji?id=6026121742315952530) Total: {total_count} Userbots"
    
    buttons = []
    nav_row = []
    
    if page > 0:
        nav_row.append(InlineKeyboardButton("⬅️ Previous", callback_data=f"ub_list_{page-1}"))
    
    nav_row.append(InlineKeyboardButton(f"Page {page+1}/{total_pages} ⤵️", callback_data=f"jump_input_ub"))
    
    if end_idx < total_count:
        nav_row.append(InlineKeyboardButton("Next ➡️", callback_data=f"ub_list_{page+1}"))
    
    if nav_row:
        buttons.append(nav_row)
        
    buttons.append([InlineKeyboardButton("🔙 Back", callback_data="userbot_management")])
    
    await callback.message.edit_text(
        text=text,
        reply_markup=InlineKeyboardMarkup(buttons)
    )
    await callback.answer()

@Client.on_callback_query(filters.regex("^jump_input_ub$"))
async def jump_input_ub_callback(client: Client, callback: CallbackQuery):
    """Jump to page for userbot list"""
    await callback.answer()
    
    try:
        response = await client.ask(
            chat_id=callback.from_user.id,
            text="![🔢](tg://emoji?id=6026201306585110323) **Jump to Page (Userbots)**\n\nSend the page number you want to view:\n\nSend /cancel to cancel",
            timeout=30
        )
        
        if response.text == "/cancel":
             await response.reply("Operation cancelled.")
             return
             
        page = int(response.text) - 1
        mongo = client.mongo
        sessions = await mongo.get_all_sessions()
        
        limit = 5
        total_pages = max(1, (len(sessions) + limit - 1) // limit)
        
        if page < 0: page = 0
        if page >= total_pages: page = total_pages - 1
        
        # Show page
        start_idx = page * limit
        end_idx = start_idx + limit
        current_sessions = sessions[start_idx:end_idx]
        
        text = f"![📋](tg://emoji?id=6021435576513730578) **Userbot List** (Page {page + 1}/{total_pages})\n\n"
        
        for i, session in enumerate(current_sessions, 1):
            phone = session.get("phone", "Unknown")
            is_connected = session.get("is_connected", False)
            status = "🟢" if is_connected else "🔴"
            reason = session.get("status_reason", "")[:30]
            
            actual_index = start_idx + i
            text += f"{actual_index}. {status} `{phone}`\n"
            if reason:
                text += f"   └ {reason}\n"
        
        text += f"\n![📊](tg://emoji?id=6026121742315952530) Total: {len(sessions)} Userbots"
        
        buttons = []
        nav_row = []
        
        if page > 0:
            nav_row.append(InlineKeyboardButton("⬅️ Previous", callback_data=f"ub_list_{page-1}"))
        
        nav_row.append(InlineKeyboardButton(f"Page {page+1}/{total_pages} ⤵️", callback_data=f"jump_input_ub"))
        
        if end_idx < len(sessions):
            nav_row.append(InlineKeyboardButton("Next ➡️", callback_data=f"ub_list_{page+1}"))
            
        if nav_row:
            buttons.append(nav_row)
        
        buttons.append([InlineKeyboardButton("🔙 Back", callback_data="userbot_management")])
        
        await response.reply(text, reply_markup=InlineKeyboardMarkup(buttons))
        
    except ValueError:
        await client.send_message(callback.from_user.id, "❌ Invalid number.")
    except Exception as e:
        # logger.error(f"Error in jump to page: {e}") # logger not defined in this file context, skip log
        await client.send_message(callback.from_user.id, "❌ An unexpected error occurred.")


@Client.on_callback_query(filters.regex("^ub_check_status$"))
async def userbot_check_status_callback(client: Client, callback: CallbackQuery):
    """Check status of all userbots"""
    userbot_manager = client.userbot_manager
    
    if not userbot_manager:
        await callback.answer("❌ Userbot manager unavailable!", show_alert=True)
        return
    
    await callback.answer("🔄 Checking connections...", show_alert=False)
    
    result = await userbot_manager.check_all_connections()
    
    text = f"""![📊](tg://emoji?id=6026121742315952530) **Connection Status**

![✅](tg://emoji?id=6026228223145154159) Connected: {result.get('connected', 0)}
![❌](tg://emoji?id=5807651380332076999) Disconnected: {result.get('disconnected', 0)}
![📊](tg://emoji?id=6026121742315952530) Total: {result.get('total', 0)}"""

    try:

        await callback.message.edit_text(
            text=text,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Refresh", callback_data="ub_check_status")],
                [InlineKeyboardButton("🔙 Back", callback_data="userbot_management")]
            ])
        )
    except MessageNotModified:
        pass


@Client.on_callback_query(filters.regex("^ub_connect_all$"))
async def userbot_connect_all_callback(client: Client, callback: CallbackQuery):
    """Connect all userbots"""
    userbot_manager = client.userbot_manager
    
    if not userbot_manager:
        await callback.answer("❌ Userbot manager not available!", show_alert=True)
        return
    
    await callback.answer("🔄 Connecting all Userbots...", show_alert=True)
    
    await userbot_manager.connect_all()
    
    result = await userbot_manager.check_all_connections()
    
    await callback.message.edit_text(
        f"![✅](tg://emoji?id=6026228223145154159) **Connection Complete**\n\n"
        f"• Connected: {result.get('connected', 0)}\n"
        f"• Failed: {result.get('disconnected', 0)}",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 Back", callback_data="userbot_management")
        ]])
    )


@Client.on_callback_query(filters.regex("^ub_disconnect_all$"))
async def userbot_disconnect_all_callback(client: Client, callback: CallbackQuery):
    """Disconnect all userbots"""
    userbot_manager = client.userbot_manager
    
    if not userbot_manager:
        await callback.answer("❌ Userbot manager not available!", show_alert=True)
        return
    
    await callback.answer("🔄 Disconnecting all Userbots...", show_alert=True)
    
    await userbot_manager.disconnect_all()
    
    await callback.message.edit_text(
        "![✅](tg://emoji?id=6026228223145154159) **All Userbots Disconnected!**",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 Back", callback_data="userbot_management")
        ]])
    )


@Client.on_callback_query(filters.regex(r"^ub_connect_one(?:_(\d+))?$"))
async def userbot_connect_one_callback(client: Client, callback: CallbackQuery):
    """Connect single userbot with pagination"""
    mongo = client.mongo
    page = 0
    if callback.matches[0].lastindex and callback.matches[0].group(1):
        page = int(callback.matches[0].group(1))
        
    sessions = await mongo.get_all_sessions()
    disconnected = [s for s in sessions if not s.get("is_connected")]
    
    if not disconnected:
        await callback.answer("All Userbots are connected!", show_alert=True)
        return
    
    limit = 5
    total_count = len(disconnected)
    total_pages = max(1, (total_count + limit - 1) // limit)
    
    start_idx = page * limit
    end_idx = start_idx + limit
    current_list = disconnected[start_idx:end_idx]
    
    buttons = []
    for session in current_list:
        phone = session.get("phone")
        buttons.append([
            InlineKeyboardButton(f"🔌 {phone}", callback_data=f"connect_ub_{phone}")
        ])
    
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("⬅️ Previous", callback_data=f"ub_connect_one_{page-1}"))
    
    nav_row.append(InlineKeyboardButton(f"Page {page+1}/{total_pages} ⤵️", callback_data=f"jump_input_connect_ub"))
    
    if end_idx < total_count:
        nav_row.append(InlineKeyboardButton("Next ➡️", callback_data=f"ub_connect_one_{page+1}"))
    
    if nav_row:
        buttons.append(nav_row)
        
    buttons.append([InlineKeyboardButton("🔙 Back", callback_data="userbot_management")])
    
    await callback.message.edit_text(
        f"![🔌](tg://emoji?id=6024110108483525116) **Connect Userbot** (Page {page + 1}/{total_pages})\n\nSelect a Userbot to connect:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )
    await callback.answer()

@Client.on_callback_query(filters.regex("^jump_input_connect_ub$"))
async def jump_input_connect_ub_callback(client: Client, callback: CallbackQuery):
    """Jump to page for connect userbot"""
    await callback.answer()
    try:
        response = await client.ask(
            chat_id=callback.from_user.id,
            text="![🔢](tg://emoji?id=6026201306585110323) **Jump to Page (Connect Userbot)**\n\nSend the page number:",
            timeout=30
        )
        if response.text == "/cancel":
             await response.reply("Cancelled.")
             return
        page = int(response.text) - 1
        mongo = client.mongo
        sessions = await mongo.get_all_sessions()
        disconnected = [s for s in sessions if not s.get("is_connected")]
        
        limit = 5
        total_pages = max(1, (len(disconnected) + limit - 1) // limit)
        if page < 0: page = 0
        if page >= total_pages: page = total_pages - 1
        
        # Trigger show page
        # We can just call the callback func but we need to mock or edit message. 
        # Easier to reduplicate logic or extract helper. Extracting helper is better but for now replacing inline:
        
        start_idx = page * limit
        end_idx = start_idx + limit
        current_list = disconnected[start_idx:end_idx]
        
        buttons = []
        for session in current_list:
            phone = session.get("phone")
            buttons.append([
                InlineKeyboardButton(f"🔌 {phone}", callback_data=f"connect_ub_{phone}")
            ])
        
        nav_row = []
        if page > 0:
            nav_row.append(InlineKeyboardButton("⬅️ Previous", callback_data=f"ub_connect_one_{page-1}"))
        
        nav_row.append(InlineKeyboardButton(f"Page {page+1}/{total_pages} ⤵️", callback_data=f"jump_input_connect_ub"))
        
        if end_idx < len(disconnected):
            nav_row.append(InlineKeyboardButton("Next ➡️", callback_data=f"ub_connect_one_{page+1}"))
        
        if nav_row:
            buttons.append(nav_row)
            
        buttons.append([InlineKeyboardButton("🔙 Back", callback_data="userbot_management")])
        
        await response.reply(
             f"![🔌](tg://emoji?id=6024110108483525116) **Connect Userbot** (Page {page + 1}/{total_pages})\n\nSelect a Userbot to connect:",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        
    except ValueError:
        await client.send_message(callback.from_user.id, "❌ Invalid number.")
    except Exception:
        await client.send_message(callback.from_user.id, "❌ Error.")


@Client.on_callback_query(filters.regex("^connect_ub_(.+)$"))
async def connect_userbot_callback(client: Client, callback: CallbackQuery):
    """Connect specific userbot"""
    phone = callback.matches[0].group(1)
    userbot_manager = client.userbot_manager
    
    await callback.answer("🔄 Connecting...", show_alert=False)
    
    result = await userbot_manager.connect_single_userbot(phone)
    
    if result.get("success"):
        await callback.message.edit_text(
            f"![✅](tg://emoji?id=6026228223145154159) **Userbot Connected!**\n\nPhone: `{phone}`",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Back", callback_data="userbot_management")
            ]])
        )
    else:
        await callback.message.edit_text(
            f"![❌](tg://emoji?id=5807651380332076999) **Connection Failed!**\n\nPhone: `{phone}`\nError: {result.get('message')}",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Back", callback_data="userbot_management")
            ]])
        )


@Client.on_callback_query(filters.regex(r"^ub_disconnect_one(?:_(\d+))?$"))
async def userbot_disconnect_one_callback(client: Client, callback: CallbackQuery):
    """Disconnect single userbot with pagination"""
    mongo = client.mongo
    page = 0
    if callback.matches[0].lastindex and callback.matches[0].group(1):
        page = int(callback.matches[0].group(1))
        
    sessions = await mongo.get_all_sessions()
    connected = [s for s in sessions if s.get("is_connected")]
    
    if not connected:
        await callback.answer("No connected Userbots found!", show_alert=True)
        return
    
    limit = 5
    total_count = len(connected)
    total_pages = max(1, (total_count + limit - 1) // limit)
    
    start_idx = page * limit
    end_idx = start_idx + limit
    current_list = connected[start_idx:end_idx]
    
    buttons = []
    for session in current_list:
        phone = session.get("phone")
        buttons.append([
            InlineKeyboardButton(f"🔌 {phone}", callback_data=f"disconnect_ub_{phone}")
        ])
    
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("⬅️ Previous", callback_data=f"ub_disconnect_one_{page-1}"))
    
    nav_row.append(InlineKeyboardButton(f"Page {page+1}/{total_pages} ⤵️", callback_data=f"jump_input_disconnect_ub"))
    
    if end_idx < total_count:
        nav_row.append(InlineKeyboardButton("Next ➡️", callback_data=f"ub_disconnect_one_{page+1}"))
    
    if nav_row:
        buttons.append(nav_row)
        
    buttons.append([InlineKeyboardButton("🔙 Back", callback_data="userbot_management")])
    
    await callback.message.edit_text(
        f"![🔌](tg://emoji?id=6024110108483525116) **Disconnect Userbot** (Page {page + 1}/{total_pages})\n\nSelect a Userbot to disconnect:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )
    await callback.answer()

@Client.on_callback_query(filters.regex("^jump_input_disconnect_ub$"))
async def jump_input_disconnect_ub_callback(client: Client, callback: CallbackQuery):
    """Jump page disconnect"""
    await callback.answer()
    try:
        response = await client.ask(callback.from_user.id, "![🔢](tg://emoji?id=6026201306585110323) **Jump to Page**\n\nPage number:", timeout=30)
        if response.text == "/cancel": return
        page = int(response.text) - 1
        
        mongo = client.mongo
        sessions = await mongo.get_all_sessions()
        connected = [s for s in sessions if s.get("is_connected")]
        limit = 5
        total_pages = max(1, (len(connected) + limit - 1) // limit)
        if page < 0: page = 0
        if page >= total_pages: page = total_pages - 1
        
        start_idx = page * limit
        end_idx = start_idx + limit
        current_list = connected[start_idx:end_idx]
        
        buttons = []
        for session in current_list:
            phone = session.get("phone")
            buttons.append([InlineKeyboardButton(f"🔌 {phone}", callback_data=f"disconnect_ub_{phone}")])
            
        nav_row = []
        if page > 0: nav_row.append(InlineKeyboardButton("⬅️ Previous", callback_data=f"ub_disconnect_one_{page-1}"))
        nav_row.append(InlineKeyboardButton(f"Page {page+1}/{total_pages} ⤵️", callback_data=f"jump_input_disconnect_ub"))
        if end_idx < len(connected): nav_row.append(InlineKeyboardButton("Next ➡️", callback_data=f"ub_disconnect_one_{page+1}"))
        
        if nav_row: buttons.append(nav_row)
        buttons.append([InlineKeyboardButton("🔙 Back", callback_data="userbot_management")])
        
        await response.reply(f"![🔌](tg://emoji?id=6024110108483525116) **Disconnect Userbot** (Page {page + 1}/{total_pages})", reply_markup=InlineKeyboardMarkup(buttons))
    except: pass


@Client.on_callback_query(filters.regex("^disconnect_ub_(.+)$"))
async def disconnect_userbot_callback(client: Client, callback: CallbackQuery):
    """Disconnect specific userbot"""
    phone = callback.matches[0].group(1)
    userbot_manager = client.userbot_manager
    
    result = await userbot_manager.disconnect_single_userbot(phone)
    
    if result.get("success"):
        await callback.answer(f"✅ Disconnected {phone}", show_alert=True)
    else:
        await callback.answer(f"❌ Failed: {result.get('message')}", show_alert=True)
    
    # Refresh to management menu
    mongo = client.mongo
    total = await mongo.get_total_userbots_count()
    connected = await mongo.get_connected_userbots_count()
    
    await callback.message.edit_text(
        f"🤖 **Userbot Management**\n\n"
        f"![📊](tg://emoji?id=6026121742315952530) Total: {total} | Connected: {connected}",
        reply_markup=AdminKeyboards.userbot_menu()
    )


@Client.on_callback_query(filters.regex(r"^ub_remove(?:_(\d+))?$"))
async def userbot_remove_callback(client: Client, callback: CallbackQuery):
    """Remove userbot with pagination"""
    mongo = client.mongo
    page = 0
    if callback.matches[0].lastindex and callback.matches[0].group(1):
        page = int(callback.matches[0].group(1))
        
    sessions = await mongo.get_all_sessions()
    
    if not sessions:
        await callback.answer("No Userbots to remove!", show_alert=True)
        return
    
    limit = 5
    total_count = len(sessions)
    total_pages = max(1, (total_count + limit - 1) // limit)
    
    start_idx = page * limit
    end_idx = start_idx + limit
    current_list = sessions[start_idx:end_idx]
    
    buttons = []
    for session in current_list:
        phone = session.get("phone")
        status = "🟢" if session.get("is_connected") else "🔴"
        buttons.append([
            InlineKeyboardButton(f"{status} 🗑️ {phone}", callback_data=f"remove_ub_{phone}")
        ])
    
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("⬅️ Previous", callback_data=f"ub_remove_{page-1}"))
    
    nav_row.append(InlineKeyboardButton(f"Page {page+1}/{total_pages} ⤵️", callback_data=f"jump_input_rem_ub"))
    
    if end_idx < total_count:
        nav_row.append(InlineKeyboardButton("Next ➡️", callback_data=f"ub_remove_{page+1}"))
    
    if nav_row:
        buttons.append(nav_row)
        
    buttons.append([InlineKeyboardButton("🔙 Back", callback_data="userbot_management")])
    
    await callback.message.edit_text(
        f"![🗑️](tg://emoji?id=5807651380332076999) **Remove Userbot** (Page {page + 1}/{total_pages})\n\nSelect a Userbot to remove:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )
    await callback.answer()

@Client.on_callback_query(filters.regex("^jump_input_rem_ub$"))
async def jump_input_rem_ub_callback(client: Client, callback: CallbackQuery):
    """Jump page remove"""
    await callback.answer()
    try:
        response = await client.ask(callback.from_user.id, "![🔢](tg://emoji?id=6026201306585110323) **Jump to Page**\n\nPage number:", timeout=30)
        if response.text == "/cancel": return
        page = int(response.text) - 1
        
        mongo = client.mongo
        sessions = await mongo.get_all_sessions()
        limit = 5
        total_pages = max(1, (len(sessions) + limit - 1) // limit)
        if page < 0: page = 0
        if page >= total_pages: page = total_pages - 1
        
        start_idx = page * limit
        end_idx = start_idx + limit
        current_list = sessions[start_idx:end_idx]
        
        buttons = []
        for session in current_list:
            phone = session.get("phone")
            status = "🟢" if session.get("is_connected") else "🔴"
            buttons.append([InlineKeyboardButton(f"{status} 🗑️ {phone}", callback_data=f"remove_ub_{phone}")])
            
        nav_row = []
        if page > 0: nav_row.append(InlineKeyboardButton("⬅️ Previous", callback_data=f"ub_remove_{page-1}"))
        nav_row.append(InlineKeyboardButton(f"Page {page+1}/{total_pages} ⤵️", callback_data=f"jump_input_rem_ub"))
        if end_idx < len(sessions): nav_row.append(InlineKeyboardButton("Next ➡️", callback_data=f"ub_remove_{page+1}"))
        
        if nav_row: buttons.append(nav_row)
        buttons.append([InlineKeyboardButton("🔙 Back", callback_data="userbot_management")])
        
        await response.reply(f"![🗑️](tg://emoji?id=5807651380332076999) **Remove Userbot** (Page {page + 1}/{total_pages})", reply_markup=InlineKeyboardMarkup(buttons))
    except: pass


@Client.on_callback_query(filters.regex("^remove_ub_(.+)$"))
async def remove_userbot_callback(client: Client, callback: CallbackQuery):
    """Remove specific userbot"""
    phone = callback.matches[0].group(1)
    userbot_manager = client.userbot_manager
    
    if await userbot_manager.remove_userbot(phone):
        await callback.answer(f"✅ Removed {phone}", show_alert=True)
    else:
        await callback.answer("❌ Failed to remove!", show_alert=True)
    
    # Refresh
    mongo = client.mongo
    total = await mongo.get_total_userbots_count()
    connected = await mongo.get_connected_userbots_count()
    
    await callback.message.edit_text(
        f"🤖 **Userbot Management**\n\n"
        f"![📊](tg://emoji?id=6026121742315952530) Total: {total} | Connected: {connected}",
        reply_markup=AdminKeyboards.userbot_menu()
    )


@Client.on_callback_query(filters.regex("^ub_remove_disconnected$"))
async def userbot_remove_disconnected_callback(client: Client, callback: CallbackQuery):
    """Remove all disconnected userbots"""
    userbot_manager = client.userbot_manager
    
    count = await userbot_manager.remove_disconnected_userbots()
    
    await callback.answer(f"✅ Removed {count} disconnected Userbots", show_alert=True)
    
    mongo = client.mongo
    total = await mongo.get_total_userbots_count()
    connected = await mongo.get_connected_userbots_count()
    
    await callback.message.edit_text(
        f"🤖 **Userbot Management**\n\n"
        f"![📊](tg://emoji?id=6026121742315952530) Total: {total} | Connected: {connected}",
        reply_markup=AdminKeyboards.userbot_menu()
    )


@Client.on_callback_query(filters.regex("^ub_reward_amount$"))
async def ub_reward_amount_callback(client: Client, callback: CallbackQuery):
    """View and update constant reward amount and exchange rate"""
    mongo = client.mongo
    user_id = callback.from_user.id
    
    if not await mongo.is_admin(user_id):
        await callback.answer("❌ Admin only!", show_alert=True)
        return
        
    current_reward = await mongo.get_system_setting("reward_amount", 0.0)
    exchange_rate = await mongo.get_system_setting("exchange_rate", 100.0)
    
    inr_val = current_reward * exchange_rate
    text = f"![💰](tg://emoji?id=6030558512252197022) **Reward Amount & Exchange Rate Settings**\n\n" \
           f"• Constant Reward: `${current_reward:.3f}`\n" \
           f"• Exchange Rate: `1 USD = {exchange_rate:.2f} INR`\n" \
           f"• Equivalent INR Reward: `{inr_val:.2f}₹`\n\n" \
           f"Select an option to update settings manually:"
           
    buttons = [
        [InlineKeyboardButton("✏️ Edit Reward Amount", callback_data="ub_set_reward")],
        [InlineKeyboardButton("💱 Edit Exchange Rate", callback_data="ub_set_exchange")],
        [InlineKeyboardButton("🔙 Back", callback_data="userbot_management")]
    ]
    
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
    await callback.answer()


@Client.on_callback_query(filters.regex("^ub_set_reward$"))
async def ub_set_reward_callback(client: Client, callback: CallbackQuery):
    """Interactively set the constant reward amount"""
    mongo = client.mongo
    user_id = callback.from_user.id
    
    if not await mongo.is_admin(user_id):
        await callback.answer("❌ Admin only!", show_alert=True)
        return
        
    await callback.answer()
    
    try:
        response = await client.ask(
            chat_id=user_id,
            text="![💰](tg://emoji?id=6030558512252197022) **Set Reward Amount**\n\nSend the reward amount in USD (e.g. `0.145` or `0.15`):\n\nSend /cancel to cancel",
            timeout=60
        )
        
        if response.text == "/cancel":
            await response.reply("Operation cancelled.")
            return
            
        reward_val = float(response.text)
        if reward_val < 0:
            await response.reply("❌ Reward amount cannot be negative!")
            return
            
        await mongo.set_system_setting("reward_amount", reward_val)
        
        exchange_rate = await mongo.get_system_setting("exchange_rate", 100.0)
        inr_val = reward_val * exchange_rate
        await response.reply(
            f"![✅](tg://emoji?id=6026228223145154159) **Reward Amount updated successfully!**\n\n"
            f"• New Rate: {inr_val:.2f}₹ ~( {reward_val:.3f}$)"
        )
        
    except ValueError:
        await client.send_message(user_id, "❌ Invalid value. Please send a valid decimal number (e.g., `0.145`).")
    except ListenerTimeout:
        await client.send_message(user_id, "❌ Session timed out. Please try again.")
    except Exception as e:
        await client.send_message(user_id, f"❌ Error: {e}")


@Client.on_callback_query(filters.regex("^ub_set_exchange$"))
async def ub_set_exchange_callback(client: Client, callback: CallbackQuery):
    """Interactively set the exchange rate"""
    mongo = client.mongo
    user_id = callback.from_user.id
    
    if not await mongo.is_admin(user_id):
        await callback.answer("❌ Admin only!", show_alert=True)
        return
        
    await callback.answer()
    
    try:
        response = await client.ask(
            chat_id=user_id,
            text="![💰](tg://emoji?id=6030558512252197022) **Set Exchange Rate (USD/INR)**\n\nSend the new exchange rate value (e.g. `100.0` or `83.5`):\n\nSend /cancel to cancel",
            timeout=60
        )
        
        if response.text == "/cancel":
            await response.reply("Operation cancelled.")
            return
            
        rate_val = float(response.text)
        if rate_val <= 0:
            await response.reply("❌ Exchange rate must be greater than zero!")
            return
            
        await mongo.set_system_setting("exchange_rate", rate_val)
        await response.reply(f"![✅](tg://emoji?id=6026228223145154159) **Exchange Rate successfully updated to `1 USD = {rate_val:.2f} INR`!**")
        
    except ValueError:
        await client.send_message(user_id, "❌ Invalid value. Please send a valid decimal number (e.g., `83.5`).")
    except ListenerTimeout:
        await client.send_message(user_id, "❌ Session timed out. Please try again.")
    except Exception as e:
        await client.send_message(user_id, f"❌ Error: {e}")

