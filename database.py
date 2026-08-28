#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
数据库模块 - SQLite 持久化存储
支持：Bot配置、用户验证、消息映射
"""
import sqlite3
import json
import logging
import os
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from threading import Lock
logger = logging.getLogger(__name__)

# 数据库文件路径（使用绝对路径，确保不同运行方式下都访问同一文件）
# 优先使用环境变量，否则使用脚本所在目录
DB_DIR = os.environ.get('TG_BOT_DATA_DIR', os.path.dirname(os.path.abspath(__file__)))
DB_FILE = os.path.join(DB_DIR, 'bot_data.db')

# 线程锁，防止并发写入冲突
db_lock = Lock()
def get_connection():
    """获取数据库连接"""
    conn = sqlite3.connect(DB_FILE, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row  # 支持字典访问
    conn.execute('PRAGMA busy_timeout = 30000')
    conn.execute('PRAGMA journal_mode = WAL')
    conn.execute('PRAGMA synchronous = NORMAL')
    return conn
def init_database():
    """初始化数据库表结构"""
    with db_lock:
        # 打印数据库文件路径（用于诊断）
        logger.info(f"📂 数据库文件路径: {DB_FILE}")
        logger.info(f"📂 数据库文件是否存在: {os.path.exists(DB_FILE)}")
        
        conn = get_connection()
        cursor = conn.cursor()
        
        # 1. Bot配置表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS bots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bot_username TEXT UNIQUE NOT NULL,
                token TEXT NOT NULL,
                owner INTEGER NOT NULL,
                welcome_msg TEXT DEFAULT '',
                mode TEXT DEFAULT 'direct',
                forum_group_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # 1.1 添加新字段（兼容旧数据库）
        try:
            cursor.execute('ALTER TABLE bots ADD COLUMN mode TEXT DEFAULT "direct"')
        except sqlite3.OperationalError:
            pass  # 字段已存在
        
        try:
            cursor.execute('ALTER TABLE bots ADD COLUMN forum_group_id INTEGER')
        except sqlite3.OperationalError:
            pass  # 字段已存在
        
        try:
            cursor.execute('ALTER TABLE bots ADD COLUMN verification_type TEXT DEFAULT "simple"')
        except sqlite3.OperationalError:
            pass  # 字段已存在
        
        try:
            cursor.execute('ALTER TABLE bots ADD COLUMN custom_captcha_question TEXT')
            cursor.execute('ALTER TABLE bots ADD COLUMN custom_captcha_answer TEXT')
        except sqlite3.OperationalError:
            pass  # 字段已存在
        
        try:
            cursor.execute('ALTER TABLE bots ADD COLUMN custom_captcha_hint TEXT')
        except sqlite3.OperationalError:
            pass  # 字段已存在

        # 1.2 健康状态字段（用于检测失效/被转移到其他平台的 Bot）
        for _sql in (
            'ALTER TABLE bots ADD COLUMN health_status TEXT',
            'ALTER TABLE bots ADD COLUMN health_detail TEXT',
            'ALTER TABLE bots ADD COLUMN last_check_at TIMESTAMP',
            'ALTER TABLE bots ADD COLUMN webhook_url TEXT',
            'ALTER TABLE bots ADD COLUMN conflict_count INTEGER DEFAULT 0',
            'ALTER TABLE bots ADD COLUMN last_conflict_at TIMESTAMP',
        ):
            try:
                cursor.execute(_sql)
            except sqlite3.OperationalError:
                pass  # 字段已存在

        # 2. 已验证用户表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS verified_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bot_username TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                user_name TEXT DEFAULT '',
                user_username TEXT DEFAULT '',
                verified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(bot_username, user_id)
            )
        ''')
        
        # 3. 消息映射表（重新设计，支持完整映射）
        # 先检查表是否存在以及结构
        cursor.execute('''
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='message_mappings'
        ''')
        table_exists = cursor.fetchone() is not None
        
        if table_exists:
            # 检查是否有 map_type 列
            cursor.execute('PRAGMA table_info(message_mappings)')
            columns = [row[1] for row in cursor.fetchall()]
            
            if 'map_type' not in columns:
                # 旧表结构，需要迁移
                logger.info("🔄 检测到旧的 message_mappings 表，正在迁移...")
                
                # 备份旧数据
                cursor.execute('ALTER TABLE message_mappings RENAME TO message_mappings_old')
                
                # 创建新表
                cursor.execute('''
                    CREATE TABLE message_mappings (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        bot_username TEXT NOT NULL,
                        map_type TEXT NOT NULL CHECK(map_type IN ('direct', 'topic', 'user_forward', 'forward_user', 'owner_user')),
                        key TEXT NOT NULL,
                        value TEXT NOT NULL,
                        user_id INTEGER,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                
                # 尝试迁移旧数据（如果有的话）
                try:
                    cursor.execute('''
                        INSERT INTO message_mappings (bot_username, map_type, key, value, user_id, created_at)
                        SELECT bot_username, 'direct', key, value, user_id, created_at
                        FROM message_mappings_old
                    ''')
                    logger.info("✅ 旧数据已迁移到新表")
                except Exception as e:
                    logger.warning(f"⚠️ 迁移旧数据失败（可能旧表为空）: {e}")
                
                # 删除旧表
                cursor.execute('DROP TABLE IF EXISTS message_mappings_old')
                logger.info("✅ message_mappings 表结构升级完成")
        else:
            # 表不存在，直接创建新表
            cursor.execute('''
                CREATE TABLE message_mappings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    bot_username TEXT NOT NULL,
                    map_type TEXT NOT NULL CHECK(map_type IN ('direct', 'topic', 'user_forward', 'forward_user', 'owner_user')),
                    key TEXT NOT NULL,
                    value TEXT NOT NULL,
                    user_id INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
        
        # 4. 黑名单表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS blacklist (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bot_username TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                reason TEXT DEFAULT '',
                blocked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(bot_username, user_id)
            )
        ''')
        
        # 5. 全局设置表（管理员设置）
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS global_settings (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # 6. 验证令牌表（CF验证）
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS verification_tokens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                token TEXT UNIQUE NOT NULL,
                bot_username TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                user_name TEXT,
                user_username TEXT,
                message_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP NOT NULL
            )
        ''')
        
        # 添加 message_id 列（兼容旧数据库）
        try:
            cursor.execute('ALTER TABLE verification_tokens ADD COLUMN message_id INTEGER')
            logger.info("✅ verification_tokens 表添加 message_id 列")
        except Exception:
            pass  # 列已存在

        
        # 6. 创建索引加速查询（独立语句）
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_verified_users_bot 
            ON verified_users(bot_username, user_id)
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_message_mappings_lookup 
            ON message_mappings(bot_username, map_type, key)
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_message_mappings_cleanup 
            ON message_mappings(created_at)
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_blacklist_bot 
            ON blacklist(bot_username, user_id)
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_verification_tokens_token 
            ON verification_tokens(token)
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_verification_tokens_cleanup 
            ON verification_tokens(expires_at)
        ''')

        
        conn.commit()
        conn.close()
        logger.info(f"✅ 数据库初始化完成: {DB_FILE}")
# ================== Bot 配置管理 ==================
def add_bot(bot_username: str, token: str, owner: int, welcome_msg: str = '') -> bool:
    """添加新机器人"""
    try:
        with db_lock:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO bots (bot_username, token, owner, welcome_msg)
                VALUES (?, ?, ?, ?)
            ''', (bot_username, token, owner, welcome_msg))
            conn.commit()
            conn.close()
            logger.info(f"✅ 数据库操作成功 - 添加 Bot: {bot_username} (Owner: {owner})")
            logger.info(f"📂 数据已写入: {DB_FILE}")
            return True
    except sqlite3.IntegrityError:
        logger.warning(f"⚠️ Bot 已存在: {bot_username}")
        return False
    except Exception as e:
        logger.error(f"❌ 添加 Bot 失败: {e}")
        import traceback
        traceback.print_exc()
        return False
def get_bot(bot_username: str) -> Optional[Dict]:
    """获取单个机器人信息"""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM bots WHERE bot_username = ?', (bot_username,))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            # 安全地获取 verification_type 字段（兼容旧数据库）
            try:
                verification_type = row['verification_type'] if row['verification_type'] else 'simple'
            except (KeyError, IndexError):
                verification_type = 'simple'
            
            return {
                'bot_username': row['bot_username'],
                'token': row['token'],
                'owner': row['owner'],
                'welcome_msg': row['welcome_msg'] or '',
                'mode': row.get('mode') if hasattr(row, 'get') else (row['mode'] if 'mode' in row.keys() else 'direct'),
                'forum_group_id': row.get('forum_group_id') if hasattr(row, 'get') else (row['forum_group_id'] if 'forum_group_id' in row.keys() else None),
                'verification_type': verification_type,
                'custom_captcha_question': row.get('custom_captcha_question') if hasattr(row, 'get') else (row['custom_captcha_question'] if 'custom_captcha_question' in row.keys() else None),
                'custom_captcha_answer': row.get('custom_captcha_answer') if hasattr(row, 'get') else (row['custom_captcha_answer'] if 'custom_captcha_answer' in row.keys() else None),
                'custom_captcha_hint': row.get('custom_captcha_hint') if hasattr(row, 'get') else (row['custom_captcha_hint'] if 'custom_captcha_hint' in row.keys() else None),
                'created_at': row['created_at']
            }

        return None
    except Exception as e:
        logger.error(f"❌ 查询 Bot 失败: {e}")
        return None
def get_all_bots() -> Dict[str, Dict]:
    """获取所有机器人（返回字典格式）"""
    try:
        logger.info(f"📖 正在从数据库读取 Bot 数据: {DB_FILE}")
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM bots ORDER BY created_at')
        rows = cursor.fetchall()
        conn.close()
        
        bots = {}
        for row in rows:
            # 安全地获取 verification_type 字段（兼容旧数据库）
            try:
                verification_type = row['verification_type'] if row['verification_type'] else 'simple'
            except (KeyError, IndexError):
                verification_type = 'simple'
            
            bots[row['bot_username']] = {
                'token': row['token'],
                'owner': row['owner'],
                'welcome_msg': row['welcome_msg'] or '',
                'mode': row['mode'] if row['mode'] else 'direct',
                'forum_group_id': row['forum_group_id'],
                'verification_type': verification_type,
                'custom_captcha_question': row.get('custom_captcha_question') if hasattr(row, 'get') else (row['custom_captcha_question'] if 'custom_captcha_question' in row.keys() else None),
                'custom_captcha_answer': row.get('custom_captcha_answer') if hasattr(row, 'get') else (row['custom_captcha_answer'] if 'custom_captcha_answer' in row.keys() else None),
                'custom_captcha_hint': row.get('custom_captcha_hint') if hasattr(row, 'get') else (row['custom_captcha_hint'] if 'custom_captcha_hint' in row.keys() else None)
            }

        
        logger.info(f"📊 从数据库读取了 {len(bots)} 个 Bot")
        return bots
    except Exception as e:
        logger.error(f"❌ 查询所有 Bot 失败: {e}")
        import traceback
        traceback.print_exc()
        return {}
def update_bot_welcome(bot_username: str, welcome_msg: str) -> bool:
    """更新欢迎消息"""
    try:
        with db_lock:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE bots 
                SET welcome_msg = ?, updated_at = CURRENT_TIMESTAMP
                WHERE bot_username = ?
            ''', (welcome_msg, bot_username))
            conn.commit()
            affected = cursor.rowcount
            conn.close()
            
            if affected > 0:
                logger.info(f"✅ 更新欢迎消息: {bot_username}")
                return True
            return False
    except Exception as e:
        logger.error(f"❌ 更新欢迎消息失败: {e}")
        return False


def update_bot_mode(bot_username: str, mode: str) -> bool:
    """更新机器人模式（direct/forum）"""
    try:
        with db_lock:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE bots 
                SET mode = ?, updated_at = CURRENT_TIMESTAMP
                WHERE bot_username = ?
            ''', (mode, bot_username))
            conn.commit()
            affected = cursor.rowcount
            conn.close()
            
            if affected > 0:
                logger.info(f"✅ 更新模式: {bot_username} -> {mode}")
                return True
            return False
    except Exception as e:
        logger.error(f"❌ 更新模式失败: {e}")
        return False


def update_bot_forum_id(bot_username: str, forum_group_id: int) -> bool:
    """更新话题群ID"""
    try:
        with db_lock:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE bots 
                SET forum_group_id = ?, updated_at = CURRENT_TIMESTAMP
                WHERE bot_username = ?
            ''', (forum_group_id, bot_username))
            conn.commit()
            affected = cursor.rowcount
            conn.close()
            
            if affected > 0:
                logger.info(f"✅ 更新话题群ID: {bot_username} -> {forum_group_id}")
                return True
            return False
    except Exception as e:
        logger.error(f"❌ 更新话题群ID失败: {e}")
        return False

def update_bot_verification_type(bot_username: str, verification_type: str) -> bool:
    """更新机器人验证类型（simple/cf）"""
    try:
        with db_lock:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE bots 
                SET verification_type = ?, updated_at = CURRENT_TIMESTAMP
                WHERE bot_username = ?
            ''', (verification_type, bot_username))
            conn.commit()
            affected = cursor.rowcount
            conn.close()
            
            if affected > 0:
                logger.info(f"✅ 更新验证类型: {bot_username} -> {verification_type}")
                return True
            return False
    except Exception as e:
        logger.error(f"❌ 更新验证类型失败: {e}")
        return False

def update_bot_custom_captcha(bot_username: str, question: str = None, answer: str = None, hint: str = None) -> bool:
    """更新自定义验证问题"""
    try:
        with db_lock:
            conn = get_connection()
            cursor = conn.cursor()
            
            # 先确保 hint 字段存在
            try:
                cursor.execute('ALTER TABLE bots ADD COLUMN custom_captcha_hint TEXT')
            except sqlite3.OperationalError:
                pass  # 字段已存在
            
            cursor.execute('''
                UPDATE bots 
                SET custom_captcha_question = ?, 
                    custom_captcha_answer = ?, 
                    custom_captcha_hint = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE bot_username = ?
            ''', (question, answer, hint, bot_username))
            conn.commit()
            affected = cursor.rowcount
            conn.close()
            
            if affected > 0:
                logger.info(f"✅ 更新自定义验证: {bot_username} (hint: {'有' if hint else '无'})")
                return True
            return False
    except Exception as e:
        logger.error(f"❌ 更新自定义验证失败: {e}")
        return False

def delete_bot(bot_username: str) -> bool:
    """删除机器人及其关联数据"""

    try:
        with db_lock:
            conn = get_connection()
            cursor = conn.cursor()

            # 删除关联的已验证用户
            cursor.execute('DELETE FROM verified_users WHERE bot_username = ?', (bot_username,))

            # 删除关联的消息映射
            cursor.execute('DELETE FROM message_mappings WHERE bot_username = ?', (bot_username,))

            # 删除关联的黑名单 / 待验证 / 验证链接（避免残留脏数据）
            for _table in ('blacklist', 'pending_verifications', 'verification_tokens'):
                try:
                    cursor.execute(f'DELETE FROM {_table} WHERE bot_username = ?', (bot_username,))
                except sqlite3.OperationalError:
                    pass  # 表不存在（旧库）

            # 删除 Bot
            cursor.execute('DELETE FROM bots WHERE bot_username = ?', (bot_username,))
            affected = cursor.rowcount

            conn.commit()
            conn.close()

            if affected > 0:
                logger.info(f"✅ 删除 Bot: {bot_username}")
                return True
            return False
    except Exception as e:
        logger.error(f"❌ 删除 Bot 失败: {e}")
        return False


# ================== Bot 健康状态 ==================
def update_bot_health(bot_username: str, status: str, detail: str = '',
                      webhook_url: str = None, update_webhook: bool = True) -> bool:
    """记录一次体检结果（status 见 host_bot.HEALTH_* 常量）

    update_webhook=False 时保留原有 webhook_url（例如只想更新"主人失联"状态）
    """
    try:
        with db_lock:
            conn = get_connection()
            cursor = conn.cursor()
            if update_webhook:
                cursor.execute('''
                    UPDATE bots
                    SET health_status = ?, health_detail = ?, webhook_url = ?,
                        last_check_at = CURRENT_TIMESTAMP
                    WHERE bot_username = ?
                ''', (status, (detail or '')[:300], webhook_url, bot_username))
            else:
                cursor.execute('''
                    UPDATE bots
                    SET health_status = ?, health_detail = ?,
                        last_check_at = CURRENT_TIMESTAMP
                    WHERE bot_username = ?
                ''', (status, (detail or '')[:300], bot_username))
            conn.commit()
            conn.close()
            return True
    except Exception as e:
        logger.error(f"❌ 更新 Bot 健康状态失败 {bot_username}: {e}")
        return False


def bump_conflict_count(bot_username: str, delta: int = 1) -> bool:
    """累加 getUpdates 409 冲突次数（说明该 token 被别处同时拉取）"""
    if delta <= 0:
        return False
    try:
        with db_lock:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE bots
                SET conflict_count = COALESCE(conflict_count, 0) + ?,
                    last_conflict_at = CURRENT_TIMESTAMP
                WHERE bot_username = ?
            ''', (delta, bot_username))
            conn.commit()
            conn.close()
            return True
    except Exception as e:
        logger.error(f"❌ 记录冲突次数失败 {bot_username}: {e}")
        return False


def reset_conflict_count(bot_username: str) -> bool:
    """清零冲突计数（例如管理员确认该 Bot 已恢复正常）"""
    try:
        with db_lock:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute(
                'UPDATE bots SET conflict_count = 0, last_conflict_at = NULL WHERE bot_username = ?',
                (bot_username,)
            )
            conn.commit()
            conn.close()
            return True
    except Exception as e:
        logger.error(f"❌ 清零冲突次数失败 {bot_username}: {e}")
        return False


def get_bot_health(bot_username: str) -> Dict:
    """读取单个 Bot 的健康信息"""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT health_status, health_detail, last_check_at,
                   webhook_url, conflict_count, last_conflict_at
            FROM bots WHERE bot_username = ?
        ''', (bot_username,))
        row = cursor.fetchone()
        conn.close()
        if not row:
            return {}
        return {
            'health_status': row['health_status'],
            'health_detail': row['health_detail'],
            'last_check_at': row['last_check_at'],
            'webhook_url': row['webhook_url'],
            'conflict_count': row['conflict_count'] or 0,
            'last_conflict_at': row['last_conflict_at'],
        }
    except Exception as e:
        logger.error(f"❌ 查询 Bot 健康信息失败 {bot_username}: {e}")
        return {}


def get_conflict_counts() -> Dict[str, int]:
    """一次性取回所有 Bot 的冲突计数"""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT bot_username, COALESCE(conflict_count, 0) AS c FROM bots')
        rows = cursor.fetchall()
        conn.close()
        return {row['bot_username']: row['c'] for row in rows}
    except Exception as e:
        logger.error(f"❌ 查询冲突计数失败: {e}")
        return {}
def get_bots_by_owner(owner: int) -> List[Dict]:
    """获取某个用户的所有机器人"""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM bots WHERE owner = ? ORDER BY created_at', (owner,))
        rows = cursor.fetchall()
        conn.close()
        
        bots = []
        for row in rows:
            bots.append({
                'bot_username': row['bot_username'],
                'token': row['token'],
                'welcome_msg': row['welcome_msg'] or ''
            })
        
        return bots
    except Exception as e:
        logger.error(f"❌ 查询用户 Bot 失败: {e}")
        return []
# ================== 用户验证管理 ==================
def is_verified(bot_username: str, user_id: int) -> bool:
    """检查用户是否已验证"""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT 1 FROM verified_users 
            WHERE bot_username = ? AND user_id = ?
        ''', (bot_username, user_id))
        exists = cursor.fetchone() is not None
        conn.close()
        return exists
    except Exception as e:
        logger.error(f"❌ 检查验证状态失败: {e}")
        return False
def add_verified_user(bot_username: str, user_id: int, user_name: str = '', user_username: str = '') -> bool:
    """添加已验证用户"""
    try:
        with db_lock:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO verified_users 
                (bot_username, user_id, user_name, user_username, verified_at)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            ''', (bot_username, user_id, user_name, user_username))
            conn.commit()
            conn.close()
            logger.info(f"✅ 添加验证用户: {bot_username} - {user_id}")
            return True
    except Exception as e:
        logger.error(f"❌ 添加验证用户失败: {e}")
        return False
def remove_verified_user(bot_username: str, user_id: int) -> bool:
    """移除验证用户"""
    try:
        with db_lock:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute('''
                DELETE FROM verified_users 
                WHERE bot_username = ? AND user_id = ?
            ''', (bot_username, user_id))
            conn.commit()
            affected = cursor.rowcount
            conn.close()
            
            if affected > 0:
                logger.info(f"✅ 移除验证用户: {bot_username} - {user_id}")
                return True
            return False
    except Exception as e:
        logger.error(f"❌ 移除验证用户失败: {e}")
        return False
def get_verified_users(bot_username: str) -> List[Dict]:
    """获取某个 Bot 的所有已验证用户"""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT user_id, user_name, user_username, verified_at
            FROM verified_users 
            WHERE bot_username = ?
            ORDER BY verified_at DESC
        ''', (bot_username,))
        rows = cursor.fetchall()
        conn.close()
        
        users = []
        for row in rows:
            users.append({
                'user_id': row['user_id'],
                'user_name': row['user_name'],
                'user_username': row['user_username'],
                'verified_at': row['verified_at']
            })
        
        return users
    except Exception as e:
        logger.error(f"❌ 查询验证用户失败: {e}")
        return []
def get_verified_count(bot_username: str) -> int:
    """获取已验证用户数量"""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT COUNT(*) as count FROM verified_users 
            WHERE bot_username = ?
        ''', (bot_username,))
        count = cursor.fetchone()['count']
        conn.close()
        return count
    except Exception as e:
        logger.error(f"❌ 统计验证用户失败: {e}")
        return 0


# ================== 黑名单管理 ==================

def is_blacklisted(bot_username: str, user_id: int) -> bool:
    """检查用户是否在黑名单中"""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT 1 FROM blacklist 
            WHERE bot_username = ? AND user_id = ?
        ''', (bot_username, user_id))
        exists = cursor.fetchone() is not None
        conn.close()
        return exists
    except Exception as e:
        logger.error(f"❌ 检查黑名单状态失败: {e}")
        return False


def add_to_blacklist(bot_username: str, user_id: int, reason: str = '') -> bool:
    """添加用户到黑名单"""
    try:
        with db_lock:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO blacklist 
                (bot_username, user_id, reason, blocked_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ''', (bot_username, user_id, reason))
            conn.commit()
            conn.close()
            logger.info(f"✅ 添加黑名单用户: {bot_username} - {user_id}")
            return True
    except Exception as e:
        logger.error(f"❌ 添加黑名单用户失败: {e}")
        return False


def remove_from_blacklist(bot_username: str, user_id: int) -> bool:
    """从黑名单移除用户"""
    try:
        with db_lock:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute('''
                DELETE FROM blacklist 
                WHERE bot_username = ? AND user_id = ?
            ''', (bot_username, user_id))
            conn.commit()
            affected = cursor.rowcount
            conn.close()
            
            if affected > 0:
                logger.info(f"✅ 移除黑名单用户: {bot_username} - {user_id}")
                return True
            return False
    except Exception as e:
        logger.error(f"❌ 移除黑名单用户失败: {e}")
        return False


def get_blacklist(bot_username: str) -> List[int]:
    """获取某个 Bot 的黑名单用户ID列表"""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT user_id FROM blacklist 
            WHERE bot_username = ?
            ORDER BY blocked_at DESC
        ''', (bot_username,))
        rows = cursor.fetchall()
        conn.close()
        
        return [row['user_id'] for row in rows]
    except Exception as e:
        logger.error(f"❌ 查询黑名单失败: {e}")
        return []


def get_blacklist_count(bot_username: str) -> int:
    """获取黑名单用户数量"""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT COUNT(*) as count FROM blacklist 
            WHERE bot_username = ?
        ''', (bot_username,))
        count = cursor.fetchone()['count']
        conn.close()
        return count
    except Exception as e:
        logger.error(f"❌ 统计黑名单用户失败: {e}")
        return 0


# ================== 消息映射管理（新版：支持完整映射结构）==================

def set_mapping(bot_username: str, map_type: str, key: str, value: str, user_id: int = None) -> bool:
    """
    设置消息映射
    
    Args:
        bot_username: Bot用户名
        map_type: 映射类型 ('direct', 'topic', 'user_forward', 'forward_user', 'owner_user')
        key: 映射键
        value: 映射值（对于 topic 类型，这里是 topic_id 的字符串形式）
        user_id: 关联的用户ID（可选，用于清理）
    
    映射类型说明：
    - direct: 主人的被转发消息ID -> 用户ID (直连模式)
    - topic: 用户ID -> 话题ID (话题模式)
    - user_forward: 用户消息ID -> 转发后的消息ID
    - forward_user: 转发消息ID -> 用户消息ID
    - owner_user: 主人消息ID -> 发送给用户的消息ID
    """
    try:
        with db_lock:
            conn = get_connection()
            cursor = conn.cursor()
            
            # 先删除旧记录（确保唯一性）
            cursor.execute('''
                DELETE FROM message_mappings 
                WHERE bot_username = ? AND map_type = ? AND key = ?
            ''', (bot_username, map_type, key))
            
            # 插入新记录
            cursor.execute('''
                INSERT INTO message_mappings 
                (bot_username, map_type, key, value, user_id, updated_at)
                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ''', (bot_username, map_type, key, value, user_id))
            
            conn.commit()
            conn.close()
            return True
    except Exception as e:
        logger.error(f"❌ 设置映射失败: {e}")
        return False


def get_mapping(bot_username: str, map_type: str, key: str) -> Optional[str]:
    """
    获取消息映射值
    
    Args:
        bot_username: Bot用户名
        map_type: 映射类型
        key: 映射键
    
    Returns:
        映射值，如果不存在返回 None
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT value FROM message_mappings 
            WHERE bot_username = ? AND map_type = ? AND key = ?
            ORDER BY updated_at DESC LIMIT 1
        ''', (bot_username, map_type, key))
        
        row = cursor.fetchone()
        conn.close()
        
        return row['value'] if row else None
    except Exception as e:
        logger.error(f"❌ 查询映射失败: {e}")
        return None


def get_all_mappings(bot_username: str, map_type: str) -> Dict[str, str]:
    """
    获取某个Bot某种类型的所有映射
    
    Args:
        bot_username: Bot用户名
        map_type: 映射类型
    
    Returns:
        映射字典 {key: value}
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT key, value FROM message_mappings 
            WHERE bot_username = ? AND map_type = ?
            ORDER BY updated_at DESC
        ''', (bot_username, map_type))
        
        rows = cursor.fetchall()
        conn.close()
        
        # 转换为字典
        mappings = {row['key']: row['value'] for row in rows}
        return mappings
    except Exception as e:
        logger.error(f"❌ 查询所有映射失败: {e}")
        return {}


