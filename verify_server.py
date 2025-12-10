#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CF Turnstile 验证服务器
独立的 Flask Web 服务，处理 Cloudflare Turnstile 验证流程
"""
import os
import logging
import requests
from flask import Flask, render_template, request, redirect, url_for
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 导入数据库模块
import database as db

# 配置日志
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Flask app初始化
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your-secret-key-here')

# CF Turnstile 配置
CF_SITE_KEY = os.environ.get('CF_TURNSTILE_SITE_KEY')
CF_SECRET_KEY = os.environ.get('CF_TURNSTILE_SECRET_KEY')
VERIFY_SERVER_URL = os.environ.get('VERIFY_SERVER_URL', 'http://localhost:5000')

# Telegram Bot Token（用于发送通知）
MANAGER_TOKEN = os.environ.get('MANAGER_TOKEN')

if not CF_SITE_KEY or not CF_SECRET_KEY:
    logger.error("❌ 缺少 CF Turnstile 配置！请设置环境变量 CF_TURNSTILE_SITE_KEY 和 CF_TURNSTILE_SECRET_KEY")


@app.route('/verify/<token>', methods=['GET'])
def verify_page(token):
    """显示 CF 验证页面"""
    # 验证令牌是否有效
    token_info = db.get_verification_token(token)
    
    if not token_info:
        return render_template('error.html', 
                             error_message="验证链接无效或已过期",
                             error_detail="请返回 Telegram 重新发送 /start 命令获取新的验证链接"), 400
    
    # 渲染验证页面
    return render_template('verify.html', 
                         site_key=CF_SITE_KEY,
                         token=token,
                         bot_username=token_info['bot_username'])


@app.route('/verify/<token>', methods=['POST'])
def verify_submit(token):
    """处理 CF 验证提交"""
    try:
        # 获取令牌信息
        token_info = db.get_verification_token(token)
        
        if not token_info:
            return render_template('error.html',
                                 error_message="验证链接无效或已过期",
                                 error_detail="请返回 Telegram 重新发送 /start 命令"), 400
        
        # 获取 CF Turnstile 响应
        cf_response = request.form.get('cf-turnstile-response')
        
        if not cf_response:
            return render_template('error.html',
                                 error_message="验证失败",
                                 error_detail="未收到验证响应，请重试"), 400
        
        # 验证 CF Turnstile 响应
        verify_result = verify_turnstile(cf_response, request.remote_addr)
        
        if not verify_result['success']:
            error_codes = verify_result.get('error-codes', ['未知错误'])
            logger.warning(f"CF 验证失败: {error_codes}")
            return render_template('error.html',
                                 error_message="验证失败",
                                 error_detail=f"Cloudflare 验证未通过: {', '.join(error_codes)}"), 400
        
        # 验证成功 - 添加到已验证用户
        bot_username = token_info['bot_username']
        user_id = token_info['user_id']
        user_name = token_info['user_name']
        user_username = token_info['user_username']
        
        db.add_verified_user(bot_username, user_id, user_name, user_username)
        
        # 删除已使用的令牌
        db.delete_verification_token(token)
        
        # 发送欢迎消息给用户 + 通知 Bot 主人
        try:
            from datetime import datetime
            send_welcome_and_notify(bot_username, user_id, user_name, user_username, token_info)
        except Exception as e:
            logger.error(f"发送欢迎消息/通知失败: {e}")
        
        logger.info(f"✅ 用户验证成功: {bot_username} - {user_id} ({user_name})")
        
        # 重定向到成功页面
        return render_template('success.html', 
                             bot_username=bot_username,
                             user_name=user_name)
    
    except Exception as e:
        logger.error(f"验证处理失败: {e}")
        import traceback
        traceback.print_exc()
        return render_template('error.html',
                             error_message="服务器错误",
                             error_detail="验证处理失败，请稍后重试"), 500


def verify_turnstile(response_token: str, remote_ip: str) -> dict:
    """
    验证 Cloudflare Turnstile 响应
    
    Args:
        response_token: CF Turnstile 响应令牌
        remote_ip: 用户 IP 地址
    
    Returns:
        验证结果字典
    """
    verify_url = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
    
    payload = {
        'secret': CF_SECRET_KEY,
        'response': response_token,
        'remoteip': remote_ip
    }
    
    try:
        response = requests.post(verify_url, data=payload, timeout=10)
        result = response.json()
        return result
    except Exception as e:
        logger.error(f"CF Turnstile 验证请求失败: {e}")
        return {'success': False, 'error-codes': ['network-error']}


def send_welcome_and_notify(bot_username: str, user_id: int, user_name: str, user_username: str, token_info: dict = None):
    """发送欢迎消息给用户 + 通知 Bot 主人"""
    from datetime import datetime
    from telegram import Bot
    import asyncio
    
    # 获取 Bot 信息
    bot_info = db.get_bot(bot_username)
    if not bot_info:
        logger.warning(f"未找到 Bot 信息: {bot_username}")
        return
    
    owner_id = bot_info['owner']
    
    # 获取欢迎语
    welcome_msg = bot_info.get('welcome_msg') or db.get_global_welcome() or (
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
    
    # 构建通知消息（给主人）
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    notification_text = f"✅ 新用户验证成功（CF验证）\n\n"
    notification_text += f"👤 昵称: {user_name}\n"
    if user_username:
        notification_text += f"📱 用户名: @{user_username}\n"
    notification_text += (
        f"🆔 ID: <code>{user_id}</code>\n"
        f"🤖 Bot: @{bot_username}\n"
        f"⏰ {now}"
    )
    
    # 发送消息
    try:
        async def send_messages():
            bot = Bot(token=bot_info['token'])
            
            # 1. 删除验证消息（如果有 message_id）
            if token_info.get('message_id'):
                try:
                    await bot.delete_message(
                        chat_id=user_id,
                        message_id=token_info['message_id']
                    )
                    logger.info(f"✅ 已删除验证消息: {token_info['message_id']}")
                except Exception as e:
                    logger.warning(f"删除验证消息失败: {e}")
            
            # 2. 发送欢迎消息给用户
            await bot.send_message(
                chat_id=user_id,
                text=welcome_msg,
                parse_mode="HTML"
            )
            logger.info(f"✅ 已发送欢迎消息给用户: {user_id}")
            
            # 3. 通知 Bot 主人
            await bot.send_message(
                chat_id=owner_id,
                text=notification_text,
                parse_mode="HTML"
            )
            logger.info(f"✅ 已通知 Bot 主人: {owner_id}")
        
        # 运行异步任务
        asyncio.run(send_messages())
    except Exception as e:
        logger.error(f"发送欢迎/通知失败: {e}")
        import traceback
        traceback.print_exc()


@app.route('/health', methods=['GET'])
def health_check():
    """健康检查端点"""
    return {'status': 'ok', 'service': 'CF Verification Server'}, 200


@app.errorhandler(404)
def not_found(error):
    return render_template('error.html',
                         error_message="页面未找到",
                         error_detail="请检查链接是否正确"), 404


@app.errorhandler(500)
def internal_error(error):
    return render_template('error.html',
                         error_message="服务器内部错误",
                         error_detail="请稍后重试或联系管理员"), 500


if __name__ == '__main__':
    # 开发模式
    port = int(os.environ.get('VERIFY_SERVER_PORT', 5000))
    logger.info(f"🚀 CF 验证服务器启动中...")
    logger.info(f"📍 监听端口: {port}")
    logger.info(f"🔗 验证 URL: {VERIFY_SERVER_URL}")
    
    app.run(host='0.0.0.0', port=port, debug=True)
