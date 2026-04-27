#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_APP_DIR="$SCRIPT_DIR"

# 兼容历史部署目录：若当前脚本目录不含项目文件，则回退到 /opt/tg_multi_bot
if [ ! -f "$DEFAULT_APP_DIR/host_bot.py" ] && [ -d "/opt/tg_multi_bot" ]; then
  DEFAULT_APP_DIR="/opt/tg_multi_bot"
fi

APP_DIR="${TG_BOT_APP_DIR:-$DEFAULT_APP_DIR}"
BACKUP_DIR="${TG_BOT_BACKUP_DIR:-$APP_DIR/backup_temp}"
DATE=$(date +%Y-%m-%d_%H-%M-%S)

# 加载环境变量
if [ -f "$APP_DIR/.env" ]; then
  source "$APP_DIR/.env"
fi

# 检查必要的环境变量
if [ -z "$GH_USERNAME" ] || [ -z "$GH_REPO" ] || [ -z "$GH_TOKEN" ]; then
  echo "❌ GitHub 配置缺失，请检查 .env 文件"
  exit 1
fi

# 创建临时备份目录
mkdir -p "$BACKUP_DIR"
cd "$BACKUP_DIR"

# 初始化 Git（如果还没有）
if [ ! -d ".git" ]; then
  git init -b main
  git config user.name "TG Bot Backup"
  git config user.email "backup@bot.local"
  git remote add origin "https://$GH_TOKEN@github.com/$GH_USERNAME/$GH_REPO.git" 2>/dev/null || \
  git remote set-url origin "https://$GH_TOKEN@github.com/$GH_USERNAME/$GH_REPO.git"
fi

# 复制数据库文件
echo "📦 备份数据文件..."
if [ -f "$APP_DIR/bot_data.db" ]; then
  # 使用 SQLite backup API 生成一致性快照（WAL 模式下也安全）
  if python3 - "$APP_DIR/bot_data.db" "$BACKUP_DIR/bot_data.db" <<'PY'
import sqlite3
import sys

src_path = sys.argv[1]
dst_path = sys.argv[2]

src = sqlite3.connect(src_path, timeout=30)
dst = sqlite3.connect(dst_path)
try:
    src.backup(dst)
finally:
    dst.close()
    src.close()
PY
  then
    echo "  ✅ bot_data.db（数据库快照）"
  else
    # 极端场景回退普通复制
    cp -f "$APP_DIR/bot_data.db" . 2>/dev/null && echo "  ⚠️ 使用文件复制方式备份 bot_data.db"
  fi
else
  echo "  ⚠️ 未找到数据库文件 bot_data.db"
fi

# 备份配置文件
echo "⚙️ 备份配置文件..."
cp -f "$APP_DIR/.env" . 2>/dev/null || echo "# Empty" > .env

# 备份脚本文件
echo "📜 备份脚本文件..."
cp -f "$APP_DIR/host_bot.py" . 2>/dev/null && echo "  ✅ host_bot.py"
cp -f "$APP_DIR/database.py" . 2>/dev/null && echo "  ✅ database.py"
cp -f "$APP_DIR/verify_server.py" . 2>/dev/null && echo "  ✅ verify_server.py"

# 备份模板文件
if [ -d "$APP_DIR/templates" ]; then
  cp -r "$APP_DIR/templates" . 2>/dev/null && echo "  ✅ templates/ (目录)"
fi

# 创建备份信息文件
cat <<EOF > backup_info.txt
备份时间: $DATE
服务器: $(hostname)
Python版本: $(python3 --version 2>&1)
备份内容:
  - 数据库文件: bot_data.db
  - 配置文件: .env
  - 脚本文件: host_bot.py, database.py, verify_server.py
  - 模板目录: templates/
EOF

# 提交到 GitHub
git add .
if git diff --cached --quiet; then
  echo "✅ 数据无变化，跳过备份"
  # 只在非静默模式下发送通知
  if [ -z "$SILENT_BACKUP" ] && [ -n "$MANAGER_TOKEN" ] && [ -n "$ADMIN_CHANNEL" ]; then
    curl -s -X POST "https://api.telegram.org/bot$MANAGER_TOKEN/sendMessage" \
      -d chat_id="$ADMIN_CHANNEL" \
      -d text="📦 自动备份提醒%0A%0A⏰ 时间: $DATE%0A📊 状态: 数据无变化%0A📂 仓库: $GH_USERNAME/$GH_REPO" \
      >/dev/null 2>&1
  fi
else
  git commit -m "自动备份 - $DATE" >/dev/null 2>&1
  
  # 强制推送（避免冲突）
  git push -f origin main >/dev/null 2>&1
  
  if [ $? -eq 0 ]; then
    echo "✅ 备份成功推送到 GitHub ($DATE)"
    
    # 只在非静默模式下发送成功通知
    if [ -z "$SILENT_BACKUP" ] && [ -n "$MANAGER_TOKEN" ] && [ -n "$ADMIN_CHANNEL" ]; then
      curl -s -X POST "https://api.telegram.org/bot$MANAGER_TOKEN/sendMessage" \
        -d chat_id="$ADMIN_CHANNEL" \
        -d text="✅ 自动备份成功%0A%0A⏰ 时间: $DATE%0A📂 仓库: $GH_USERNAME/$GH_REPO%0A📦 状态: 已推送到 GitHub" \
        >/dev/null 2>&1
    fi
  else
    echo "❌ 推送失败，请检查 GitHub Token 权限"
    
    # 只在非静默模式下发送失败通知
    if [ -z "$SILENT_BACKUP" ] && [ -n "$MANAGER_TOKEN" ] && [ -n "$ADMIN_CHANNEL" ]; then
      curl -s -X POST "https://api.telegram.org/bot$MANAGER_TOKEN/sendMessage" \
        -d chat_id="$ADMIN_CHANNEL" \
        -d text="❌ 自动备份失败%0A%0A⏰ 时间: $DATE%0A📂 仓库: $GH_USERNAME/$GH_REPO%0A⚠️ 原因: GitHub 推送失败" \
        >/dev/null 2>&1
    fi
    exit 1
  fi
fi