def delete_mapping(bot_username: str, map_type: str, key: str) -> bool:
    """删除指定映射"""
    try:
        with db_lock:
            conn = get_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                DELETE FROM message_mappings 
                WHERE bot_username = ? AND map_type = ? AND key = ?
            ''', (bot_username, map_type, key))
            
            conn.commit()
            affected = cursor.rowcount
            conn.close()
            
            return affected > 0
    except Exception as e:
        logger.error(f"❌ 删除映射失败: {e}")
        return False


def clear_bot_mappings(bot_username: str) -> int:
    """清空某个Bot的所有映射"""
    try:
        with db_lock:
            conn = get_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                DELETE FROM message_mappings 
                WHERE bot_username = ?
            ''', (bot_username,))
            
            deleted = cursor.rowcount
            conn.commit()
            conn.close()
            
            if deleted > 0:
                logger.info(f"🧹 清空 {bot_username} 的 {deleted} 条映射")
            return deleted
    except Exception as e:
        logger.error(f"❌ 清空映射失败: {e}")
        return 0


def cleanup_old_mappings(days: int = 7) -> int:
    """清理旧的消息映射（防止数据库过大）"""
    try:
        with db_lock:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute('''
                DELETE FROM message_mappings 
                WHERE created_at < datetime('now', '-' || ? || ' days')
                AND map_type != 'topic'
            ''', (days,))
            deleted = cursor.rowcount
            conn.commit()
            conn.close()
            
            if deleted > 0:
                logger.info(f"🧹 清理 {deleted} 条旧消息映射")
            return deleted
    except Exception as e:
        logger.error(f"❌ 清理消息映射失败: {e}")
        return 0
