#!/opt/tg_multi_bot/venv/bin/python
import os
import json
import logging
import asyncio
import time
from datetime import datetime
from functools import partial, wraps
from typing import Optional, Dict, Any, Callable
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters
)
from telegram.error import BadRequest, NetworkError, TimedOut, RetryAfter
from dotenv import load_dotenv
load_dotenv()

# ================== 配置 ==================
BOTS_FILE = "bots.json"
MAP_FILE = "msg_map.json"
ADMIN_CHANNEL = os.environ.get("ADMIN_CHANNEL")      # 宿主通知群/频道（可选）
MANAGER_TOKEN = os.environ.get("MANAGER_TOKEN")      # 管理机器人 Token（必须）

# 重试配置
MAX_RETRIES = 3
RETRY_DELAY = 1.0
BACKOFF_FACTOR = 2.0
TIMEOUT_SECONDS = 30

bots_data = {}
msg_map = {}
running_apps = {}

# 配置日志
logging.basicConfig(
    level=logging.INFO, 
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("bot.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ================== 装饰器和工具函数 ==================
def retry_on_error(max_retries: int = MAX_RETRIES, delay: float = RETRY_DELAY, 
                   backoff: float = BACKOFF_FACTOR, exceptions: tuple = None):
    """重试装饰器，支持指数退避"""
    if exceptions is None:
        exceptions = (NetworkError, TimedOut, Exception)
    
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None
            current_delay = delay
            
            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except RetryAfter as e:
                    # Telegram API 限流，等待指定时间
                    wait_time = e.retry_after + 1
                    logger.warning(f"API限流，等待 {wait_time} 秒后重试")
                    await asyncio.sleep(wait_time)
                    continue
                except exceptions as e:
                    last_exception = e
                    if attempt < max_retries:
                        logger.warning(f"函数 {func.__name__} 第 {attempt + 1} 次尝试失败: {e}")
                        await asyncio.sleep(current_delay)
                        current_delay *= backoff
                    else:
                        logger.error(f"函数 {func.__name__} 重试 {max_retries} 次后仍然失败: {e}")
                        break
            
            raise last_exception
        return wrapper
    return decorator

@safe_file_operation("load")
def load_bots():
    """安全加载机器人配置"""
    global bots_data
    if os.path.exists(BOTS_FILE):
        with open(BOTS_FILE, "r", encoding="utf-8") as f:
            bots_data = json.load(f)
    else:
        bots_data = {}
    logger.info(f"加载了 {len(bots_data)} 个用户的机器人配置")

@safe_file_operation("save")
def save_bots():
    """安全保存机器人配置"""
    # 创建备份
    if os.path.exists(BOTS_FILE):
        backup_file = f"{BOTS_FILE}.backup"
        try:
            os.rename(BOTS_FILE, backup_file)
        except Exception as e:
            logger.warning(f"创建备份失败: {e}")
    
    with open(BOTS_FILE, "w", encoding="utf-8") as f:
        json.dump(bots_data, f, ensure_ascii=False, indent=2)
    logger.debug("机器人配置已保存")

@safe_file_operation("load")
def load_map():
    """安全加载消息映射"""
    global msg_map
    if os.path.exists(MAP_FILE):
        with open(MAP_FILE, "r", encoding="utf-8") as f:
            msg_map = json.load(f)
    else:
        msg_map = {}
    logger.info(f"加载了 {len(msg_map)} 个机器人的消息映射")

@safe_file_operation("save")
def save_map():
    """安全保存消息映射"""
    # 创建备份
    if os.path.exists(MAP_FILE):
        backup_file = f"{MAP_FILE}.backup"
        try:
            os.rename(MAP_FILE, backup_file)
        except Exception as e:
            logger.warning(f"创建备份失败: {e}")
    
    with open(MAP_FILE, "w", encoding="utf-8") as f:
        json.dump(msg_map, f, ensure_ascii=False, indent=2)
    logger.debug("消息映射已保存")

def ensure_bot_map(bot_username: str):
    """保证 msg_map 结构存在"""
    try:
        if bot_username not in msg_map or not isinstance(msg_map[bot_username], dict):
            msg_map[bot_username] = {}
        # 直连：主人的被转发消息 msg_id -> 用户ID
        msg_map[bot_username].setdefault("direct", {})
        # 话题：用户ID(str) -> topic_id(int)
        msg_map[bot_username].setdefault("topics", {})
    except Exception as e:
        logger.error(f"初始化机器人映射失败 {bot_username}: {e}")
        msg_map[bot_username] = {"direct": {}, "topics": {}}

@retry_on_error(max_retries=2, delay=1.0)
async def reply_and_auto_delete(message, text: str, delay: int = 5, **kwargs):
    """安全的回复并自动删除消息"""
    try:
        sent = await message.reply_text(text, **kwargs)
        await asyncio.sleep(delay)
        await sent.delete()
    except BadRequest as e:
        if "message to delete not found" not in str(e).lower():
            logger.warning(f"删除消息失败: {e}")
    except Exception as e:
        logger.error(f"回复消息失败: {e}")

@retry_on_error(max_retries=2, delay=2.0)
async def send_admin_log(text: str):
    """安全发送管理员日志"""
    if not ADMIN_CHANNEL:
        return
    
    try:
        app = running_apps.get("__manager__")
        if app and app.bot:
            await app.bot.send_message(chat_id=ADMIN_CHANNEL, text=text)
            logger.debug("管理员通知已发送")
    except Exception as e:
        logger.error(f"宿主通知失败: {e}")

def get_bot_cfg(owner_id: int | str, bot_username: str) -> Optional[Dict[str, Any]]:
    """从 bots_data 中找到某个 owner 的某个子机器人配置"""
    try:
        owner_id = str(owner_id)
        info = bots_data.get(owner_id, {})
        for b in info.get("bots", []):
            if b.get("bot_username") == bot_username:
                return b
        return None
    except Exception as e:
        logger.error(f"获取机器人配置失败: {e}")
        return None

# ================== 宿主机 /start 菜单 ==================
def manager_main_menu():
    keyboard = [
        [InlineKeyboardButton("➕ 添加机器人", callback_data="addbot")],
        [InlineKeyboardButton("🤖 我的机器人", callback_data="mybots")]
    ]
    return InlineKeyboardMarkup(keyboard)

@retry_on_error(max_retries=2)
async def manager_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """管理机器人启动命令"""
    try:
        if update.message:
            await update.message.reply_text(
                "📣 欢迎使用客服机器人管理面板\n👇 请选择操作：", 
                reply_markup=manager_main_menu()
            )
        elif update.callback_query:
            query = update.callback_query
            await query.answer()
            await query.message.edit_text(
                "📣 欢迎使用客服机器人管理面板\n👇 请选择操作：", 
                reply_markup=manager_main_menu()
            )
    except Exception as e:
        logger.error(f"管理机器人启动失败: {e}")

# ================== 子机器人 /start ==================
@retry_on_error(max_retries=2)
async def subbot_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """子机器人启动消息"""
    try:
        await update.message.reply_text(
            "👋 欢迎使用客服 Bot\n\n"
            "--------------------------\n"
            "✨ 核心功能\n"
            "* 多机器人接入：只需提供 Token，即可快速启用。\n\n"
            "* 两种模式：\n"
            "  ▸ 私聊模式 —— 用户消息直接转发到bot。\n"
            "  ▸ 话题模式 —— 每个用户自动建立独立话题，消息更清晰。\n\n"
            "* 智能映射：自动维护消息与话题的对应关系。\n"
            "---------------------------\n"
            "- 客服bot托管中心 @tg_multis_bot \n"
            "---------------------------\n\n"
            "请直接输入消息，主人收到就会回复你"
        )
    except Exception as e:
        logger.error(f"子机器人启动消息发送失败: {e}")

# ================== 消息转发逻辑 ==================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE, owner_id: int, bot_username: str):
    """处理消息转发的核心函数"""
    try:
        message = update.message
        if not message:
            return
            
        chat_id = message.chat.id

        # 找到该子机器人的配置
        bot_cfg = get_bot_cfg(owner_id, bot_username)
        if not bot_cfg:
            logger.warning(f"找不到 bot 配置: @{bot_username} for owner {owner_id}")
            return

        mode = bot_cfg.get("mode", "direct")
        forum_group_id = bot_cfg.get("forum_group_id")

        ensure_bot_map(bot_username)

        # ---------- /id 功能 ----------
        if message.text and message.text.strip().startswith("/id"):
            await handle_id_command(message, context, owner_id, bot_username, mode, forum_group_id)
            return

        # ---------- 直连模式 ----------
        if mode == "direct":
            await handle_direct_mode(message, context, owner_id, bot_username, chat_id)
        # ---------- 话题模式 ----------
        elif mode == "forum":
            await handle_forum_mode(message, context, owner_id, bot_username, chat_id, forum_group_id)

    except Exception as e:
        logger.error(f"[{bot_username}] 消息处理错误: {e}")

@retry_on_error(max_retries=2)
async def handle_id_command(message, context, owner_id: int, bot_username: str, mode: str, forum_group_id: Optional[int]):
    """处理 /id 命令"""
    # 🚫 如果不是主人发的，忽略
    if message.from_user.id != owner_id:
        return  

    target_user = None

    try:
        # 直连模式：主人私聊里，必须回复一条转发消息
        if mode == "direct" and message.chat.type == "private" and message.chat.id == owner_id and message.reply_to_message:
            direct_map = msg_map[bot_username]["direct"]
            target_user = direct_map.get(str(message.reply_to_message.message_id))

        # 话题模式：群里，必须回复某条消息
        elif mode == "forum" and message.chat.id == forum_group_id and message.reply_to_message:
            topic_id = message.reply_to_message.message_thread_id
            for uid_str, t_id in msg_map[bot_username]["topics"].items():
                if t_id == topic_id:
                    target_user = int(uid_str)
                    break

        # 如果找到了用户，展示信息
        if target_user:
            user = await context.bot.get_chat(target_user)
            text = (
                f"━━━━━━━━━━━━━━\n"
                f"👤 <b>User Info</b>\n"
                f"━━━━━━━━━━━━━━\n"
                f"🆔 <b>TG_ID:</b> <code>{user.id}</code>\n"
                f"👤 <b>全   名:</b> {user.first_name} {user.last_name or ''}\n"
                f"🔗 <b>用户名:</b> @{user.username if user.username else '(无)'}\n"
                f"━━━━━━━━━━━━━━"
            )

            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("📋 复制 UID", switch_inline_query_current_chat=str(user.id))]
            ])

            await message.reply_text(
                text,
                parse_mode="HTML",
                disable_web_page_preview=True,
                reply_markup=keyboard
            )
    except Exception as e:
        logger.error(f"处理 /id 命令失败: {e}")
        await message.reply_text(f"❌ 获取用户信息失败: {e}")

