#!/usr/bin/env python3
"""
验证用户管理脚本
用于查看、清空、移除已验证用户
"""
import json
import os
import sys

VERIFIED_FILE = "verified_users.json"

def load_verified():
    if not os.path.exists(VERIFIED_FILE):
        return {}
    with open(VERIFIED_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_verified(data):
    with open(VERIFIED_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def list_verified():
    """列出所有已验证用户"""
    data = load_verified()
    if not data:
        print("✅ 没有已验证用户")
        return
    
    print("📋 已验证用户列表：\n")
    total = 0
    for bot_username, user_ids in data.items():
        print(f"🤖 Bot: @{bot_username}")
        print(f"   已验证用户数: {len(user_ids)}")
        for uid in user_ids:
            print(f"   - 用户ID: {uid}")
            total += 1
        print()
    
    print(f"📊 总计: {total} 个已验证用户")

def remove_user(bot_username, user_id):
    """移除指定用户的验证"""
    data = load_verified()
    
    if bot_username not in data:
        print(f"❌ Bot @{bot_username} 不存在")
        return
    
    if user_id not in data[bot_username]:
        print(f"❌ 用户 {user_id} 未验证")
        return
    
    data[bot_username].remove(user_id)
    save_verified(data)
    print(f"✅ 已取消用户 {user_id} 在 @{bot_username} 的验证")

def clear_all():
    """清空所有验证记录"""
    answer = input("⚠️  确定要清空所有验证记录吗？(yes/no): ")
    if answer.lower() == 'yes':
        save_verified({})
        print("✅ 已清空所有验证记录")
    else:
        print("❌ 操作已取消")

def clear_bot(bot_username):
    """清空指定Bot的验证记录"""
    data = load_verified()
    
    if bot_username not in data:
        print(f"❌ Bot @{bot_username} 不存在")
        return
    
    count = len(data[bot_username])
    answer = input(f"⚠️  确定要清空 @{bot_username} 的 {count} 个验证记录吗？(yes/no): ")
    if answer.lower() == 'yes':
        data[bot_username] = []
        save_verified(data)
        print(f"✅ 已清空 @{bot_username} 的验证记录")
    else:
        print("❌ 操作已取消")

def show_help():
    """显示帮助信息"""
    print("""
📖 验证用户管理工具

用法:
  python3 manage_verified.py [命令] [参数]

命令:
  list                          列出所有已验证用户
  remove <bot_username> <uid>   移除指定用户的验证
  clear <bot_username>          清空指定Bot的所有验证
  clear-all                     清空所有验证记录
  help                          显示此帮助信息

示例:
  python3 manage_verified.py list
  python3 manage_verified.py remove mybot 123456789
  python3 manage_verified.py clear mybot
  python3 manage_verified.py clear-all
    """)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        show_help()
        sys.exit(0)
    
    command = sys.argv[1]
    
    if command == "list":
        list_verified()
    
    elif command == "remove":
        if len(sys.argv) != 4:
            print("❌ 用法: python3 manage_verified.py remove <bot_username> <user_id>")
            sys.exit(1)
        bot_username = sys.argv[2]
        try:
            user_id = int(sys.argv[3])
            remove_user(bot_username, user_id)
        except ValueError:
            print("❌ 用户ID必须是数字")
    
    elif command == "clear":
        if len(sys.argv) != 3:
            print("❌ 用法: python3 manage_verified.py clear <bot_username>")
            sys.exit(1)
        clear_bot(sys.argv[2])
    
    elif command == "clear-all":
        clear_all()
    
    elif command == "help":
        show_help()
    
    else:
        print(f"❌ 未知命令: {command}")
        show_help()
        sys.exit(1)