# ================== JSON 数据迁移 ==================
def migrate_from_json():
    """从旧版 JSON 文件迁移数据到数据库"""
    import json
    
    json_file = os.path.join(os.path.dirname(__file__), 'bots.json')
    if not os.path.exists(json_file):
        logger.warning("⚠️ 未找到 bots.json 文件，跳过迁移")
        return
    
    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        migrated_count = 0
        for owner_id, info in data.items():
            for bot in info.get('bots', []):
                bot_username = bot.get('bot_username', '')
                token = bot.get('token', '')
                welcome_msg = bot.get('welcome_msg', '')
                mode = bot.get('mode', 'direct')
                forum_group_id = bot.get('forum_group_id')
                
                if bot_username and token:
                    # 添加 Bot 到数据库
                    if add_bot(bot_username, token, int(owner_id), welcome_msg):
                        migrated_count += 1
                        
                        # 更新模式和话题群ID
                        if mode:
                            update_bot_mode(bot_username, mode)
                        if forum_group_id:
                            update_bot_forum_id(bot_username, forum_group_id)
                        
                        logger.info(f"✅ 迁移 Bot: {bot_username} (Owner: {owner_id})")
        
        logger.info(f"🎉 数据迁移完成，共迁移 {migrated_count} 个 Bot")
        
        # 备份旧文件
        backup_file = json_file + '.backup'
        os.rename(json_file, backup_file)
        logger.info(f"📦 旧文件已备份到: {backup_file}")
        
    except Exception as e:
        logger.error(f"❌ JSON 数据迁移失败: {e}")
        import traceback
        traceback.print_exc()
        raise

