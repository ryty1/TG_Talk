#!/opt/tg_multi_bot/venv/bin/python
import os
import json
import logging
import asyncio
import random
import string
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
BLACKLIST_FILE = "blacklist.json"  # 新增：黑名单文件
VERIFIED_FILE = "verified_users.json"  # 新增：已验证用户文件
ADMIN_CHANNEL = os.environ.get("ADMIN_CHANNEL")      # 宿主通知群/频道（可选）
MANAGER_TOKEN = os.environ.get("MANAGER_TOKEN")      # 管理机器人 Token（必须）

bots_data = {}
msg_map = {}
blacklist = {}  # 新增：黑名单数据 {"bot_username": [user_id1, user_id2, ...]}
verified_users = {}  # 新增：已验证用户 {"bot_username": [user_id1, user_id2, ...]}
pending_verifications = {}  # 新增：待验证用户 {"bot_username_user_id": "验证码"}
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

# 新增：黑名单管理
def load_blacklist():
    global blacklist
    if os.path.exists(BLACKLIST_FILE):
        with open(BLACKLIST_FILE, "r", encoding="utf-8") as f:
            blacklist = json.load(f)
    else:
        blacklist = {}

def save_blacklist():
    with open(BLACKLIST_FILE, "w", encoding="utf-8") as f:
        json.dump(blacklist, f, ensure_ascii=False, indent=2)

# 新增：验证用户管理
def load_verified_users():
    global verified_users
    if os.path.exists(VERIFIED_FILE):
        with open(VERIFIED_FILE, "r", encoding="utf-8") as f:
            verified_users = json.load(f)
    else:
        verified_users = {}

def save_verified_users():
    with open(VERIFIED_FILE, "w", encoding="utf-8") as f:
        json.dump(verified_users, f, ensure_ascii=False, indent=2)

def is_verified(bot_username: str, user_id: int) -> bool:
    """检查用户是否已验证"""
    return user_id in verified_users.get(bot_username, [])

def add_verified_user(bot_username: str, user_id: int):
    """添加已验证用户"""
    if bot_username not in verified_users:
        verified_users[bot_username] = []
    if user_id not in verified_users[bot_username]:
        verified_users[bot_username].append(user_id)
        save_verified_users()

def remove_verified_user(bot_username: str, user_id: int):
    """取消用户验证"""
    if bot_username in verified_users and user_id in verified_users[bot_username]:
        verified_users[bot_username].remove(user_id)
        save_verified_users()
        return True
    return False