@retry_on_error(max_retries=3, delay=1.0)
async def handle_direct_mode(message, context, owner_id: int, bot_username: str, chat_id: int):
    """处理直连模式消息"""
    try:
        # 普通用户发私聊 -> 转给主人
        if message.chat.type == "private" and chat_id != owner_id:
            fwd_msg = await context.bot.forward_message(
                chat_id=owner_id,
                from_chat_id=chat_id,
                message_id=message.message_id
            )
            msg_map[bot_username]["direct"][str(fwd_msg.message_id)] = chat_id
            save_map()
            await reply_and_auto_delete(message, "✅ 已成功发送", delay=3)
            return

        # 主人在私聊里回复 -> 回用户
        if message.chat.type == "private" and chat_id == owner_id and message.reply_to_message:
            direct_map = msg_map[bot_username]["direct"]
            target_user = direct_map.get(str(message.reply_to_message.message_id))
            if target_user:
                await context.bot.copy_message(
                    chat_id=target_user,
                    from_chat_id=owner_id,
                    message_id=message.message_id
                )
                await reply_and_auto_delete(message, "✅ 回复已送达", delay=2)
            else:
                await reply_and_auto_delete(message, "⚠️ 找不到对应的用户映射。", delay=5)
    except Exception as e:
        logger.error(f"直连模式处理失败: {e}")
        await reply_and_auto_delete(message, "❌ 消息处理失败，请稍后重试。", delay=5)