# ================== 数据库维护 ==================
def vacuum_database():
    """压缩数据库（释放空间）"""
    try:
        conn = get_connection()
        conn.execute('VACUUM')
        conn.close()
        logger.info("✅ 数据库压缩完成")
    except Exception as e:
        logger.error(f"❌ 数据库压缩失败: {e}")
def get_database_stats() -> Dict:
    """获取数据库统计信息"""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        stats = {}
        
        # Bot 数量
        cursor.execute('SELECT COUNT(*) as count FROM bots')
        stats['total_bots'] = cursor.fetchone()['count']
        
        # 验证用户数量
        cursor.execute('SELECT COUNT(*) as count FROM verified_users')
        stats['total_verified_users'] = cursor.fetchone()['count']
        
        # 黑名单用户数量
        cursor.execute('SELECT COUNT(*) as count FROM blacklist')
        stats['total_blacklisted_users'] = cursor.fetchone()['count']
        
        # 消息映射数量
        cursor.execute('SELECT COUNT(*) as count FROM message_mappings')
        stats['total_message_mappings'] = cursor.fetchone()['count']
        
        # 数据库文件大小
        if os.path.exists(DB_FILE):
            stats['db_size_kb'] = round(os.path.getsize(DB_FILE) / 1024, 2)
        else:
            stats['db_size_kb'] = 0
        
        conn.close()
        return stats
    except Exception as e:
        logger.error(f"❌ 获取数据库统计失败: {e}")
        return {}