def generate_captcha() -> dict:
    """生成复杂验证码（多种类型）- 完全免费"""
    captcha_type = random.choice(['math', 'sequence', 'chinese', 'logic', 'time'])
    
    if captcha_type == 'math':
        # 数学运算验证码（升级版：支持多步运算）
        style = random.choice(['simple', 'complex'])
        if style == 'simple':
            operators = ['+', '-', '*']
            op = random.choice(operators)
            if op == '+':
                a, b = random.randint(10, 99), random.randint(10, 99)
                answer = str(a + b)
                question = f"{a} + {b} = ?"
            elif op == '-':
                a, b = random.randint(50, 99), random.randint(10, 49)
                answer = str(a - b)
                question = f"{a} - {b} = ?"
            else:  # *
                a, b = random.randint(2, 12), random.randint(2, 12)
                answer = str(a * b)
                question = f"{a} × {b} = ?"
        else:  # complex - 两步运算
            a, b, c = random.randint(5, 20), random.randint(2, 10), random.randint(2, 10)
            ops = random.choice([
                ('+', '*'),  # 先乘后加
                ('-', '+'),  # 混合
            ])
            if ops == ('+', '*'):
                answer = str(a + b * c)
                question = f"{a} + {b} × {c} = ?"
            else:
                answer = str(a - b + c)
                question = f"{a} - {b} + {c} = ?"
        
        return {
            'type': 'math',
            'question': question,
            'answer': answer
        }
    
    elif captcha_type == 'sequence':
        # 数字序列验证码（找规律）
        patterns = [
            # 等差数列
            lambda: {
                'nums': (start := random.randint(1, 10), d := random.randint(2, 5)),
                'seq': [start + i*d for i in range(4)],
                'answer': str(start + 4*d)
            },
            # 等比数列
            lambda: {
                'nums': (start := random.randint(2, 5), r := random.randint(2, 3)),
                'seq': [start * (r**i) for i in range(4)],
                'answer': str(start * (r**4))
            },
            # 平方数列
            lambda: {
                'nums': (start := random.randint(1, 5),),
                'seq': [(start + i)**2 for i in range(4)],
                'answer': str((start + 4)**2)
            }
        ]
        pattern = random.choice(patterns)()
        question = f"找规律填空：{', '.join(map(str, pattern['seq']))}, ?"
        
        return {
            'type': 'sequence',
            'question': question,
            'answer': pattern['answer']
        }
    
    elif captcha_type == 'chinese':
        # 中文数字验证码（防机器人效果极佳）
        chinese_nums = ['零', '一', '二', '三', '四', '五', '六', '七', '八', '九']
        num = random.randint(10, 99)
        # 修复：先判断是否为10-19，避免重复赋值
        if num // 10 == 1:
            chinese_form = '十' + (chinese_nums[num % 10] if num % 10 != 0 else '')
        else:
            chinese_form = chinese_nums[num // 10] + '十' + (chinese_nums[num % 10] if num % 10 != 0 else '')
        
        return {
            'type': 'chinese',
            'question': f"请将中文数字转为阿拉伯数字",
            'answer': str(num),
            'display': chinese_form
        }
    
    elif captcha_type == 'logic':
        # 逻辑推理验证码
        logic_puzzles = [
            # 年龄问题
            {
                'question': lambda: (
                    age := random.randint(8, 15),
                    f"小明今年{age}岁，5年后他多少岁？"
                )[1],
                'answer': lambda age=random.randint(8, 15): str(age + 5)
            },
            # 时间问题
            {
                'question': lambda: (
                    hours := random.randint(2, 5),
                    f"现在是上午10点，{hours}小时后是几点？（只填数字，如：15）"
                )[1],
                'answer': lambda hours=random.randint(2, 5): str(10 + hours)
            },
            # 数量问题
            {
                'question': lambda: (
                    apples := random.randint(5, 12),
                    eat := random.randint(2, 4),
                    f"小红有{apples}个苹果，吃了{eat}个，还剩几个？"
                )[1],
                'answer': lambda apples=random.randint(5, 12), eat=random.randint(2, 4): str(apples - eat)
            }
        ]
        
        # 简化逻辑题
        scenarios = [
            (lambda: random.randint(8, 15), lambda age: f"小明今年{age}岁，5年后他多少岁？", lambda age: str(age + 5)),
            (lambda: random.randint(2, 5), lambda h: f"现在是10点，{h}小时后几点？", lambda h: str(10 + h)),
            (lambda: (random.randint(8, 15), random.randint(2, 5)), lambda x: f"有{x[0]}个，吃{x[1]}个，剩几个？", lambda x: str(x[0] - x[1])),
        ]
        
        scenario = random.choice(scenarios)
        value = scenario[0]()
        question = scenario[1](value)
        answer = scenario[2](value)
        
        return {
            'type': 'logic',
            'question': question,
            'answer': answer
        }
    
    else:  # time
        # 时间识别验证码 - 修复版：明确上午/下午/晚上
        minute = random.choice([0, 15, 30, 45])
        
        # 根据时间段选择合适的小时
        period = random.choice(['上午', '下午', '晚上'])
        
        if period == '上午':
            # 上午：6点-11点 (06:00-11:59)
            hour_12 = random.randint(6, 11)
            hour_24 = hour_12
        elif period == '下午':
            # 下午：12点-5点 (12:00-17:59)
            hour_12 = random.choice([12, 1, 2, 3, 4, 5])
            hour_24 = hour_12 if hour_12 == 12 else hour_12 + 12
        else:  # 晚上
            # 晚上：6点-11点 (18:00-23:59)
            hour_12 = random.randint(6, 11)
            hour_24 = hour_12 + 12
        
        # 中文数字（1-12对应的中文）
        hour_cn_map = {
            1: '一', 2: '二', 3: '三', 4: '四', 5: '五', 6: '六',
            7: '七', 8: '八', 9: '九', 10: '十', 11: '十一', 12: '十二'
        }
        hour_cn = hour_cn_map[hour_12]
        
        # 中文表达时间
        time_str = f"{period}{hour_cn}点"
        if minute == 15:
            time_str += "一刻"
        elif minute == 30:
            time_str += "半"
        elif minute == 45:
            time_str += "三刻"
        
        answer = f"{hour_24:02d}:{minute:02d}"
        
        return {
            'type': 'time',
            'question': f"请用24小时制表示（格式：HH:MM）",
            'answer': answer,
            'display': time_str
        }

def is_blacklisted(bot_username: str, user_id: int) -> bool:
    """检查用户是否在黑名单中"""
    return user_id in blacklist.get(bot_username, [])

def add_to_blacklist(bot_username: str, user_id: int):
    """添加用户到黑名单"""
    if bot_username not in blacklist:
        blacklist[bot_username] = []
    if user_id not in blacklist[bot_username]:
        blacklist[bot_username].append(user_id)
        save_blacklist()
        return True
    return False

def remove_from_blacklist(bot_username: str, user_id: int):
    """从黑名单移除用户"""
    if bot_username in blacklist and user_id in blacklist[bot_username]:
        blacklist[bot_username].remove(user_id)
        save_blacklist()
        return True
    return False

def ensure_bot_map(bot_username: str):
    """保证 msg_map 结构存在"""
    if bot_username not in msg_map or not isinstance(msg_map[bot_username], dict):
        msg_map[bot_username] = {}
    # 直连：主人的被转发消息 msg_id -> 用户ID
    msg_map[bot_username].setdefault("direct", {})
    # 话题：用户ID(str) -> topic_id(int)
    msg_map[bot_username].setdefault("topics", {})
    # 用户消息ID -> 转发后的消息ID (用于编辑消息)
    msg_map[bot_username].setdefault("user_to_forward", {})
    # 转发消息ID -> 用户消息ID (用于反向查找)
    msg_map[bot_username].setdefault("forward_to_user", {})
    # 主人消息ID -> 发送给用户的消息ID (用于编辑主人发送的消息)
    msg_map[bot_username].setdefault("owner_to_user", {})

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
            await app.bot.send_message(chat_id=ADMIN_CHANNEL, text=text, parse_mode="HTML")
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
    """子机器人的 /start 命令，发送验证码或欢迎消息"""
    user_id = update.message.from_user.id
    bot_username = context.bot.username
    
    # 如果用户已验证，显示欢迎信息
    if is_verified(bot_username, user_id):
        await update.message.reply_text(
            "👋 欢迎回来！\n\n"
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
    else:
        # 生成验证码并发送
        captcha_data = generate_captcha()
        verification_key = f"{bot_username}_{user_id}"
        pending_verifications[verification_key] = captcha_data['answer']
        
        # 根据验证码类型构建消息
        captcha_type = captcha_data['type']
        
        if captcha_type == 'math':
            message_text = (
                f"🔐 数学验证\n\n"
                f"欢迎使用本机器人！\n"
                f"为防止滥用，首次使用需要验证。\n\n"
                f"📝 请计算：<b>{captcha_data['question']}</b>\n\n"
                f"💡 提示：请输入计算结果（纯数字）"
            )
        elif captcha_type == 'sequence':
            message_text = (
                f"🔐 逻辑验证\n\n"
                f"欢迎使用本机器人！\n"
                f"为防止滥用，首次使用需要验证。\n\n"
                f"📝 {captcha_data['question']}\n\n"
                f"💡 提示：观察规律，填入下一个数字"
            )
        elif captcha_type == 'chinese':
            message_text = (
                f"🔐 中文数字验证\n\n"
                f"欢迎使用本机器人！\n"
                f"为防止滥用，首次使用需要验证。\n\n"
                f"📝 中文数字：<b>{captcha_data['display']}</b>\n\n"
                f"💡 {captcha_data['question']}"
            )
        elif captcha_type == 'logic':
            message_text = (
                f"🔐 智力验证\n\n"
                f"欢迎使用本机器人！\n"
                f"为防止滥用，首次使用需要验证。\n\n"
                f"📝 {captcha_data['question']}\n\n"
                f"💡 提示：简单的逻辑题，输入数字答案"
            )
        elif captcha_type == 'time':
            message_text = (
                f"🔐 时间验证\n\n"
                f"欢迎使用本机器人！\n"
                f"为防止滥用，首次使用需要验证。\n\n"
                f"📝 时间：<b>{captcha_data['display']}</b>\n\n"
                f"💡 {captcha_data['question']}"
            )
        else:
            message_text = (
                f"🔐 验证\n\n"
                f"欢迎使用本机器人！\n"
                f"为防止滥用，首次使用需要验证。\n\n"
                f"📝 {captcha_data['question']}\n\n"
                f"💡 提示：请输入答案"
            )
        
        await update.message.reply_text(message_text, parse_mode="HTML")

# ================== 消息转发逻辑（直连/话题 可切换） ==================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE, owner_id: int, bot_username: str):
    """
    - 直连模式(direct):
      用户私聊 -> 转发到 owner 私聊；owner 在私聊里"回复该条转发" -> 回到对应用户
    - 话题模式(forum):
      用户私聊 -> 转发到话题群"用户专属话题"；群里该话题下的消息 -> 回到对应用户
    - /id 功能:
      只有 owner 可以用，显示目标用户信息
    - /block 功能:
      拉黑用户
    - /unblock 功能:
      解除拉黑
    - /blocklist 功能:
      查看黑名单
    """
    try:
        # 支持编辑消息
        message = update.edited_message or update.message
        if not message:
            return
        
        is_edit = update.edited_message is not None
        chat_id = message.chat.id

        # 找到该子机器人的配置
        bot_cfg = get_bot_cfg(owner_id, bot_username)
        if not bot_cfg:
            logger.warning(f"找不到 bot 配置: @{bot_username} for owner {owner_id}")
            return

        mode = bot_cfg.get("mode", "direct")
        forum_group_id = bot_cfg.get("forum_group_id")

        ensure_bot_map(bot_username)

        # ---------- /bl (blocklist) 功能 ----------
        cmd = message.text.strip() if message.text else ""
        if cmd and (cmd == "/bl" or cmd.startswith("/bl ") or cmd.startswith("/bl@") or 
                    cmd == "/blocklist" or cmd.startswith("/blocklist ") or cmd.startswith("/blocklist@")):
            if message.from_user.id != owner_id:
                return

            blocked_users = blacklist.get(bot_username, [])
            if not blocked_users:
                await message.reply_text("📋 黑名单为空")
                return

            text = f"📋 黑名单列表 (@{bot_username})：\n\n"
            for idx, uid in enumerate(blocked_users, 1):
                try:
                    user = await context.bot.get_chat(uid)
                    name = user.full_name or f"@{user.username}" if user.username else "匿名用户"
                    text += f"{idx}. {name} (ID: <code>{uid}</code>)\n"
                except:
                    text += f"{idx}. 用户ID: <code>{uid}</code> (已删除账号)\n"

            await message.reply_text(text, parse_mode="HTML")
            return

        # ---------- /b (block) 功能（拉黑用户）----------
        if cmd and (cmd == "/b" or cmd.startswith("/b ") or cmd.startswith("/b@") or 
                    cmd == "/block" or cmd.startswith("/block ") or cmd.startswith("/block@")):
            if message.from_user.id != owner_id:
                return

            target_user = None

            # 方式1：直接输入 TG ID（如：/b 123456789）
            parts = cmd.split()
            if len(parts) == 2 and parts[1].isdigit():
                target_user = int(parts[1])
            
            # 方式2：回复消息
            elif message.reply_to_message:
                # 直连模式：主人私聊里，回复转发消息
                if mode == "direct" and message.chat.type == "private" and chat_id == owner_id:
                    direct_map = msg_map[bot_username]["direct"]
                    target_user = direct_map.get(str(message.reply_to_message.message_id))

                # 话题模式：群里，回复话题消息
                elif mode == "forum" and message.chat.id == forum_group_id:
                    topic_id = message.reply_to_message.message_thread_id
                    for uid_str, t_id in msg_map[bot_username]["topics"].items():
                        if t_id == topic_id:
                            target_user = int(uid_str)
                            break

            if target_user:
                if add_to_blacklist(bot_username, target_user):
                    await message.reply_text(f"🚫 已将用户 {target_user} 加入黑名单")
                    
                    # 通知到管理频道 - 获取用户信息
                    now = datetime.now().strftime("%Y-%m-%d %H:%M")
                    try:
                        user = await context.bot.get_chat(target_user)
                        user_username = user.username
                        user_name = user.full_name or "匿名用户"
                        # 优先使用 @用户名
                        if user_username:
                            user_display = f"@{user_username}"
                        else:
                            user_display = f"<a href='tg://user?id={target_user}'>{user_name}</a>"
                        log_text = f"🚫 Bot @{bot_username} 拉黑用户 {user_display} (ID: <code>{target_user}</code>) · {now}"
                    except:
                        # 如果获取失败，仅显示ID
                        log_text = f"🚫 Bot @{bot_username} 拉黑用户 ID: <code>{target_user}</code> · {now}"
                    await send_admin_log(log_text)
                else:
                    await message.reply_text(f"⚠️ 用户 {target_user} 已在黑名单中")
            else:
                await message.reply_text("⚠️ 请回复用户消息或输入：/b <TG_ID>")

            return

        # ---------- /ub (unblock) 功能（解除拉黑）----------
        if cmd and (cmd == "/ub" or cmd.startswith("/ub ") or cmd.startswith("/ub@") or 
                    cmd == "/unblock" or cmd.startswith("/unblock ") or cmd.startswith("/unblock@")):
            if message.from_user.id != owner_id:
                return

            target_user = None

            # 方式1：直接输入 TG ID（如：/ub 123456789）
            parts = cmd.split()
            if len(parts) == 2 and parts[1].isdigit():
                target_user = int(parts[1])
            
            # 方式2：回复消息
            elif message.reply_to_message:
                # 直连模式
                if mode == "direct" and message.chat.type == "private" and chat_id == owner_id:
                    direct_map = msg_map[bot_username]["direct"]
                    target_user = direct_map.get(str(message.reply_to_message.message_id))

                # 话题模式
                elif mode == "forum" and message.chat.id == forum_group_id:
                    topic_id = message.reply_to_message.message_thread_id
                    for uid_str, t_id in msg_map[bot_username]["topics"].items():
                        if t_id == topic_id:
                            target_user = int(uid_str)
                            break

            if target_user:
                if remove_from_blacklist(bot_username, target_user):
                    await message.reply_text(f"✅ 已将用户 {target_user} 从黑名单移除")
                    
                    # 通知到管理频道 - 获取用户信息
                    now = datetime.now().strftime("%Y-%m-%d %H:%M")
                    try:
                        user = await context.bot.get_chat(target_user)
                        user_username = user.username
                        user_name = user.full_name or "匿名用户"
                        # 优先使用 @用户名
                        if user_username:
                            user_display = f"@{user_username}"
                        else:
                            user_display = f"<a href='tg://user?id={target_user}'>{user_name}</a>"
                        log_text = f"✅ Bot @{bot_username} 解除拉黑用户 {user_display} (ID: <code>{target_user}</code>) · {now}"
                    except:
                        # 如果获取失败，仅显示ID
                        log_text = f"✅ Bot @{bot_username} 解除拉黑用户 ID: <code>{target_user}</code> · {now}"
                    await send_admin_log(log_text)
                else:
                    await message.reply_text(f"⚠️ 用户 {target_user} 不在黑名单中")
            else:
                await message.reply_text("⚠️ 请回复用户消息或输入：/ub <TG_ID>")

            return

        # ---------- /unverify 功能（取消用户验证）----------
        if cmd and (cmd == "/uv" or cmd.startswith("/uv ") or cmd.startswith("/uv@") or 
                    cmd == "/unverify" or cmd.startswith("/unverify ") or cmd.startswith("/unverify@")):
            if message.from_user.id != owner_id:
                return

            target_user = None

            # 方式1：直接输入 TG ID（如：/uv 123456789）
            parts = cmd.split()
            if len(parts) == 2 and parts[1].isdigit():
                target_user = int(parts[1])
            
            # 方式2：回复消息
            elif message.reply_to_message:
                # 直连模式
                if mode == "direct" and message.chat.type == "private" and chat_id == owner_id:
                    direct_map = msg_map[bot_username]["direct"]
                    target_user = direct_map.get(str(message.reply_to_message.message_id))

                # 话题模式
                elif mode == "forum" and message.chat.id == forum_group_id:
                    topic_id = message.reply_to_message.message_thread_id
                    for uid_str, t_id in msg_map[bot_username]["topics"].items():
                        if t_id == topic_id:
                            target_user = int(uid_str)
                            break

            if target_user:
                if remove_verified_user(bot_username, target_user):
                    await message.reply_text(f"🔓 已取消用户 {target_user} 的验证\n下次发送消息时需要重新验证")
                    
                    # 通知到管理频道 - 获取用户信息
                    now = datetime.now().strftime("%Y-%m-%d %H:%M")
                    try:
                        user = await context.bot.get_chat(target_user)
                        user_username = user.username
                        user_name = user.full_name or "匿名用户"
                        # 优先使用 @用户名
                        if user_username:
                            user_display = f"@{user_username}"
                        else:
                            user_display = f"<a href='tg://user?id={target_user}'>{user_name}</a>"
                        log_text = f"🔓 Bot @{bot_username} 取消用户 {user_display} (ID: <code>{target_user}</code>) 验证 · {now}"
                    except:
                        # 如果获取失败，仅显示ID
                        log_text = f"🔓 Bot @{bot_username} 取消用户 ID: <code>{target_user}</code> 验证 · {now}"
                    await send_admin_log(log_text)
                else:
                    await message.reply_text(f"⚠️ 用户 {target_user} 未验证或不存在")
            else:
                await message.reply_text("⚠️ 请回复用户消息或输入：/uv <TG_ID>")

            return

        # ---------- /id 功能 ----------
        if message.text and message.text.strip().startswith("/id"):
            # 🚫 如果不是主人发的，忽略
            if message.from_user.id != owner_id:
                return  

            target_user = None

            # 直连模式：主人私聊里，必须回复一条转发消息
            if mode == "direct" and message.chat.type == "private" and chat_id == owner_id and message.reply_to_message:
                direct_map = msg_map[bot_username]["direct"]
                target_user = direct_map.get(str(message.reply_to_message.message_id))

            # 话题模式：群里，必须回复某条消息
            elif mode == "forum" and message.chat.id == forum_group_id and message.reply_to_message:
                topic_id = message.reply_to_message.message_thread_id
                for uid_str, t_id in msg_map[bot_username]["topics"].items():
                    if t_id == topic_id:
                        target_user = int(uid_str)
                        break

            # 如果找到了用户，展示信息；否则静默忽略
            if target_user:
                try:
                    user = await context.bot.get_chat(target_user)
                    is_blocked = is_blacklisted(bot_username, user.id)
                    user_verified = is_verified(bot_username, user.id)
                    
                    # 状态显示
                    status_parts = []
                    if is_blocked:
                        status_parts.append("🚫 已拉黑")
                    else:
                        status_parts.append("✅ 正常")
                    
                    if user_verified:
                        status_parts.append("🔓 已验证")
                    else:
                        status_parts.append("🔒 未验证")
                    
                    text = (
                        f"━━━━━━━━━━━━━━\n"
                        f"👤 <b>User Info</b>\n"
                        f"━━━━━━━━━━━━━━\n"
                        f"🆔 <b>TG_ID:</b> <code>{user.id}</code>\n"
                        f"👤 <b>全   名:</b> {user.first_name} {user.last_name or ''}\n"
                        f"🔗 <b>用户名:</b> @{user.username if user.username else '(无)'}\n"
                        f"🛡 <b>状   态:</b> {' | '.join(status_parts)}\n"
                        f"━━━━━━━━━━━━━━"
                    )

                    # 根据状态显示不同按钮
                    buttons = []
                    
                    # 第一行：拉黑/解除拉黑
                    if is_blocked:
                        buttons.append([InlineKeyboardButton("✅ 解除拉黑", callback_data=f"unblock_{bot_username}_{user.id}")])
                    else:
                        buttons.append([InlineKeyboardButton("🚫 拉黑用户", callback_data=f"block_{bot_username}_{user.id}")])
                    
                    # 第二行：取消验证（仅已验证用户显示）
                    if user_verified:
                        buttons.append([InlineKeyboardButton("🔓 取消验证", callback_data=f"unverify_{bot_username}_{user.id}")])
                    
                    # 第三行：复制UID
                    buttons.append([InlineKeyboardButton("📋 复制 UID", switch_inline_query_current_chat=str(user.id))])
                    
                    keyboard = InlineKeyboardMarkup(buttons)

                    await message.reply_text(
                        text,
                        parse_mode="HTML",
                        disable_web_page_preview=True,
                        reply_markup=keyboard
                    )
                except Exception as e:
                    await message.reply_text(f"❌ 获取用户信息失败: {e}")

            return  # ✅ 不提示、别人也用不了

        # ---------- 验证码检查（普通用户） ----------
        if message.chat.type == "private" and chat_id != owner_id:
            user_id = message.from_user.id
            verification_key = f"{bot_username}_{user_id}"
            
            logger.info(f"[验证检查] Bot: @{bot_username}, 用户: {user_id}, 已验证: {is_verified(bot_username, user_id)}")
            
            # 如果用户未验证
            if not is_verified(bot_username, user_id):
                # 检查是否有待验证的验证码
                if verification_key in pending_verifications:
                    expected_captcha = pending_verifications[verification_key]
                    user_input = message.text.strip() if message.text else ""
                    
                    logger.info(f"[验证码输入] 用户 {user_id} 输入: '{user_input}', 期望: '{expected_captcha}'")
                    
                    # 验证码正确
                    if user_input == expected_captcha:
                        add_verified_user(bot_username, user_id)
                        pending_verifications.pop(verification_key, None)
                        
                        await message.reply_text(
                            "👋 欢迎回来！\n\n"
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
                        
                        # 通知Bot的主人（owner）
                        user_name = message.from_user.full_name or "匿名用户"
                        user_username = message.from_user.username
                        now = datetime.now().strftime("%Y-%m-%d %H:%M")
                        
                        # 构建用户显示：统一风格（多行分开显示）
                        notification_text = f"✅ 新用户验证成功\n\n"
                        notification_text += f"👤 昵称: {user_name}\n"
                        if user_username:
                            notification_text += f"📱 用户名: @{user_username}\n"
                        notification_text += (
                            f"🆔 ID: <code>{user_id}</code>\n"
                            f"🤖 Bot: @{bot_username}\n"
                            f"⏰ {now}"
                        )
                        
                        # 仅发送给Bot的主人
                        try:
                            await context.bot.send_message(
                                chat_id=owner_id,
                                text=notification_text,
                                parse_mode="HTML"
                            )
                        except Exception as e:
                            logger.error(f"通知Bot主人失败: {e}")
                        
                        return
                    else:
                        # 验证码错误 - 不显示正确答案！
                        await reply_and_auto_delete(
                            message, 
                            f"❌ 验证码错误！\n\n请仔细检查后重新输入\n或发送 /start 获取新的验证题", 
                            delay=5
                        )
                        return
                else:
                    # 没有待验证的验证码，生成新的
                    logger.info(f"[生成验证码] 用户 {user_id} 首次发送消息，生成验证码")
                    captcha_data = generate_captcha()
                    pending_verifications[verification_key] = captcha_data['answer']
                    logger.info(f"[验证码] 类型: {captcha_data['type']}, 答案: {captcha_data['answer']}")
                    
                    # 根据验证码类型构建消息
                    retry_captcha_type = captcha_data['type']
                    
                    if retry_captcha_type == 'math':
                        message_text = f"🔐 数学验证\n\n你还未通过验证。\n\n📝 请计算：<b>{captcha_data['question']}</b>\n\n💡 输入计算结果或 /start 换题"
                    elif retry_captcha_type == 'sequence':
                        message_text = f"🔐 逻辑验证\n\n你还未通过验证。\n\n📝 {captcha_data['question']}\n\n💡 观察规律或 /start 换题"
                    elif retry_captcha_type == 'chinese':
                        message_text = f"🔐 中文数字验证\n\n你还未通过验证。\n\n📝 中文数字：<b>{captcha_data['display']}</b>\n\n💡 {captcha_data['question']}或 /start 换题"
                    elif retry_captcha_type == 'logic':
                        message_text = f"🔐 智力验证\n\n你还未通过验证。\n\n📝 {captcha_data['question']}\n\n💡 简单逻辑题或 /start 换题"
                    elif retry_captcha_type == 'time':
                        message_text = f"🔐 时间验证\n\n你还未通过验证。\n\n📝 时间：<b>{captcha_data['display']}</b>\n\n💡 {captcha_data['question']}或 /start 换题"
                    else:
                        message_text = f"🔐 验证\n\n你还未通过验证。\n\n📝 {captcha_data['question']}\n\n💡 请输入答案或 /start 换题"
                    
                    await message.reply_text(message_text, parse_mode="HTML")
                    return

        # ---------- 黑名单拦截 ----------
        if message.chat.type == "private" and chat_id != owner_id:
            if is_blacklisted(bot_username, chat_id):
                # 被拉黑用户发消息，静默忽略或返回提示
                await reply_and_auto_delete(message, "⚠️ 你已被管理员拉黑，消息无法发送。", delay=5)
                logger.info(f"拦截黑名单用户 {chat_id} 的消息 (@{bot_username})")
                return

        # ---------- 直连模式 ----------
        if mode == "direct":
            # 普通用户发私聊 -> 转给主人
            if message.chat.type == "private" and chat_id != owner_id:
                user_msg_key = f"{chat_id}_{message.message_id}"
                
                if is_edit:
                    # 如果是编辑消息，尝试编辑之前发送的消息
                    forward_msg_id = msg_map[bot_username]["user_to_forward"].get(user_msg_key)
                    if forward_msg_id:
                        try:
                            # 编辑消息 (只能编辑文本)
                            if message.text:
                                # 获取用户名
                                username = f"@{message.from_user.username}" if message.from_user.username else ""
                                display_name = message.from_user.full_name or '未知'
                                user_header = f"👤 {display_name} ({username})" if username else f"👤 {display_name}"
                                
                                await context.bot.edit_message_text(
                                    chat_id=owner_id,
                                    message_id=forward_msg_id,
                                    text=f"{user_header}\n\n{message.text} [✏️已编辑]"
                                )
                                logger.info(f"用户 {chat_id} 编辑消息成功")
                            else:
                                # 如果不是文本消息，无法直接编辑，发送新消息提示
                                await context.bot.send_message(
                                    chat_id=owner_id,
                                    text=f"✏️ 用户 {message.from_user.full_name or '未知'} (ID: {chat_id}) 编辑了消息\n(非文本消息无法同步编辑)"
                                )
                        except Exception as e:
                            logger.error(f"编辑消息失败: {e}")
                            # 如果编辑失败，发送提示
                            await context.bot.send_message(
                                chat_id=owner_id,
                                text=f"✏️ 用户 {message.from_user.full_name or '未知'} (ID: {chat_id}) 编辑了消息，但无法同步编辑"
                            )
                        return
                else:
                    # 新消息 - 发送文本消息而不是转发(这样可以编辑)
                    # 获取用户名
                    username = f"@{message.from_user.username}" if message.from_user.username else ""
                    display_name = message.from_user.full_name or '未知'
                    user_header = f"👤 {display_name} ({username})" if username else f"👤 {display_name}"
                    
                    if message.text:
                        # 文本消息：发送可编辑的消息
                        sent_msg = await context.bot.send_message(
                            chat_id=owner_id,
                            text=f"{user_header}\n\n{message.text}"
                        )
                        msg_map[bot_username]["direct"][str(sent_msg.message_id)] = chat_id
                        msg_map[bot_username]["user_to_forward"][user_msg_key] = sent_msg.message_id
                        msg_map[bot_username]["forward_to_user"][str(sent_msg.message_id)] = user_msg_key
                        save_map()
                    else:
                        # 非文本消息：先发送用户信息，再转发原消息
                        await context.bot.send_message(
                            chat_id=owner_id,
                            text=user_header
                        )
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
                    owner_msg_key = f"{owner_id}_{message.message_id}"
                    
                    if is_edit:
                        # 主人编辑了回复，尝试编辑发送给用户的消息
                        user_msg_id = msg_map[bot_username]["owner_to_user"].get(owner_msg_key)
                        if user_msg_id:
                            try:
                                if message.text:
                                    await context.bot.edit_message_text(
                                        chat_id=target_user,
                                        message_id=user_msg_id,
                                        text=message.text
                                    )
                                    logger.info(f"主人编辑回复成功")
                                else:
                                    await reply_and_auto_delete(message, "⚠️ 非文本消息无法编辑", delay=3)
                            except Exception as e:
                                logger.error(f"编辑回复失败: {e}")
                                await reply_and_auto_delete(message, f"⚠️ 编辑失败: {e}", delay=5)
                        return
                    else:
                        # 新回复
                        sent_msg = await context.bot.copy_message(
                            chat_id=target_user,
                            from_chat_id=owner_id,
                            message_id=message.message_id
                        )
                        # 保存映射关系
                        msg_map[bot_username]["owner_to_user"][owner_msg_key] = sent_msg.message_id
                        save_map()
                        await reply_and_auto_delete(message, "✅ 回复已送达", delay=2)
                else:
                    if not is_edit:
                        await reply_and_auto_delete(message, "⚠️ 找不到对应的用户映射。", delay=5)
                return

        # ---------- 话题模式 ----------
        elif mode == "forum":
            logger.info(f"[话题模式] Bot: @{bot_username}, forum_group_id: {forum_group_id}")
            
            if not forum_group_id:
                logger.warning(f"[话题模式] 未设置群ID，无法转发")
                if message.chat.type == "private" and chat_id != owner_id:
                    await reply_and_auto_delete(message, "⚠️ 主人未设置话题群，暂无法转发。", delay=5)
                return

            topics = msg_map[bot_username]["topics"]

            # 普通用户发私聊 -> 转到对应话题
            if message.chat.type == "private" and chat_id != owner_id:
                logger.info(f"[话题模式] 收到用户 {chat_id} 的私聊消息，准备转发到群 {forum_group_id}")
                uid_key = str(chat_id)
                topic_id = topics.get(uid_key)
                user_msg_key = f"{chat_id}_{message.message_id}"

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
                    if is_edit:
                        # 如果是编辑消息，尝试编辑之前发送的消息
                        forward_msg_id = msg_map[bot_username]["user_to_forward"].get(user_msg_key)
                        if forward_msg_id:
                            try:
                                if message.text:
                                    # 话题模式：不显示用户信息(话题名称已经是用户名)
                                    await context.bot.edit_message_text(
                                        chat_id=forum_group_id,
                                        message_id=forward_msg_id,
                                        text=f"{message.text} [✏️已编辑]"
                                    )
                                    logger.info(f"[话题模式] 用户 {chat_id} 编辑消息成功")
                                else:
                                    # 非文本消息无法编辑
                                    await context.bot.send_message(
                                        chat_id=forum_group_id,
                                        message_thread_id=topic_id,
                                        text=f"✏️ 用户编辑了消息 (非文本消息无法同步编辑)"
                                    )
                            except Exception as e:
                                logger.error(f"[话题模式] 编辑消息失败: {e}")
                                # 编辑失败，发送提示
                                await context.bot.send_message(
                                    chat_id=forum_group_id,
                                    message_thread_id=topic_id,
                                    text="✏️ 用户编辑了消息，但无法同步编辑"
                                )
                        return
                    else:
                        # 新消息
                        logger.info(f"[话题模式] 转发消息到话题 {topic_id}")
                        
                        if message.text:
                            # 文本消息：发送可编辑的消息(话题模式不显示用户信息)
                            sent_msg = await context.bot.send_message(
                                chat_id=forum_group_id,
                                message_thread_id=topic_id,
                                text=message.text
                            )
                            # 保存映射关系
                            msg_map[bot_username]["user_to_forward"][user_msg_key] = sent_msg.message_id
                            msg_map[bot_username]["forward_to_user"][str(sent_msg.message_id)] = user_msg_key
                            save_map()
                        else:
                            # 非文本消息：直接转发(话题模式)
                            await context.bot.forward_message(
                                chat_id=forum_group_id,
                                from_chat_id=chat_id,
                                message_id=message.message_id,
                                message_thread_id=topic_id
                            )
                        
                        logger.info(f"[话题模式] 转发成功")
                        await reply_and_auto_delete(message, "✅ 已转交客服处理", delay=2)

                except BadRequest as e:
                    low = str(e).lower()
                    if ("message thread not found" in low) or ("topic not found" in low):
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
                return

            # 群里该话题下的消息 -> 回到用户
            if message.chat.id == forum_group_id and getattr(message, "is_topic_message", False):
                topic_id = message.message_thread_id
                logger.info(f"[话题模式] 收到群消息，topic_id: {topic_id}, 查找对应用户")
                target_uid = None
                for uid_str, t_id in topics.items():
                    if t_id == topic_id:
                        target_uid = int(uid_str)
                        break
                if target_uid:
                    try:
                        owner_msg_key = f"{forum_group_id}_{message.message_id}"
                        
                        if is_edit:
                            # 主人编辑了消息，尝试编辑发送给用户的消息
                            user_msg_id = msg_map[bot_username]["owner_to_user"].get(owner_msg_key)
                            if user_msg_id:
                                try:
                                    if message.text:
                                        await context.bot.edit_message_text(
                                            chat_id=target_uid,
                                            message_id=user_msg_id,
                                            text=message.text
                                        )
                                        logger.info(f"[话题模式] 主人编辑回复成功")
                                    else:
                                        logger.warning(f"[话题模式] 非文本消息无法编辑")
                                except Exception as e:
                                    logger.error(f"[话题模式] 编辑回复失败: {e}")
                        else:
                            # 新消息
                            logger.info(f"[话题模式] 找到用户 {target_uid}，准备发送")
                            sent_msg = await context.bot.copy_message(
                                chat_id=target_uid,
                                from_chat_id=forum_group_id,
                                message_id=message.message_id
                            )
                            # 保存映射关系
                            msg_map[bot_username]["owner_to_user"][owner_msg_key] = sent_msg.message_id
                            save_map()
                            logger.info(f"[话题模式] 回复发送成功")
                    except Exception as e:
                        logger.error(f"群->用户 复制失败: {e}")
                else:
                    logger.warning(f"[话题模式] 未找到 topic_id {topic_id} 对应的用户")
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
                user_username = update.message.from_user.username
                user_display = f"@{user_username}" if user_username else f"用户ID: {owner_id}"
                await send_admin_log(f"🛠 {user_display} (ID: <code>{owner_id}</code>) 为 @{bot_username} 设置话题群ID为 {gid} · {now}")
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
    # 处理普通消息
    new_app.add_handler(MessageHandler(filters.ALL, partial(handle_message, owner_id=int(owner_id), bot_username=bot_username)))
    # 处理编辑消息
    new_app.add_handler(MessageHandler(filters.UpdateType.EDITED_MESSAGE, partial(handle_message, owner_id=int(owner_id), bot_username=bot_username)))

    running_apps[bot_username] = new_app
    await new_app.initialize()
    await new_app.start()
    await new_app.updater.start_polling()

    await update.message.reply_text(
        f"✅ 已添加并启动 Bot：@{bot_username}\n\n"
        f"🎯 默认模式：私聊模式\n\n"
        f"🔬 可在\"我的机器人 → 进入Bot → 切换模式\"\n\n"
        f"💡 话题模式 必须 设置话题群ID。"
    )

    # 🔔 添加通知（发送到管理频道）
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    # 优先使用 @用户名
    user_display = f"@{owner_username}" if owner_username else f"用户ID: {owner_id}"
    log_text = (
        f"🛒 {user_display}\n"
        f"🆔 <code>{owner_id}</code>\n"
        f"🤖 Bot: @{bot_username}\n"
        f"⏰ {now}"
    )
    await send_admin_log(log_text)

# ================== 菜单回调 ==================
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    await query.answer()

    # 新增：处理拉黑/解除拉黑/取消验证按钮
    if data.startswith("block_") or data.startswith("unblock_") or data.startswith("unverify_"):
        parts = data.split("_")
        action = parts[0]  # "block" or "unblock" or "unverify"
        bot_username = parts[1]
        user_id = int(parts[2])

        if action == "block":
            if add_to_blacklist(bot_username, user_id):
                await query.message.edit_text(f"🚫 已将用户 {user_id} 加入黑名单")
                now = datetime.now().strftime("%Y-%m-%d %H:%M")
                # 获取用户信息
                try:
                    user = await context.bot.get_chat(user_id)
                    user_username = user.username
                    user_name = user.full_name or "匿名用户"
                    # 优先使用 @用户名
                    if user_username:
                        user_display = f"@{user_username}"
                    else:
                        user_display = f"<a href='tg://user?id={user_id}'>{user_name}</a>"
                    log_text = f"🚫 Bot @{bot_username} 拉黑用户 {user_display} (ID: <code>{user_id}</code>) · {now}"
                except:
                    # 如果获取失败，仅显示ID
                    log_text = f"🚫 Bot @{bot_username} 拉黑用户 ID: <code>{user_id}</code> · {now}"
                await send_admin_log(log_text)
            else:
                await query.message.edit_text(f"⚠️ 用户 {user_id} 已在黑名单中")
        elif action == "unblock":
            if remove_from_blacklist(bot_username, user_id):
                await query.message.edit_text(f"✅ 已将用户 {user_id} 从黑名单移除")
                now = datetime.now().strftime("%Y-%m-%d %H:%M")
                # 获取用户信息
                try:
                    user = await context.bot.get_chat(user_id)
                    user_username = user.username
                    user_name = user.full_name or "匿名用户"
                    # 优先使用 @用户名
                    if user_username:
                        user_display = f"@{user_username}"
                    else:
                        user_display = f"<a href='tg://user?id={user_id}'>{user_name}</a>"
                    log_text = f"✅ Bot @{bot_username} 解除拉黑用户 {user_display} (ID: <code>{user_id}</code>) · {now}"
                except:
                    # 如果获取失败，仅显示ID
                    log_text = f"✅ Bot @{bot_username} 解除拉黑用户 ID: <code>{user_id}</code> · {now}"
                await send_admin_log(log_text)
            else:
                await query.message.edit_text(f"⚠️ 用户 {user_id} 不在黑名单中")
        else:  # unverify
            if remove_verified_user(bot_username, user_id):
                await query.message.edit_text(f"🔓 已取消用户 {user_id} 的验证\n下次发送消息时需要重新验证")
                now = datetime.now().strftime("%Y-%m-%d %H:%M")
                # 获取用户信息
                try:
                    user = await context.bot.get_chat(user_id)
                    user_username = user.username
                    user_name = user.full_name or "匿名用户"
                    # 优先使用 @用户名
                    if user_username:
                        user_display = f"@{user_username}"
                    else:
                        user_display = f"<a href='tg://user?id={user_id}'>{user_name}</a>"
                    log_text = f"🔓 Bot @{bot_username} 取消用户 {user_display} (ID: <code>{user_id}</code>) 验证 · {now}"
                except:
                    # 如果获取失败，仅显示ID
                    log_text = f"🔓 Bot @{bot_username} 取消用户 ID: <code>{user_id}</code> 验证 · {now}"
                await send_admin_log(log_text)
            else:
                await query.message.edit_text(f"⚠️ 用户 {user_id} 未验证或不存在")
        return

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
        blocked_count = len(blacklist.get(bot_username, []))
        
        info_text = (
            f"🤖 Bot: @{bot_username}\n"
            f"🔑 Token: {target_bot['token'][:10]}... （已隐藏）\n"
            f"👤 绑定用户: @{bots_data[owner_id].get('username', '未知')}\n"
            f"🆔 用户ID: {owner_id}\n"
            f"⏰ 创建时间: {target_bot.get('created_at', '未知')}\n"
            f"📡 当前模式: {mode_label} 模式\n"
            f"🏷 群ID: {forum_gid if forum_gid else '未设置'}\n"
            f"🚫 黑名单: {blocked_count} 个用户"
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
                "⚠️ 请先\"🛠 设置 话题群ID\"。",
                delay=10
            )
            return

        target_bot["mode"] = mode
        save_bots()

        # 显示中文标签 & 推送到 ADMIN_CHANNEL
        mode_cn_full = "私聊模式" if mode == "direct" else "话题模式"
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        user_username = query.from_user.username
        user_display = f"@{user_username}" if user_username else f"用户ID: {owner_id}"
        await send_admin_log(f"📡 {user_display} (ID: <code>{owner_id}</code>) 将 @{bot_username} 切换为 {mode_cn_full} · {now}")

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

            # 🔔 删除通知（发送到管理频道）
            now = datetime.now().strftime("%Y-%m-%d %H:%M")
            # 优先使用 @用户名
            user_display = f"@{owner_username}" if owner_username else f"用户ID: {owner_id}"
            log_text = (
                f"🗑 {user_display}\n"
                f"🆔 <code>{owner_id}</code>\n"
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
    load_blacklist()  # 新增：加载黑名单
    load_verified_users()  # 新增：加载已验证用户

    # 启动子 bot（恢复）
    for owner_id, info in bots_data.items():
        for b in info.get("bots", []):
            token = b["token"]; bot_username = b["bot_username"]
            try:
                app = Application.builder().token(token).build()
                app.add_handler(CommandHandler("start", subbot_start))
                # 处理普通消息
                app.add_handler(MessageHandler(filters.ALL, partial(handle_message, owner_id=int(owner_id), bot_username=bot_username)))
                # 处理编辑消息 - 使用 filters.UpdateType.EDITED_MESSAGE
                app.add_handler(MessageHandler(filters.UpdateType.EDITED_MESSAGE, partial(handle_message, owner_id=int(owner_id), bot_username=bot_username)))
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