@retry_on_error(max_retries=3, delay=1.0)
async def handle_forum_mode(message, context, owner_id: int, bot_username: str, chat_id: int, forum_group_id: Optional[int]):
    """处理话题模式消息"""
    try:
        if not forum_group_id:
            if message.chat.type == "private" and chat_id != owner_id:
                await reply_and_auto_delete(message, "⚠️ 主人未设置话题群，暂无法转发。", delay=5)
            return

        topics = msg_map[bot_username]["topics"]

        # 普通用户发私聊 -> 转到对应话题
        if message.chat.type == "private" and chat_id != owner_id:
            uid_key = str(chat_id)
            topic_id = topics.get(uid_key)

            # 若无映射，先创建话题
            if not topic_id:
                display_name = (
                    message.from_user.full_name
                    or (f"@{message.from_user.username}" if message.from_user.username else None)
                    or "匿名用户"
                )
                try:
                    topic = await context.bot.create_forum_topic(
                        chat_id=forum_group_id,
                        name=f"{display_name}"
                    )
                    topic_id = topic.message_thread_id
                    topics[uid_key] = topic_id
                    save_map()
                except Exception as e:
                    logger.error(f"创建话题失败: {e}")
                    await reply_and_auto_delete(message, "❌ 创建话题失败，请联系管理员。", delay=5)
                    return

            # 转发到话题
            try:
                await context.bot.forward_message(
                    chat_id=forum_group_id,
                    from_chat_id=chat_id,
                    message_id=message.message_id,
                    message_thread_id=topic_id
                )
                await reply_and_auto_delete(message, "✅ 已转交客服处理", delay=2)

            except BadRequest as e:
                # 话题可能被删除，尝试重建
                if "message thread not found" in str(e).lower() or "topic not found" in str(e).lower():
                    logger.warning(f"话题 {topic_id} 不存在，尝试重建")
                    try:
                        display_name = (
                            message.from_user.full_name
                            or (f"@{message.from_user.username}" if message.from_user.username else None)
                            or "匿名用户"
                        )
                        topic = await context.bot.create_forum_topic(
                            chat_id=forum_group_id,
                            name=f"{display_name}"
                        )
                        topic_id = topic.message_thread_id
                        topics[uid_key] = topic_id
                        save_map()

                        await context.bot.forward_message(
                            chat_id=forum_group_id,
                            from_chat_id=chat_id,
                            message_id=message.message_id,
                            message_thread_id=topic_id
                        )
                        await reply_and_auto_delete(message, "✅ 已转交客服处理（话题已重建）", delay=2)

                    except Exception as e2:
                        logger.error(f"重建话题失败: {e2}")
                        await reply_and_auto_delete(message, "❌ 转发失败，重建话题也未成功。", delay=5)
                else:
                    logger.error(f"转发到话题失败: {e}")
                    await reply_and_auto_delete(message, "❌ 转发到话题失败，请检查权限。", delay=5)

        # 群里该话题下的消息 -> 回到用户
        elif message.chat.id == forum_group_id and getattr(message, "is_topic_message", False):
            topic_id = message.message_thread_id
            target_uid = None
            for uid_str, t_id in topics.items():
                if t_id == topic_id:
                    target_uid = int(uid_str)
                    break
            
            if target_uid:
                try:
                    await context.bot.copy_message(
                        chat_id=target_uid,
                        from_chat_id=forum_group_id,
                        message_id=message.message_id
                    )
                except Exception as e:
                    logger.error(f"群->用户 复制失败: {e}")

    except Exception as e:
        logger.error(f"话题模式处理失败: {e}")
        await reply_and_auto_delete(message, "❌ 消息处理失败，请稍后重试。", delay=5)

