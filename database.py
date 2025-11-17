#!/opt/tg_multi_bot/venv/bin/python
"""
SQLite 数据库管理模块
替代原来的 JSON 文件存储方案
"""
import sqlite3
import json
import logging
from typing import Optional, List, Dict, Any
from contextlib import contextmanager
from datetime import datetime

logger = logging.getLogger(__name__)

DB_FILE = "tg_bot_data.db"

@contextmanager
def get_db():
    """数据库连接上下文管理器"""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row  # 允许通过列名访问
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error(f"数据库操作失败: {e}")
        raise
    finally:
        conn.close()

def init_database():
    """初始化数据库表结构"""
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Bots 表 - 存储机器人配置
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS bots (
                username TEXT PRIMARY KEY,
                token TEXT NOT NULL,
                owner_id INTEGER NOT NULL,
                welcome_msg TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # 消息映射表 - 存储消息转发关系
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS message_map (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bot_username TEXT NOT NULL,
                original_chat_id INTEGER NOT NULL,
                original_msg_id INTEGER NOT NULL,
                forwarded_chat_id INTEGER NOT NULL,
                forwarded_msg_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(bot_username, original_chat_id, original_msg_id)
            )
        """)
        
        # 黑名单表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS blacklist (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bot_username TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                reason TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(bot_username, user_id)
            )
        """)
        
        # 已验证用户表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS verified_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bot_username TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                user_name TEXT,
                user_username TEXT,
                verified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(bot_username, user_id)
            )
        """)
        
        # 创建索引以提高查询性能
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_msg_map_bot ON message_map(bot_username)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_blacklist_bot ON blacklist(bot_username)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_verified_bot ON verified_users(bot_username)")
        
        logger.info("✅ 数据库初始化完成")

# ==================== Bot 管理 ====================
def get_all_bots() -> Dict[str, Dict[str, Any]]:
    """获取所有机器人配置"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT username, token, owner_id, welcome_msg FROM bots")
        rows = cursor.fetchall()
        
        result = {}
        for row in rows:
            result[row['username']] = {
                'token': row['token'],
                'owner': row['owner_id'],
                'welcome_msg': row['welcome_msg'] or ""
            }
        return result

def get_bot(username: str) -> Optional[Dict[str, Any]]:
    """获取单个机器人配置"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT token, owner_id, welcome_msg FROM bots WHERE username = ?",
            (username,)
        )
        row = cursor.fetchone()
        if row:
            return {
                'token': row['token'],
                'owner': row['owner_id'],
                'welcome_msg': row['welcome_msg'] or ""
            }
        return None

def add_bot(username: str, token: str, owner_id: int, welcome_msg: str = ""):
    """添加机器人"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """INSERT OR REPLACE INTO bots (username, token, owner_id, welcome_msg, updated_at) 
               VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)""",
            (username, token, owner_id, welcome_msg)
        )
        logger.info(f"✅ 添加/更新 Bot: {username}")

def remove_bot(username: str):
    """删除机器人及其相关数据"""
    with get_db() as conn:
        cursor = conn.cursor()
        # 删除 bot 配置
        cursor.execute("DELETE FROM bots WHERE username = ?", (username,))
        # 删除相关消息映射
        cursor.execute("DELETE FROM message_map WHERE bot_username = ?", (username,))
        # 删除相关黑名单
        cursor.execute("DELETE FROM blacklist WHERE bot_username = ?", (username,))
        # 删除相关验证用户
        cursor.execute("DELETE FROM verified_users WHERE bot_username = ?", (username,))
        logger.info(f"✅ 删除 Bot 及其所有数据: {username}")

def update_bot_welcome(username: str, welcome_msg: str):
    """更新欢迎消息"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE bots SET welcome_msg = ?, updated_at = CURRENT_TIMESTAMP WHERE username = ?",
            (welcome_msg, username)
        )

