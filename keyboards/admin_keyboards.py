"""
Admin Keyboards - Keyboard layouts for admin panel
"""

from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton


class AdminKeyboards:
    @staticmethod
    def userbot_menu() -> InlineKeyboardMarkup:
        """Userbot management menu"""
        return InlineKeyboardMarkup([
            [
                InlineKeyboardButton("➕ Add Bot", callback_data="ub_add"),
                InlineKeyboardButton("📋 Bot List", callback_data="ub_list")
            ],
            [
                InlineKeyboardButton("🔍 Check Status", callback_data="ub_check_status")
            ],
            [
                InlineKeyboardButton("🔌 Connect All", callback_data="ub_connect_all"),
                InlineKeyboardButton("⏹️ Disconnect All", callback_data="ub_disconnect_all")
            ],
            [
                InlineKeyboardButton("🔌 Connect One", callback_data="ub_connect_one"),
                InlineKeyboardButton("⏹️ Disconnect One", callback_data="ub_disconnect_one")
            ],
            [
                InlineKeyboardButton("🗑️ Remove Bot", callback_data="ub_remove")
            ],
            [
                InlineKeyboardButton("🧹 Remove Disconnected", callback_data="ub_remove_disconnected")
            ],
            [
                InlineKeyboardButton("💰 Reward Amount", callback_data="ub_reward_amount")
            ],
            [
                InlineKeyboardButton("🔙 Back", callback_data="main_menu")
            ]
        ])
