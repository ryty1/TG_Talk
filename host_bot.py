#!/opt/tg_multi_bot/venv/bin/python
import os
import json
import logging
import asyncio
from datetime import datetime
from functools import partial
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters
)
from dotenv import load_dotenv
load_dotenv()

# ================== 配置 ==================
BOTS_FILE = "bots.json"
MAP_FILE = "msg_map.json"
ADMIN_CHANNEL = os.environ.get("ADMIN_CHANNEL")  # 宿主通知群/频道

bots_data = {}
msg_map = {}
running_apps = {}

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# ================== 工具函数 ==================
def load_bots():
    global bots_data
    if os.path.exists(BOTS_FILE):
        with open(BOTS_FILE, "r", encoding="utf-8") as f:
            bots_data = json.load(f)
    else:
        bots_data = {}

def save_bots():
    with open(BOTS_FILE, "w", encoding="utf-8") as f:
        json.dump(bots_data, f, ensure_ascii=False, indent=2)

def load_map():
    global msg_map
    if os.path.exists(MAP_FILE):
        with open(MAP_FILE, "r", encoding="utf-8") as f:
            msg_map = json.load(f)
    else:
        msg_map = {}

def save_map():
    with open(MAP_FILE, "w", encoding="utf-8") as f:
        json.dump(msg_map, f, ensure_ascii=False, indent=2)

async def reply_and_auto_delete(message, text, delay=5, **kwargs):
    try:
        sent = await message.reply_text(text, **kwargs)
        await asyncio.sleep(delay)
        await sent.delete()
    except Exception:
        pass

async def send_admin_log(text: str):
    if not ADMIN_CHANNEL:
        return
    try:
        app = running_apps.get("__manager__")
        if app:
            await app.bot.send_message(chat_id=ADMIN_CHANNEL, text=text)
    except Exception as e:
        logger.error(f"宿主通知失败: {e}")

# ================== 宿主机 /start 菜单 ==================
async def manager_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("➕ 添加机器人", callback_data="addbot")],
        [InlineKeyboardButton("🤖 我的机器人", callback_data="mybots")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.message:
        await update.message.reply_text("📣 欢迎使用客服机器人管理面板\n👇 请选择操作：", reply_markup=reply_markup)
    elif update.callback_query:
        query = update.callback_query
        await query.answer()
        await query.message.edit_text("📣 欢迎使用客服机器人管理面板\n👇 请选择操作：", reply_markup=reply_markup)

# ================== 子机器人 /start ==================
async def subbot_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 欢迎使用客服 Bot\n\n"
        "请直接输入消息，主人收到就会回复你"
    )

# ================== 消息转发逻辑 ==================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE, owner_id: int, bot_username: str):
    try:
        user_id = update.message.chat.id

        if user_id == owner_id:  # 管理员回复
            if update.message.reply_to_message:
                reply_msg_id = str(update.message.reply_to_message.message_id)
                if bot_username in msg_map and reply_msg_id in msg_map[bot_username]:
                    target_user = msg_map[bot_username][reply_msg_id]
                    await context.bot.copy_message(
                        chat_id=target_user,
                        from_chat_id=user_id,
                        message_id=update.message.message_id
                    )
                    await reply_and_auto_delete(update.message, "✅ 回复已送达", delay=5)
                else:
                    await reply_and_auto_delete(update.message, "⚠️ 找不到对应的用户映射。", delay=10)
            else:
                await reply_and_auto_delete(update.message, "请直接回复用户的消息。", delay=10)

        else:  # 普通用户发消息
            fwd_msg = await context.bot.forward_message(
                chat_id=owner_id,
                from_chat_id=user_id,
                message_id=update.message.message_id
            )
            msg_map.setdefault(bot_username, {})[str(fwd_msg.message_id)] = user_id
            save_map()
            await reply_and_auto_delete(update.message, "✅ 已成功发送", delay=5)

    except Exception as e:
        logger.error(f"[{bot_username}] 转发错误: {e}")