# ================== 待验证用户管理 ==================

def add_pending_verification(bot_username: str, user_id: int, captcha_answer: str) -> bool:
    """添加待验证用户"""
    try:
        with db_lock:
            conn = get_connection()
            cursor = conn.cursor()
            
            # 检查表是否存在，不存在则创建
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS pending_verifications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    bot_username TEXT NOT NULL,
                    user_id INTEGER NOT NULL,
                    captcha_answer TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(bot_username, user_id)
                )
            ''')
            
            # 删除旧记录（如果存在）
            cursor.execute('''
                DELETE FROM pending_verifications 
                WHERE bot_username = ? AND user_id = ?
            ''', (bot_username, user_id))
            
            # 插入新记录
            cursor.execute('''
                INSERT INTO pending_verifications 
                (bot_username, user_id, captcha_answer, created_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ''', (bot_username, user_id, captcha_answer))
            
            conn.commit()
            conn.close()
            return True
    except Exception as e:
        logger.error(f"❌ 添加待验证用户失败: {e}")
        return False


def get_pending_verification(bot_username: str, user_id: int) -> Optional[str]:
    """获取待验证用户的验证码答案"""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        # 确保表存在
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS pending_verifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bot_username TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                captcha_answer TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(bot_username, user_id)
            )
        ''')
        
        cursor.execute('''
            SELECT captcha_answer FROM pending_verifications 
            WHERE bot_username = ? AND user_id = ?
        ''', (bot_username, user_id))
        
        row = cursor.fetchone()
        conn.close()
        
        return row['captcha_answer'] if row else None
    except Exception as e:
        logger.error(f"❌ 查询待验证用户失败: {e}")
        return None