# ==================== 消息映射管理 ====================
def add_message_map(bot_username: str, original_chat_id: int, original_msg_id: int,
                   forwarded_chat_id: int, forwarded_msg_id: int):
    """添加消息映射"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """INSERT OR REPLACE INTO message_map 
               (bot_username, original_chat_id, original_msg_id, forwarded_chat_id, forwarded_msg_id)
               VALUES (?, ?, ?, ?, ?)""",
            (bot_username, original_chat_id, original_msg_id, forwarded_chat_id, forwarded_msg_id)
        )

def get_message_map(bot_username: str, chat_id: int, msg_id: int) -> Optional[Dict[str, int]]:
    """获取消息映射"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """SELECT forwarded_chat_id, forwarded_msg_id 
               FROM message_map 
               WHERE bot_username = ? AND original_chat_id = ? AND original_msg_id = ?""",
            (bot_username, chat_id, msg_id)
        )
        row = cursor.fetchone()
        if row:
            return {
                'chat_id': row['forwarded_chat_id'],
                'msg_id': row['forwarded_msg_id']
            }
        return None

def find_original_message(bot_username: str, forwarded_chat_id: int, 
                         forwarded_msg_id: int) -> Optional[Dict[str, int]]:
    """根据转发消息查找原始消息"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """SELECT original_chat_id, original_msg_id 
               FROM message_map 
               WHERE bot_username = ? AND forwarded_chat_id = ? AND forwarded_msg_id = ?""",
            (bot_username, forwarded_chat_id, forwarded_msg_id)
        )
        row = cursor.fetchone()
        if row:
            return {
                'chat_id': row['original_chat_id'],
                'msg_id': row['original_msg_id']
            }
        return None

# ==================== 黑名单管理 ====================
def is_blacklisted(bot_username: str, user_id: int) -> bool:
    """检查用户是否在黑名单"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT 1 FROM blacklist WHERE bot_username = ? AND user_id = ?",
            (bot_username, user_id)
        )
        return cursor.fetchone() is not None

def add_to_blacklist(bot_username: str, user_id: int, reason: str = ""):
    """添加到黑名单"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR IGNORE INTO blacklist (bot_username, user_id, reason) VALUES (?, ?, ?)",
            (bot_username, user_id, reason)
        )

def remove_from_blacklist(bot_username: str, user_id: int) -> bool:
    """从黑名单移除"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM blacklist WHERE bot_username = ? AND user_id = ?",
            (bot_username, user_id)
        )
        return cursor.rowcount > 0

def get_blacklist(bot_username: str) -> List[int]:
    """获取机器人的黑名单"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT user_id FROM blacklist WHERE bot_username = ?",
            (bot_username,)
        )
        return [row['user_id'] for row in cursor.fetchall()]

# ==================== 验证用户管理 ====================
def is_verified(bot_username: str, user_id: int) -> bool:
    """检查用户是否已验证"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT 1 FROM verified_users WHERE bot_username = ? AND user_id = ?",
            (bot_username, user_id)
        )
        return cursor.fetchone() is not None

def add_verified_user(bot_username: str, user_id: int, user_name: str = "", 
                     user_username: str = ""):
    """添加已验证用户"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """INSERT OR IGNORE INTO verified_users 
               (bot_username, user_id, user_name, user_username) 
               VALUES (?, ?, ?, ?)""",
            (bot_username, user_id, user_name, user_username)
        )

def remove_verified_user(bot_username: str, user_id: int) -> bool:
    """取消用户验证"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM verified_users WHERE bot_username = ? AND user_id = ?",
            (bot_username, user_id)
        )
        return cursor.rowcount > 0

