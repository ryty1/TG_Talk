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
from telegram.error import BadRequest
from dotenv import load_dotenv
load_dotenv()

# ================== 配置 ==================
BOTS_FILE = "bots.json"
MAP_FILE = "msg_map.json"
ADMIN_CHANNEL = os.environ.get("ADMIN_CHANNEL")      # 宿主通知群/频道（可选）
MANAGER_TOKEN = os.environ.get("MANAGER_TOKEN")      # 管理机器人 Token（必须）

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

def ensure_bot_map(bot_username: str):
    """保证 msg_map 结构存在"""
    if bot_username not in msg_map or not isinstance(msg_map[bot_username], dict):
        msg_map[bot_username] = {}
    # 直连：主人的被转发消息 msg_id -> 用户ID
    msg_map[bot_username].setdefault("direct", {})
    # 话题：用户ID(str) -> topic_id(int)
    msg_map[bot_username].setdefault("topics", {})

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

def get_bot_cfg(owner_id: int | str, bot_username: str):
    """从 bots_data 中找到某个 owner 的某个子机器人配置"""
    owner_id = str(owner_id)
    info = bots_data.get(owner_id, {})
    for b in info.get("bots", []):
        if b.get("bot_username") == bot_username:
            return b
    return None

# ================== 宿主机 /start 菜单 ==================
def manager_main_menu():
    keyboard = [
        [InlineKeyboardButton("➕ 添加机器人", callback_data="addbot")],
        [InlineKeyboardButton("🤖 我的机器人", callback_data="mybots")]
    ]
    return InlineKeyboardMarkup(keyboard)

async def manager_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message:
        await update.message.reply_text("📣 欢迎使用客服机器人管理面板\n👇 请选择操作：", reply_markup=manager_main_menu())
    elif update.callback_query:
        query = update.callback_query
        await query.answer()
        await query.message.edit_text("📣 欢迎使用客服机器人管理面板\n👇 请选择操作：", reply_markup=manager_main_menu())

# ================== 子机器人 /start ==================
async def subbot_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 欢迎使用客服 Bot\n\n"
        "请直接输入消息，主人收到就会回复你"
    )