def remove_pending_verification(bot_username: str, user_id: int) -> bool:
    """移除待验证用户"""
    try:
        with db_lock:
            conn = get_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                DELETE FROM pending_verifications 
                WHERE bot_username = ? AND user_id = ?
            ''', (bot_username, user_id))
            
            conn.commit()
            affected = cursor.rowcount
            conn.close()
            
            return affected > 0
    except Exception as e:
        logger.error(f"❌ 移除待验证用户失败: {e}")
        return False


def cleanup_old_pending_verifications(hours: int = 24) -> int:
    """清理过期的待验证记录（默认24小时）"""
    try:
        with db_lock:
            conn = get_connection()
            cursor = conn.cursor()
            
            # 确保表存在
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS pending_verifications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    bot_username TEXT NOT NULL,
                    user_id INTEGER NOT NULL,
                    captcha_answer TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(bot_username, user_id)
                )
            ''')
            
            cursor.execute('''
                DELETE FROM pending_verifications 
                WHERE created_at < datetime('now', '-' || ? || ' hours')
            ''', (hours,))
            
            deleted = cursor.rowcount
            conn.commit()
            conn.close()
            
            if deleted > 0:
                logger.info(f"🧹 清理 {deleted} 条过期的待验证记录")
            return deleted
    except Exception as e:
        logger.error(f"❌ 清理待验证记录失败: {e}")
        return 0