def get_verified_users(bot_username: str) -> List[int]:
    """获取机器人的已验证用户列表"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT user_id FROM verified_users WHERE bot_username = ?",
            (bot_username,)
        )
        return [row['user_id'] for row in cursor.fetchall()]

# ==================== 数据迁移工具 ====================
def migrate_from_json():
    """从 JSON 文件迁移数据到数据库"""
    import os
    
    logger.info("🔄 开始数据迁移...")
    
    # 迁移 bots.json
    if os.path.exists("bots.json"):
        try:
            with open("bots.json", "r", encoding="utf-8") as f:
                bots_data = json.load(f)
            for username, data in bots_data.items():
                add_bot(
                    username=username,
                    token=data['token'],
                    owner_id=data['owner'],
                    welcome_msg=data.get('welcome_msg', '')
                )
            logger.info(f"✅ 迁移 {len(bots_data)} 个 Bot 配置")
        except Exception as e:
            logger.error(f"迁移 bots.json 失败: {e}")
    
    # 迁移 msg_map.json
    if os.path.exists("msg_map.json"):
        try:
            with open("msg_map.json", "r", encoding="utf-8") as f:
                msg_map_data = json.load(f)
            count = 0
            for key, value in msg_map_data.items():
                # key 格式: "bot_username|chat_id|msg_id"
                parts = key.split('|')
                if len(parts) == 3:
                    bot_username, chat_id, msg_id = parts
                    add_message_map(
                        bot_username=bot_username,
                        original_chat_id=int(chat_id),
                        original_msg_id=int(msg_id),
                        forwarded_chat_id=value['chat_id'],
                        forwarded_msg_id=value['msg_id']
                    )
                    count += 1
            logger.info(f"✅ 迁移 {count} 条消息映射")
        except Exception as e:
            logger.error(f"迁移 msg_map.json 失败: {e}")
    
    # 迁移 blacklist.json
    if os.path.exists("blacklist.json"):
        try:
            with open("blacklist.json", "r", encoding="utf-8") as f:
                blacklist_data = json.load(f)
            count = 0
            for bot_username, user_ids in blacklist_data.items():
                for user_id in user_ids:
                    add_to_blacklist(bot_username, user_id)
                    count += 1
            logger.info(f"✅ 迁移 {count} 条黑名单记录")
        except Exception as e:
            logger.error(f"迁移 blacklist.json 失败: {e}")
    
    # 迁移 verified_users.json
    if os.path.exists("verified_users.json"):
        try:
            with open("verified_users.json", "r", encoding="utf-8") as f:
                verified_data = json.load(f)
            count = 0
            for bot_username, user_ids in verified_data.items():
                for user_id in user_ids:
                    add_verified_user(bot_username, user_id)
                    count += 1
            logger.info(f"✅ 迁移 {count} 条验证用户记录")
        except Exception as e:
            logger.error(f"迁移 verified_users.json 失败: {e}")
    
    logger.info("✅ 数据迁移完成")

def backup_to_json():
    """将数据库数据备份为 JSON 格式（用于 GitHub 备份）"""
    backup_data = {}
    
    # 导出 bots
    bots = get_all_bots()
    with open("bots.json", "w", encoding="utf-8") as f:
        json.dump(bots, f, ensure_ascii=False, indent=2)
    
    # 导出 message_map
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM message_map")
        msg_map = {}
        for row in cursor.fetchall():
            key = f"{row['bot_username']}|{row['original_chat_id']}|{row['original_msg_id']}"
            msg_map[key] = {
                'chat_id': row['forwarded_chat_id'],
                'msg_id': row['forwarded_msg_id']
            }
        with open("msg_map.json", "w", encoding="utf-8") as f:
            json.dump(msg_map, f, ensure_ascii=False, indent=2)
    
    # 导出 blacklist
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT bot_username, user_id FROM blacklist")
        blacklist_data = {}
        for row in cursor.fetchall():
            bot = row['bot_username']
            if bot not in blacklist_data:
                blacklist_data[bot] = []
            blacklist_data[bot].append(row['user_id'])
        with open("blacklist.json", "w", encoding="utf-8") as f:
            json.dump(blacklist_data, f, ensure_ascii=False, indent=2)
    
    # 导出 verified_users
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT bot_username, user_id FROM verified_users")
        verified_data = {}
        for row in cursor.fetchall():
            bot = row['bot_username']
            if bot not in verified_data:
                verified_data[bot] = []
            verified_data[bot].append(row['user_id'])
        with open("verified_users.json", "w", encoding="utf-8") as f:
            json.dump(verified_data, f, ensure_ascii=False, indent=2)
    
    logger.info("✅ 数据已导出为 JSON 格式")

if __name__ == "__main__":
    # 测试模块
    logging.basicConfig(level=logging.INFO)
    init_database()
    print("✅ 数据库模块测试通过")
