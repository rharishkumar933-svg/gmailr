"""
MongoDB Database Connection and Operations (Asynchronous using Motor)
Handles database interactions for userbot management.
"""

import logging
from datetime import datetime
from typing import Optional, List, Dict, Any
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import DuplicateKeyError
from config import MONGO_URI, DATABASE_NAME

logger = logging.getLogger(__name__)


class MongoDB:
    def __init__(self, db_name: str = None):
        """Initialize MongoDB connection (Async using Motor)"""
        self.client = AsyncIOMotorClient(MONGO_URI)
        self.db = self.client[db_name or DATABASE_NAME]
        
        # Collections
        self.users = self.db["users"]
        self.userbots = self.db["userbots"]
        self.admins = self.db["admins"]
        self.system_settings = self.db["system_settings"]
        
        logger.info(f"MongoDB Client initialized for database: {db_name or DATABASE_NAME}")
    
    async def init_db(self):
        """Perform async database setup like index creation"""
        await self._create_indexes()
        logger.info(f"MongoDB connected and initialized successfully")

    async def _create_indexes(self):
        """Create database indexes for better performance"""
        try:
            # Users collection indexes
            await self.users.create_index("user_id", unique=True)
            await self.users.create_index("username")
            
            # Userbots collection indexes
            await self.userbots.create_index("phone", unique=True)
            await self.userbots.create_index("is_connected")
            
            # Admins collection indexes
            await self.admins.create_index("user_id", unique=True)
            
            logger.info("Database indexes created successfully")
        except Exception as e:
            logger.error(f"Error creating indexes: {e}")
    
    # ==================== USER OPERATIONS ====================
    
    async def get_user(self, user_id: int) -> Optional[Dict]:
        """Get user by user_id"""
        return await self.users.find_one({"user_id": user_id})
    
    async def create_user(self, user_id: int, username: str = None, first_name: str = None, referred_by: int = None) -> Dict:
        """Create a new user"""
        user_data = {
            "user_id": user_id,
            "username": username,
            "first_name": first_name,
            "created_at": datetime.utcnow(),
            "last_active": datetime.utcnow()
        }
        if referred_by:
            # Prevent self-referral and check if referrer exists
            if referred_by != user_id:
                referrer_exists = await self.users.find_one({"user_id": referred_by})
                if referrer_exists:
                    user_data["referred_by"] = referred_by
                else:
                    referred_by = None
            else:
                referred_by = None
        
        try:
            await self.users.insert_one(user_data)
            logger.info(f"Created new user: {user_id}")
            return user_data
        except DuplicateKeyError:
            return await self.get_user(user_id)
    
    async def get_or_create_user(self, user_id: int, username: str = None, first_name: str = None, referred_by: int = None) -> tuple:
        """Get existing user or create new one. Returns (user_doc, is_new)"""
        user = await self.get_user(user_id)
        is_new = False
        if not user:
            user = await self.create_user(user_id, username, first_name, referred_by)
            is_new = True
        else:
            # Update last active
            await self.users.update_one(
                {"user_id": user_id},
                {"$set": {"last_active": datetime.utcnow()}}
            )
        return user, is_new
    
    async def get_all_users(self) -> List[Dict]:
        """Get all users"""
        return await self.users.find().to_list(length=None)
    
    async def get_users_count(self) -> int:
        """Get total users count"""
        return await self.users.count_documents({})
    
    # ==================== USERBOT OPERATIONS ====================
    
    async def save_session(self, user_id: int, phone: str, session_string: str) -> bool:
        """Save userbot session"""
        try:
            await self.userbots.update_one(
                {"phone": phone},
                {
                    "$set": {
                        "phone": phone,
                        "session_string": session_string,
                        "added_by": user_id,
                        "is_connected": False,
                        "status_reason": "Newly added",
                        "created_at": datetime.utcnow(),
                        "updated_at": datetime.utcnow()
                    }
                },
                upsert=True
            )
            return True
        except Exception as e:
            logger.error(f"Error saving session: {e}")
            return False
    
    async def get_session(self, phone: str) -> Optional[Dict]:
        """Get userbot session by phone"""
        return await self.userbots.find_one({"phone": phone})
    
    async def get_all_sessions(self) -> List[Dict]:
        """Get all userbot sessions"""
        return await self.userbots.find().to_list(length=None)
    
    async def is_phone_number_exists(self, user_id: int, phone: str) -> bool:
        """Check if phone number already exists"""
        return await self.userbots.find_one({"phone": phone}) is not None
    
    async def update_userbot_status(self, phone: str, is_connected: bool, reason: str = None) -> bool:
        """Update userbot connection status"""
        update_data = {
            "is_connected": is_connected,
            "updated_at": datetime.utcnow()
        }
        if reason:
            update_data["status_reason"] = reason
        
        result = await self.userbots.update_one(
            {"phone": phone},
            {"$set": update_data}
        )
        return result.modified_count > 0
    
    async def remove_userbot(self, phone: str) -> bool:
        """Remove userbot by phone"""
        result = await self.userbots.delete_one({"phone": phone})
        return result.deleted_count > 0
    
    async def remove_disconnected_userbots(self) -> tuple:
        """Remove all disconnected userbots"""
        disconnected = await self.userbots.find({"is_connected": False}).to_list(length=None)
        phone_numbers = [ub["phone"] for ub in disconnected]
        
        result = await self.userbots.delete_many({"is_connected": False})
        return phone_numbers, result.deleted_count
    
    async def get_connected_userbots_count(self) -> int:
        """Get count of connected userbots"""
        return await self.userbots.count_documents({"is_connected": True})
    
    async def get_total_userbots_count(self) -> int:
        """Get total userbots count"""
        return await self.userbots.count_documents({})
    
    # ==================== ADMIN OPERATIONS ====================
    
    async def add_admin(self, user_id: int, added_by: int) -> bool:
        """Add a new admin"""
        try:
            await self.admins.insert_one({
                "user_id": user_id,
                "added_by": added_by,
                "created_at": datetime.utcnow()
            })
            return True
        except DuplicateKeyError:
            return False
    
    async def remove_admin(self, user_id: int) -> bool:
        """Remove an admin"""
        result = await self.admins.delete_one({"user_id": user_id})
        return result.deleted_count > 0
    
    async def is_admin(self, user_id: int) -> bool:
        """Check if user is admin"""
        from config import OWNER_ID
        if user_id == OWNER_ID:
            return True
        return await self.admins.find_one({"user_id": user_id}) is not None
    
    async def get_all_admins(self) -> List[Dict]:
        """Get all admins"""
        return await self.admins.find().to_list(length=None)
    
    # ==================== SYSTEM SETTINGS OPERATIONS ====================

    async def get_system_setting(self, key: str, default: Any = None) -> Any:
        """Get a system-wide setting"""
        setting = await self.system_settings.find_one({"key": key})
        return setting["value"] if setting else default

    async def set_system_setting(self, key: str, value: Any) -> bool:
        """Set a system-wide setting"""
        result = await self.system_settings.update_one(
            {"key": key},
            {"$set": {"value": value, "updated_at": datetime.utcnow()}},
            upsert=True
        )
        return result.modified_count > 0 or result.upserted_id is not None

    # ==================== REGISTRATION OPERATIONS ====================

    async def save_registration(self, user_id: int, phone: str, msg_id: int, details: dict, bot_msg_id: int = None) -> Optional[str]:
        """Save a Gmail registration record and return its ID"""
        try:
            update_data = {
                "user_id": user_id,
                "phone": phone,
                "msg_id": msg_id,
                "first_name": details.get("first_name", ""),
                "last_name": details.get("last_name", ""),
                "email": details.get("email", ""),
                "password": details.get("password", ""),
                "recovery_email": details.get("recovery_email", ""),
                "updated_at": datetime.utcnow()
            }
            if bot_msg_id is not None:
                update_data["bot_msg_id"] = bot_msg_id
                
            await self.db["registrations"].update_one(
                {"phone": phone, "msg_id": msg_id},
                {
                    "$set": update_data,
                    "$setOnInsert": {"status": "active", "created_at": datetime.utcnow()}
                },
                upsert=True
            )
            doc = await self.db["registrations"].find_one({"phone": phone, "msg_id": msg_id})
            return str(doc["_id"]) if doc else None
        except Exception as e:
            logger.error(f"Error saving registration: {e}")
            return None

    async def update_registration_status(self, phone: str, msg_id: int, status: str) -> bool:
        """Update registration status by phone and msg_id"""
        try:
            result = await self.db["registrations"].update_one(
                {"phone": phone, "msg_id": msg_id},
                {"$set": {"status": status, "updated_at": datetime.utcnow()}}
            )
            return result.modified_count > 0
        except Exception as e:
            logger.error(f"Error updating registration status: {e}")
            return False

    async def get_latest_registration(self, user_id: int) -> Optional[Dict]:
        """Get the latest registration record for a user"""
        try:
            return await self.db["registrations"].find_one(
                {"user_id": user_id},
                sort=[("created_at", -1)]
            )
        except Exception as e:
            logger.error(f"Error getting latest registration: {e}")
            return None

    # ==================== TRANSACTION OPERATIONS ====================

    async def add_transaction(self, user_id: int, email: str, phone: str, amount_usd: float, hold_days: int, registration_id: Any) -> bool:
        """Create a new transaction in hold status"""
        try:
            from datetime import timedelta
            tx_data = {
                "user_id": user_id,
                "email": email,
                "phone": phone,
                "amount_usd": amount_usd,
                "status": "hold",
                "hold_until": datetime.utcnow() + timedelta(days=hold_days),
                "created_at": datetime.utcnow(),
                "credited_at": None,
                "registration_id": registration_id
            }
            await self.db["transactions"].insert_one(tx_data)
            return True
        except Exception as e:
            logger.error(f"Error adding transaction: {e}")
            return False

    async def add_balance_transaction(self, user_id: int, amount_usd: float, status: str, type: str, details: dict = None, hold_until: datetime = None) -> Optional[str]:
        """Insert a generic balance transaction (for payouts, refunds, admin adjustments, etc.)"""
        try:
            tx_data = {
                "user_id": user_id,
                "amount_usd": amount_usd,
                "status": status,
                "type": type,
                "created_at": datetime.utcnow(),
                "details": details or {}
            }
            if hold_until:
                tx_data["hold_until"] = hold_until
            res = await self.db["transactions"].insert_one(tx_data)
            return str(res.inserted_id) if res else None
        except Exception as e:
            logger.error(f"Error adding generic transaction: {e}")
            return None

    async def update_and_get_balance(self, user_id: int) -> Dict[str, float]:
        """Update and calculate current balances"""
        try:
            now = datetime.utcnow()
            # Calculate total main balance (any status that is not 'hold', 'rejected', or 'cancelled')
            pipeline_credited = [
                {"$match": {"user_id": user_id, "status": {"$nin": ["hold", "rejected", "cancelled"]}}},
                {"$group": {"_id": None, "total": {"$sum": "$amount_usd"}}}
            ]
            res_credited = await self.db["transactions"].aggregate(pipeline_credited).to_list(length=None)
            main_balance_usd = res_credited[0]["total"] if res_credited else 0.0

            # Calculate total hold balance (hold)
            pipeline_hold = [
                {"$match": {"user_id": user_id, "status": "hold"}},
                {"$group": {"_id": None, "total": {"$sum": "$amount_usd"}}}
            ]
            res_hold = await self.db["transactions"].aggregate(pipeline_hold).to_list(length=None)
            hold_balance_usd = res_hold[0]["total"] if res_hold else 0.0

            return {
                "main_balance_usd": main_balance_usd,
                "hold_balance_usd": hold_balance_usd
            }
        except Exception as e:
            logger.error(f"Error updating and getting balance for {user_id}: {e}")
            return {"main_balance_usd": 0.0, "hold_balance_usd": 0.0}

    async def get_transactions_page(self, user_id: int, page: int, per_page: int = 5) -> tuple:
        """Get a paginated list of transactions sorted by creation date descending"""
        try:
            total_count = await self.db["transactions"].count_documents({"user_id": user_id})
            skip_count = (page - 1) * per_page
            transactions = await self.db["transactions"] \
                .find({"user_id": user_id}) \
                .sort("created_at", -1) \
                .skip(skip_count) \
                .limit(per_page) \
                .to_list(length=None)
            return transactions, total_count
        except Exception as e:
            logger.error(f"Error fetching paginated transactions for {user_id}: {e}")
            return [], 0

    async def get_transaction(self, tx_id: str) -> Optional[Dict]:
        """Get a single transaction by ID"""
        try:
            from bson import ObjectId
            return await self.db["transactions"].find_one({"_id": ObjectId(tx_id)})
        except Exception as e:
            logger.error(f"Error fetching transaction {tx_id}: {e}")
            return None

    async def update_transaction_status(self, tx_id: str, status: str, details: dict = None) -> bool:
        """Update the status and details of a transaction"""
        try:
            from bson import ObjectId
            
            # Find the transaction first to check status and check if referred
            tx = await self.db["transactions"].find_one({"_id": ObjectId(tx_id)})
            if tx and tx.get("status") != "credited" and status == "credited":
                # Check if this transaction represents a Gmail registration
                if "registration_id" in tx:
                    user_id = tx.get("user_id")
                    user = await self.get_user(user_id)
                    if user and user.get("referred_by"):
                        referred_by = user["referred_by"]
                        commission_usd = await self.get_system_setting("referral_commission_usd", 0.4)
                        if commission_usd > 0:
                            await self.add_balance_transaction(
                                user_id=referred_by,
                                amount_usd=commission_usd,
                                status="credited",
                                type="referral_commission",
                                details={
                                    "reason": "Someone created",
                                    "referred_user_id": user_id
                                }
                            )
            
            update_fields = {"status": status, "updated_at": datetime.utcnow()}
            if details:
                for k, v in details.items():
                    update_fields[f"details.{k}"] = v
            result = await self.db["transactions"].update_one(
                {"_id": ObjectId(tx_id)},
                {"$set": update_fields}
            )
            return result.modified_count > 0
        except Exception as e:
            logger.error(f"Error updating transaction status {tx_id}: {e}")
            return False

    async def get_my_accounts_page(self, user_id: int, page: int, per_page: int = 5) -> tuple:
        """Get paginated active registrations: keep hold/credited permanently, expire incomplete ones after 10 hours"""
        try:
            from datetime import timedelta
            cutoff = datetime.utcnow() - timedelta(hours=10)
            
            pipeline = [
                {"$match": {
                    "user_id": user_id,
                    "email": {"$ne": ""},
                    "status": {"$ne": "cancelled"}
                }},
                {"$lookup": {
                    "from": "transactions",
                    "localField": "_id",
                    "foreignField": "registration_id",
                    "as": "tx"
                }},
                {"$match": {
                    "$or": [
                        {"created_at": {"$gt": cutoff}},
                        {"updated_at": {"$gt": cutoff}},
                        {"tx": {"$ne": []}}
                    ]
                }},
                {"$sort": {"updated_at": -1}}
            ]
            
            # Get total count
            count_pipeline = pipeline + [{"$count": "total"}]
            count_res = await self.db["registrations"].aggregate(count_pipeline).to_list(length=None)
            total_count = count_res[0]["total"] if count_res else 0
            
            # Get paginated registrations
            main_pipeline = pipeline + [
                {"$skip": (page - 1) * per_page},
                {"$limit": per_page}
            ]
            registrations = await self.db["registrations"].aggregate(main_pipeline).to_list(length=None)
            
            results = []
            for reg in registrations:
                tx_list = reg.get("tx", [])
                tx = tx_list[0] if tx_list else None
                status_str = "⚫️ Registration is not over"
                if tx:
                    tx_status = tx.get("status")
                    if tx_status == "hold":
                        hold_until = tx.get("hold_until")
                        if hold_until:
                            hold_until_ist = hold_until + timedelta(hours=5, minutes=30)
                            hold_until_str = hold_until_ist.strftime("%b %d %I:%M %p")
                        else:
                            hold_until_str = "Unknown"
                        status_str = f"🟠 In the hold until {hold_until_str}"
                    elif tx_status == "rejected":
                        status_str = "🔴 Rejected"
                    elif tx_status == "expired":
                        status_str = "⚫️ Expired"
                    elif tx_status == "credited":
                        status_str = "🟢 Credited"
                    else:
                        status_str = f"⚪️ {tx_status.title()}"
                
                reg_time = reg.get("created_at") or reg["updated_at"]
                created_ist = reg_time + timedelta(hours=5, minutes=30)
                created_str = created_ist.strftime("%b %d %I:%M %p")
                email = reg.get("email", "")
                if email and "@" not in email:
                    email = f"{email}@gmail.com"
                results.append({
                    "email": email,
                    "status": status_str,
                    "created_at": created_str
                })
                
            return results, total_count
        except Exception as e:
            logger.error(f"Error fetching active accounts for user {user_id}: {e}")
            return [], 0