# ================== 全局设置管理 ==================

def get_global_setting(key: str) -> Optional[str]:
    """获取全局设置值"""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT value FROM global_settings 
            WHERE key = ?
        ''', (key,))
        
        row = cursor.fetchone()
        conn.close()
        
        return row['value'] if row else None
    except Exception as e:
        logger.error(f"❌ 查询全局设置失败: {e}")
        return None


def set_global_setting(key: str, value: str) -> bool:
    """设置全局设置值"""
    try:
        with db_lock:
            conn = get_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT OR REPLACE INTO global_settings 
                (key, value, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
            ''', (key, value))
            
            conn.commit()
            conn.close()
            logger.info(f"✅ 设置全局配置: {key}")
            return True
    except Exception as e:
        logger.error(f"❌ 设置全局配置失败: {e}")
        return False


def delete_global_setting(key: str) -> bool:
    """删除全局设置"""
    try:
        with db_lock:
            conn = get_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                DELETE FROM global_settings 
                WHERE key = ?
            ''', (key,))
            
            conn.commit()
            affected = cursor.rowcount
            conn.close()
            
            if affected > 0:
                logger.info(f"✅ 删除全局配置: {key}")
                return True
            return False
    except Exception as e:
        logger.error(f"❌ 删除全局配置失败: {e}")
        return False


def get_global_welcome() -> Optional[str]:
    """获取管理员设置的全局欢迎语"""
    return get_global_setting('global_welcome_msg')


def set_global_welcome(welcome_msg: str) -> bool:
    """设置管理员的全局欢迎语"""
    return set_global_setting('global_welcome_msg', welcome_msg)


def delete_global_welcome() -> bool:
    """删除管理员的全局欢迎语"""
    return delete_global_setting('global_welcome_msg')


# ================== 验证令牌管理（CF验证）==================

def create_verification_token(bot_username: str, user_id: int, user_name: str = '', user_username: str = '', message_id: int = None) -> Optional[str]:
    """创建验证令牌（5分钟有效期）"""
    import secrets
    from datetime import datetime, timedelta
    
    try:
        # 生成安全的随机令牌
        token = secrets.token_urlsafe(32)
        expires_at = (datetime.now() + timedelta(minutes=5)).isoformat()
        
        with db_lock:
            conn = get_connection()
            cursor = conn.cursor()
            
            # 删除该用户的旧令牌（如果存在）
            cursor.execute('''
                DELETE FROM verification_tokens 
                WHERE bot_username = ? AND user_id = ?
            ''', (bot_username, user_id))
            
            # 插入新令牌
            cursor.execute('''
                INSERT INTO verification_tokens 
                (token, bot_username, user_id, user_name, user_username, message_id, expires_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (token, bot_username, user_id, user_name, user_username, message_id, expires_at))
            
            conn.commit()
            conn.close()
            logger.info(f"✅ 创建验证令牌: {bot_username} - {user_id}")
            return token
    except Exception as e:
        logger.error(f"❌ 创建验证令牌失败: {e}")
        return None