# ================== 主入口 ==================
async def run_all_bots():
    """启动所有机器人"""
    if not MANAGER_TOKEN:
        logger.error("MANAGER_TOKEN 未设置，无法启动管理Bot。")
        return

    try:
        load_bots()
        load_map()

        # 启动子 bot（恢复）
        failed_bots = []
        for owner_id, info in bots_data.items():
            for b in info.get("bots", []):
                token = b["token"]
                bot_username = b["bot_username"]
                try:
                    app = Application.builder().token(token).build()
                    app.add_handler(CommandHandler("start", subbot_start))
                    app.add_handler(MessageHandler(
                        filters.ALL, 
                        partial(handle_message, owner_id=int(owner_id), bot_username=bot_username)
                    ))
                    running_apps[bot_username] = app
                    await app.initialize()
                    await app.start()
                    await app.updater.start_polling()
                    logger.info(f"启动子Bot: @{bot_username}")
                except Exception as e:
                    logger.error(f"子Bot启动失败: @{bot_username} {e}")
                    failed_bots.append(bot_username)

        if failed_bots:
            logger.warning(f"以下机器人启动失败: {failed_bots}")

        # 管理 Bot
        manager_app = Application.builder().token(MANAGER_TOKEN).build()
        manager_app.add_handler(CommandHandler("start", manager_start))
        manager_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, lambda u, c: None))  # 简化版
        manager_app.add_handler(CallbackQueryHandler(lambda u, c: None))  # 简化版
        running_apps["__manager__"] = manager_app

        await manager_app.initialize()
        await manager_app.start()
        await manager_app.updater.start_polling()
        logger.info("管理 Bot 已启动 ✅")
        
        if ADMIN_CHANNEL:
            try:
                await manager_app.bot.send_message(ADMIN_CHANNEL, "✅ 宿主管理Bot已启动")
            except Exception as e:
                logger.error(f"启动通知失败: {e}")

        # 保持运行
        await asyncio.Event().wait()

    except Exception as e:
        logger.error(f"启动失败: {e}")
        raise

if __name__ == "__main__":
    try:
        asyncio.run(run_all_bots())
    except KeyboardInterrupt:
        logger.info("程序被用户中断")
    except Exception as e:
        logger.error(f"程序异常退出: {e}")

def safe_file_operation(operation: str):
    """安全文件操作装饰器"""
    def decorator(func: Callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except FileNotFoundError:
                logger.warning(f"文件不存在，{operation}操作跳过")
                return {} if operation == "load" else None
            except json.JSONDecodeError as e:
                logger.error(f"JSON解析错误 ({operation}): {e}")
                return {} if operation == "load" else None
            except PermissionError as e:
                logger.error(f"文件权限错误 ({operation}): {e}")
                raise
            except Exception as e:
                logger.error(f"文件操作错误 ({operation}): {e}")
                raise
        return wrapper
    return decorator