# ================== 消息转发逻辑（直连/话题 可切换） ==================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE, owner_id: int, bot_username: str):
    """
    - 直连模式(direct):
      用户私聊 -> 转发到 owner 私聊；owner 在私聊里“回复该条转发” -> 回到对应用户
    - 话题模式(forum):
      用户私聊 -> 转发到话题群“用户专属话题”；群里该话题下的消息 -> 回到对应用户
    """
    try:
        message = update.message
        chat_id = message.chat.id

        # 找到该子机器人的配置
        bot_cfg = get_bot_cfg(owner_id, bot_username)
        if not bot_cfg:
            logger.warning(f"找不到 bot 配置: @{bot_username} for owner {owner_id}")
            return

        mode = bot_cfg.get("mode", "direct")
        forum_group_id = bot_cfg.get("forum_group_id")

        ensure_bot_map(bot_username)

        # ---------- 直连模式 ----------
        if mode == "direct":
            # 普通用户发私聊 -> 转给主人
            if message.chat.type == "private" and chat_id != owner_id:
                fwd_msg = await context.bot.forward_message(
                    chat_id=owner_id,
                    from_chat_id=chat_id,
                    message_id=message.message_id
                )
                # 记录：主人的该条“被转发消息”的 msg_id -> 用户ID
                msg_map[bot_username]["direct"][str(fwd_msg.message_id)] = chat_id
                save_map()
                await reply_and_auto_delete(message, "✅ 已成功发送", delay=5)
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
                    await reply_and_auto_delete(message, "✅ 回复已送达", delay=5)
                else:
                    await reply_and_auto_delete(message, "⚠️ 找不到对应的用户映射。", delay=10)
                return

        # ---------- 话题模式 ----------
        elif mode == "forum":
            if not forum_group_id:
                # 未设置话题群
                if message.chat.type == "private" and chat_id != owner_id:
                    await reply_and_auto_delete(message, "⚠️ 主人未设置话题群，暂无法转发。", delay=8)
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
                        or uid_key
                    )
                    try:
                        topic = await context.bot.create_forum_topic(
                            chat_id=forum_group_id,
                            name=f"{display_name} ({uid_key})"
                        )
                        topic_id = topic.message_thread_id
                        topics[uid_key] = topic_id
                        save_map()
                    except Exception as e:
                        logger.error(f"创建话题失败: {e}")
                        await reply_and_auto_delete(message, "❌ 创建话题失败，请联系管理员检查子Bot在群内的权限。", delay=10)
                        return

                # 转发到话题（如果话题被删，则自动重建）
                try:
                    await context.bot.forward_message(
                        chat_id=forum_group_id,
                        from_chat_id=chat_id,
                        message_id=message.message_id,
                        message_thread_id=topic_id
                    )
                    await reply_and_auto_delete(message, "✅ 已转交客服处理（话题）", delay=5)
                except BadRequest as e:
                    low = str(e).lower()
                    if ("message thread not found" in low) or ("topic not found" in low):
                        # 话题被删 → 重建后再发
                        try:
                            display_name = (
                                message.from_user.full_name
                                or (f"@{message.from_user.username}" if message.from_user.username else None)
                                or uid_key
                            )
                            topic = await context.bot.create_forum_topic(
                                chat_id=forum_group_id,
                                name=f"{display_name} ({uid_key})"
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
                            await reply_and_auto_delete(message, "✅ 已转交客服处理（话题已重建）", delay=5)
                        except Exception as e2:
                            logger.error(f"重建话题失败: {e2}")
                            await reply_and_auto_delete(message, "❌ 转发失败，重建话题也未成功，请联系管理员。", delay=10)
                    else:
                        logger.error(f"转发到话题失败: {e}")
                        await reply_and_auto_delete(message, "❌ 转发到话题失败，请检查权限。", delay=10)
                return

            # 群里该话题下的消息 -> 回到用户
            if message.chat.id == forum_group_id and getattr(message, "is_topic_message", False):
                topic_id = message.message_thread_id
                # 通过 topic_id 找到用户
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
                return

    except Exception as e:
        logger.error(f"[{bot_username}] 转发错误: {e}")

# ================== 动态管理 Bot（添加/删除/配置） ==================
async def token_listener(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """监听用户输入的 token 或话题群ID"""
    # ----- 等待设置话题群ID -----
    pending_bot_forum = context.user_data.get("waiting_forum_for")
    if pending_bot_forum and update.message and update.message.text:
        bot_username = pending_bot_forum["bot_username"]
        owner_id = str(update.message.chat.id)
        try:
            gid = int(update.message.text.strip())
        except ValueError:
            await reply_and_auto_delete(update.message, "❌ 群ID无效，请输入数字。", delay=8)
            return

        # 写入该 bot 的 forum_group_id
        for b in bots_data.get(owner_id, {}).get("bots", []):
            if b["bot_username"] == bot_username:
                b["forum_group_id"] = gid
                save_bots()
                await update.message.reply_text(f"✅ 已为 @{bot_username} 设置话题群ID：{gid}")
                # 宿主通知
                now = datetime.now().strftime("%Y-%m-%d %H:%M")
                await send_admin_log(f"🛠 用户({owner_id}) 为 @{bot_username} 设置话题群ID为 {gid} · {now}")
                break
        context.user_data.pop("waiting_forum_for", None)
        return

    # ----- 等待添加子Bot Token -----
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

    # 初始化 owner 节点
    bots_data.setdefault(owner_id, {"username": owner_username, "bots": []})

    # 重复检查
    if any(b["token"] == token for b in bots_data[owner_id]["bots"]):
        await reply_and_auto_delete(update.message, "⚠️ 这个 Bot 已经添加过了。", delay=10)
        return

    # 记录 bot（默认直连模式）
    bots_data[owner_id]["bots"].append({
        "token": token,
        "bot_username": bot_username,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "mode": "direct",
        "forum_group_id": None
    })
    save_bots()

    # 启动子 Bot
    new_app = Application.builder().token(token).build()
    new_app.add_handler(CommandHandler("start", subbot_start))
    new_app.add_handler(MessageHandler(filters.ALL, partial(handle_message, owner_id=int(owner_id), bot_username=bot_username)))

    running_apps[bot_username] = new_app
    await new_app.initialize()
    await new_app.start()
    await new_app.updater.start_polling()

    await update.message.reply_text(
        f"✅ 已添加并启动 Bot：@{bot_username}\n\n"
        f"🎯 默认模式：私聊模式\n\n🔬 可在“我的机器人 → 进入Bot → 切换模式\n\n💡 话题模式 必须 设置话题群ID。"
    )

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
        return

    if data == "mybots":
        owner_id = str(query.from_user.id)
        bots = bots_data.get(owner_id, {}).get("bots", [])
        if not bots:
            await reply_and_auto_delete(query.message, "⚠️ 你还没有绑定任何 Bot。", delay=10)
            return

        keyboard = [
            [InlineKeyboardButton(f"@{b['bot_username']}", callback_data=f"info_{b['bot_username']}")]
            for b in bots
        ]
        keyboard.append([InlineKeyboardButton("🔙 返回", callback_data="back_home")])
        await query.message.edit_text("📋 你的 Bot 列表：", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    if data == "back_home":
        await query.message.edit_text("📣 欢迎使用客服机器人管理面板\n👇 请选择操作：", reply_markup=manager_main_menu())
        return

    if data.startswith("info_"):
        bot_username = data.split("_", 1)[1]
        owner_id = str(query.from_user.id)

        bots = bots_data.get(owner_id, {}).get("bots", [])
        target_bot = next((b for b in bots if b["bot_username"] == bot_username), None)
        if not target_bot:
            await reply_and_auto_delete(query.message, "⚠️ 找不到这个 Bot。", delay=10)
            return

        mode_label = "私聊" if target_bot.get("mode", "direct") == "direct" else "话题"
        forum_gid = target_bot.get("forum_group_id")
        info_text = (
            f"🤖 Bot: @{bot_username}\n"
            f"🔑 Token: {target_bot['token'][:10]}... （已隐藏）\n"
            f"👤 绑定用户: @{bots_data[owner_id].get('username', '未知')}\n"
            f"🆔 用户ID: {owner_id}\n"
            f"⏰ 创建时间: {target_bot.get('created_at', '未知')}\n"
            f"📡 当前模式: {mode_label} 模式\n"
            f"🏷 群ID: {forum_gid if forum_gid else '未设置'}"
        )

        keyboard = [
            [InlineKeyboardButton("🛠 话题群ID", callback_data=f"setforum_{bot_username}")],
            [InlineKeyboardButton("🔁 私聊模式", callback_data=f"mode_direct_{bot_username}")],
            [InlineKeyboardButton("🔁 话题模式", callback_data=f"mode_forum_{bot_username}")],
            [InlineKeyboardButton("❌ 断开连接", callback_data=f"del_{bot_username}")],
            [InlineKeyboardButton("🔙 返回", callback_data="mybots")]
        ]
        await query.message.edit_text(info_text, reply_markup=InlineKeyboardMarkup(keyboard))
        return

    if data.startswith("mode_direct_") or data.startswith("mode_forum_"):
        owner_id = str(query.from_user.id)
        _, mode, bot_username = data.split("_", 2)  # mode is 'direct' or 'forum'
        bots = bots_data.get(owner_id, {}).get("bots", [])
        target_bot = next((b for b in bots if b["bot_username"] == bot_username), None)
        if not target_bot:
            await reply_and_auto_delete(query.message, "⚠️ 找不到这个 Bot。", delay=10)
            return

        # ✅ 如果切换到话题模式但未设置群ID，直接拦截
        if mode == "forum" and not target_bot.get("forum_group_id"):
            await reply_and_auto_delete(
                query.message,
                "⚠️ 请先“🛠 设置 话题群ID”。",
                delay=10
            )
            return

        target_bot["mode"] = mode
        save_bots()

        # 显示中文标签 & 推送到 ADMIN_CHANNEL
        mode_cn_full = "私聊模式" if mode == "direct" else "话题模式"
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        await send_admin_log(f"📡 用户({owner_id}) 将 @{bot_username} 切换为 {mode_cn_full} · {now}")

        await query.message.reply_text(f"✅ 已将 @{bot_username} 切换为 {mode_cn_full.split('模式')[0]} 模式。")


    if data.startswith("setforum_"):
        bot_username = data.split("_", 1)[1]
        context.user_data["waiting_forum_for"] = {"bot_username": bot_username}
        await query.message.reply_text(f"💣 请先将 Bot 拉入话题群，给管理员权限\n\n㊙️ 请输入话题群 ID（给 @{bot_username} 使用）：")
        return

    if data.startswith("del_"):
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
        return

# ================== 主入口 ==================
async def run_all_bots():
    if not MANAGER_TOKEN:
        logger.error("MANAGER_TOKEN 未设置，无法启动管理Bot。")
        return

    load_bots()
    load_map()

    # 启动子 bot（恢复）
    for owner_id, info in bots_data.items():
        for b in info.get("bots", []):
            token = b["token"]; bot_username = b["bot_username"]
            try:
                app = Application.builder().token(token).build()
                app.add_handler(CommandHandler("start", subbot_start))
                app.add_handler(MessageHandler(filters.ALL, partial(handle_message, owner_id=int(owner_id), bot_username=bot_username)))
                running_apps[bot_username] = app
                await app.initialize(); await app.start(); await app.updater.start_polling()
                logger.info(f"启动子Bot: @{bot_username}")
            except Exception as e:
                logger.error(f"子Bot启动失败: @{bot_username} {e}")

    # 管理 Bot
    manager_app = Application.builder().token(MANAGER_TOKEN).build()
    manager_app.add_handler(CommandHandler("start", manager_start))
    manager_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, token_listener))
    manager_app.add_handler(CallbackQueryHandler(callback_handler))
    running_apps["__manager__"] = manager_app

    await manager_app.initialize(); await manager_app.start(); await manager_app.updater.start_polling()
    logger.info("管理 Bot 已启动 ✅")
    if ADMIN_CHANNEL:
        try:
            await manager_app.bot.send_message(ADMIN_CHANNEL, "✅ 宿主管理Bot已启动")
        except Exception as e:
            logger.error(f"启动通知失败: {e}")

    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(run_all_bots())