# ================== 动态管理 Bot ==================
async def token_listener(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """监听用户输入的 token 并尝试添加"""
    if not context.user_data.get("waiting_token"):
        return

    token = update.message.text.strip()
    context.user_data["waiting_token"] = False

    try:
        tmp_app = Application.builder().token(token).build()
        bot_info = await tmp_app.bot.get_me()
        bot_username = bot_info.username
    except Exception:
        await reply_and_auto_delete(update.message, "❌ Token 无效，请检查。", delay=10)
        return

    owner_id = str(update.message.chat.id)
    owner_username = update.message.from_user.username or ""

    bots_data.setdefault(owner_id, {"username": owner_username, "bots": []})
    if any(b["token"] == token for b in bots_data[owner_id]["bots"]):
        await reply_and_auto_delete(update.message, "⚠️ 这个 Bot 已经添加过了。", delay=10)
        return

    bots_data[owner_id]["bots"].append({
        "token": token,
        "bot_username": bot_username,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M")
    })
    save_bots()

    new_app = Application.builder().token(token).build()
    new_app.add_handler(CommandHandler("start", subbot_start))
    new_app.add_handler(MessageHandler(filters.ALL, partial(handle_message, owner_id=int(owner_id), bot_username=bot_username)))

    running_apps[bot_username] = new_app
    await new_app.initialize()
    await new_app.start()
    await new_app.updater.start_polling()

    await update.message.reply_text(f"✅ 已添加并启动Bot：{bot_username}")

    # 🔔 添加通知
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    log_text = (
        f"🛒 用户 @{owner_username or '未知'}\n"
        f"🆔 ({owner_id})\n"
        f"🤖 Bot: @{bot_username}\n"
        f"⏰ {now}"
    )
    await send_admin_log(log_text)

# ================== 菜单回调 ==================
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    await query.answer()

    if data == "addbot":
        await query.message.reply_text("㊙️ 请输入要添加的 Bot Token：")
        context.user_data["waiting_token"] = True

    elif data == "mybots":
        owner_id = str(query.from_user.id)
        bots = bots_data.get(owner_id, {}).get("bots", [])
        if not bots:
            await reply_and_auto_delete(query.message, "⚠️ 你还没有绑定任何 Bot。", delay=10)
            return

        keyboard = [
            [InlineKeyboardButton(f"@{b['bot_username']}", callback_data=f"info_{b['bot_username']}")]
            for b in bots
        ]
        await query.message.edit_text("📋 你的 Bot 列表：", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data.startswith("info_"):
        bot_username = data.split("_", 1)[1]
        owner_id = str(query.from_user.id)

        bots = bots_data.get(owner_id, {}).get("bots", [])
        target_bot = next((b for b in bots if b["bot_username"] == bot_username), None)
        if not target_bot:
            await reply_and_auto_delete(query.message, "⚠️ 找不到这个 Bot。", delay=10)
            return

        info_text = (
            f"🤖 Bot: @{bot_username}\n"
            f"🔑 Token: {target_bot['token'][:10]}... （已隐藏）\n"
            f"👤 绑定用户: @{bots_data[owner_id].get('username', '未知')}\n"
            f"🆔 用户ID: {owner_id}\n"
            f"⏰ 创建时间: {target_bot.get('created_at', '未知')}"
        )

        keyboard = [
            [InlineKeyboardButton("❌ 断开连接", callback_data=f"del_{bot_username}")],
            [InlineKeyboardButton("🔙 返回", callback_data="mybots")]
        ]
        await query.message.edit_text(info_text, reply_markup=InlineKeyboardMarkup(keyboard))

    elif data.startswith("del_"):
        bot_username = data.split("_", 1)[1]
        owner_id = str(query.from_user.id)
        owner_username = query.from_user.username or ""

        bots = bots_data.get(owner_id, {}).get("bots", [])
        target_bot = next((b for b in bots if b["bot_username"] == bot_username), None)
        if not target_bot:
            await reply_and_auto_delete(query.message, "⚠️ 找不到这个 Bot。", delay=10)
            return

        try:
            if bot_username in running_apps:
                app = running_apps.pop(bot_username)
                await app.updater.stop()
                await app.stop()
                await app.shutdown()
            bots.remove(target_bot)
            if not bots:
                bots_data.pop(owner_id, None)
            save_bots()
            await query.message.edit_text(f"✅ 已断开Bot：@{bot_username}")

            # 🔔 删除通知
            now = datetime.now().strftime("%Y-%m-%d %H:%M")
            log_text = (
                f"🗑 用户 @{owner_username or '未知'}\n"
                f"🆔 ({owner_id})\n"
                f"🤖 Bot: @{bot_username}\n"
                f"⏰ {now}"
            )
            await send_admin_log(log_text)
        except Exception as e:
            await reply_and_auto_delete(query.message, f"❌ 删除失败: {e}", delay=10)

# ================== 主入口 ==================
async def run_all_bots():
    load_bots()
    load_map()

    # 启动子 bot
    for owner_id, info in bots_data.items():
        for b in info["bots"]:
            token = b["token"]; bot_username = b["bot_username"]
            try:
                app = Application.builder().token(token).build()
                app.add_handler(CommandHandler("start", subbot_start))
                app.add_handler(MessageHandler(filters.ALL, partial(handle_message, owner_id=int(owner_id), bot_username=bot_username)))
                running_apps[bot_username] = app
                await app.initialize(); await app.start(); await app.updater.start_polling()
                logger.info(f"启动Bot: {bot_username}")
            except Exception as e:
                logger.error(f"子Bot启动失败: {bot_username} {e}")

    # 管理 Bot
    manager_token = os.environ.get("MANAGER_TOKEN")
    if manager_token:
        manager_app = Application.builder().token(manager_token).build()
        manager_app.add_handler(CommandHandler("start", manager_start))
        manager_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, token_listener))
        manager_app.add_handler(CallbackQueryHandler(callback_handler))
        running_apps["__manager__"] = manager_app
        await manager_app.initialize(); await manager_app.start(); await manager_app.updater.start_polling()
        logger.info("管理 Bot 已启动 ✅")

    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(run_all_bots())