def get_verification_token(token: str) -> Optional[Dict]:
    """获取验证令牌信息（如果有效）"""
    from datetime import datetime
    
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM verification_tokens 
            WHERE token = ?
        ''', (token,))
        
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            return None
        
        # 检查是否过期
        expires_at = datetime.fromisoformat(row['expires_at'])
        if datetime.now() > expires_at:
            logger.info(f"⏰ 验证令牌已过期: {token[:10]}...")
            return None
        
        return {
            'token': row['token'],
            'bot_username': row['bot_username'],
            'user_id': row['user_id'],
            'user_name': row['user_name'],
            'user_username': row['user_username'],
            'message_id': row['message_id'] if 'message_id' in row.keys() else None,
            'created_at': row['created_at'],
            'expires_at': row['expires_at']
        }
    except Exception as e:
        logger.error(f"❌ 查询验证令牌失败: {e}")
        return None


def delete_verification_token(token: str) -> bool:
    """删除已使用的验证令牌"""
    try:
        with db_lock:
            conn = get_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                DELETE FROM verification_tokens 
                WHERE token = ?
            ''', (token,))
            
            conn.commit()
            affected = cursor.rowcount
            conn.close()
            
            if affected > 0:
                logger.info(f"✅ 删除验证令牌: {token[:10]}...")
                return True
            return False
    except Exception as e:
        logger.error(f"❌ 删除验证令牌失败: {e}")
        return False


def cleanup_expired_tokens() -> int:
    """清理过期的验证令牌"""
    try:
        with db_lock:
            conn = get_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                DELETE FROM verification_tokens 
                WHERE expires_at < datetime('now')
            ''')
            
            deleted = cursor.rowcount
            conn.commit()
            conn.close()
            
            if deleted > 0:
                logger.info(f"🧹 清理 {deleted} 个过期验证令牌")
            return deleted
    except Exception as e:
        logger.error(f"❌ 清理过期令牌失败: {e}")
        return 0


# ================== 启动时初始化 ==================

# 模块导入时自动初始化数据库
init_database()

# 清理过期数据（可选）
try:
    cleanup_old_pending_verifications(24)  # 清理24小时前的待验证记录
    cleanup_old_mappings(30)  # 清理30天前的消息映射
    cleanup_expired_tokens()  # 清理过期的CF验证令牌
except Exception as e:
    logger.error(f"清理过期数据失败: {e}")

if __name__ == '__main__':
    # 测试代码
    print("数据库测试模式")
    print(f"数据库文件: {DB_FILE}")
    
    # 显示统计信息
    stats = get_database_stats()
    print("\n📊 数据库统计:")
    for key, value in stats.items():
        print(f"  {key}: {value}")
    
    # 测试添加 Bot
    print("\n🧪 测试添加 Bot...")
    add_bot("test_bot", "123456:ABC", 999999, "欢迎测试")
    
    # 测试查询
    print("\n🔍 测试查询...")
    bot = get_bot("test_bot")
    print(f"  查询结果: {bot}")
    
    # 显示所有 Bot
    all_bots = get_all_bots()
    print(f"\n📋 所有 Bot ({len(all_bots)} 个):")
    for username, info in all_bots.items():
        print(f"  - {username}: Owner={info['owner']}")
