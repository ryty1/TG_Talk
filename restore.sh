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
SERVICE_NAME="tg_multi_bot"
VERIFY_SERVICE_NAME="tg_verify_server"

# 加载环境变量
if [ -f "$APP_DIR/.env" ]; then
  source "$APP_DIR/.env"
else
  echo "⚠️ 未找到 .env 文件，将使用当前 shell 环境变量"
fi

# 检查必要的环境变量
if [ -z "$GH_USERNAME" ] || [ -z "$GH_REPO" ] || [ -z "$GH_TOKEN" ]; then
  echo "❌ GitHub 配置缺失，请先配置 GitHub 自动备份"
  exit 1
fi

echo "============================"
echo "   从 GitHub 恢复备份"
echo "============================"
echo ""
echo "⚠️  警告：此操作将覆盖当前数据！"
echo "📦 仓库: https://github.com/$GH_USERNAME/$GH_REPO"
echo ""

# 克隆或拉取 GitHub 仓库（先拉取以显示备份信息）
echo "📥 从 GitHub 拉取备份数据..."
if [ -d "$BACKUP_DIR/.git" ]; then
  cd "$BACKUP_DIR"
  git fetch origin >/dev/null 2>&1
  git reset --hard origin/main >/dev/null 2>&1
else
  rm -rf "$BACKUP_DIR"
  git clone -b main "https://$GH_TOKEN@github.com/$GH_USERNAME/$GH_REPO.git" "$BACKUP_DIR" >/dev/null 2>&1
  cd "$BACKUP_DIR"
fi

# 显示备份信息
if [ -f "$BACKUP_DIR/backup_info.txt" ]; then
  echo ""
  echo "📋 备份信息："
  cat "$BACKUP_DIR/backup_info.txt"
  echo ""
fi

# 恢复选项
echo "============================"
echo "   请选择要恢复的内容"
echo "============================"
echo ""
echo "1) 仅恢复数据文件 (bot_data.db)"
echo "2) 恢复数据库 + 配置文件 (.env)"
echo "3) 恢复数据库 + 脚本 (host_bot, database, verify_server, templates)"
echo "4) 恢复全部 (数据 + 配置 + 脚本)"
echo "5) 自定义选择"
echo "0) 取消操作"
echo ""
read -p "请选择 [0-5]: " RESTORE_OPTION

case "$RESTORE_OPTION" in
  0)
    echo "❌ 操作已取消"
    exit 0
    ;;
  1)
    RESTORE_DATA=true
    RESTORE_ENV=false
    RESTORE_SCRIPT=false
    ;;
  2)
    RESTORE_DATA=true
    RESTORE_ENV=true
    RESTORE_SCRIPT=false
    ;;
  3)
    RESTORE_DATA=true
    RESTORE_ENV=false
    RESTORE_SCRIPT=true
    ;;
  4)
    RESTORE_DATA=true
    RESTORE_ENV=true
    RESTORE_SCRIPT=true
    ;;
  5)
    echo ""
    read -p "恢复数据文件(bot_data.db)？[Y/n]: " ans_data
    RESTORE_DATA=true
    [[ "$ans_data" =~ ^[Nn]$ ]] && RESTORE_DATA=false
    
    read -p "恢复配置文件 (.env)？[y/N]: " ans_env
    RESTORE_ENV=false
    [[ "$ans_env" =~ ^[Yy]$ ]] && RESTORE_ENV=true
    
    read -p "恢复脚本文件 (含 host_bot, database, verify_server, templates)？[y/N]: " ans_script
    RESTORE_SCRIPT=false
    [[ "$ans_script" =~ ^[Yy]$ ]] && RESTORE_SCRIPT=true
    ;;
  *)
    echo "❌ 无效选择"
    exit 1
    ;;
esac

# 确认操作
echo ""
echo "将要恢复的内容："
$RESTORE_DATA && echo "  ✅ 数据库文件 (bot_data.db)"
$RESTORE_ENV && echo "  ✅ 配置文件 (.env)"
$RESTORE_SCRIPT && echo "  ✅ 脚本文件 (host_bot.py, database.py, verify_server.py, templates/)"
echo ""
read -p "确认恢复？[y/N]: " CONFIRM

if [[ ! "$CONFIRM" =~ ^[Yy]$ ]]; then
  echo "❌ 操作已取消"
  exit 0
fi

echo ""
echo "🛑 停止服务..."
systemctl stop $SERVICE_NAME.service 2>/dev/null || true
systemctl stop $VERIFY_SERVICE_NAME.service 2>/dev/null || true

# 备份当前数据（以防万一）
BACKUP_TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_OLD_DIR="$APP_DIR/backup_before_restore_$BACKUP_TIMESTAMP"
mkdir -p "$BACKUP_OLD_DIR"

echo "💾 备份当前数据到: $BACKUP_OLD_DIR"
cp -f "$APP_DIR/bot_data.db" "$BACKUP_OLD_DIR/" 2>/dev/null || true
cp -f "$APP_DIR/.env" "$BACKUP_OLD_DIR/" 2>/dev/null || true
cp -f "$APP_DIR/host_bot.py" "$BACKUP_OLD_DIR/" 2>/dev/null || true
cp -f "$APP_DIR/database.py" "$BACKUP_OLD_DIR/" 2>/dev/null || true
cp -f "$APP_DIR/verify_server.py" "$BACKUP_OLD_DIR/" 2>/dev/null || true
if [ -d "$APP_DIR/templates" ]; then
    cp -r "$APP_DIR/templates" "$BACKUP_OLD_DIR/" 2>/dev/null || true
fi

# 恢复文件
echo ""
echo "🔄 开始恢复..."
RESTORED_COUNT=0

# 恢复数据库文件
if [ "$RESTORE_DATA" = true ]; then
  echo "📦 恢复数据库文件..."
  
  if [ -f "$BACKUP_DIR/bot_data.db" ]; then
    # 清理旧的 WAL/SHM 辅助文件，避免恢复后读取到旧日志
    rm -f "$APP_DIR/bot_data.db-wal" "$APP_DIR/bot_data.db-shm" 2>/dev/null || true
    cp -f "$BACKUP_DIR/bot_data.db" "$APP_DIR/"
    echo "  ✅ bot_data.db"
    RESTORED_COUNT=$((RESTORED_COUNT + 1))
  else
    echo "  ⚠️ 备份中未找到 bot_data.db"
  fi
fi

# 恢复配置文件
if [ "$RESTORE_ENV" = true ]; then
  echo "⚙️ 恢复配置文件..."
  
  if [ -f "$BACKUP_DIR/.env" ]; then
    cp -f "$BACKUP_DIR/.env" "$APP_DIR/"
    echo "  ✅ .env"
    RESTORED_COUNT=$((RESTORED_COUNT + 1))
  else
    echo "  ⚠️ 备份中未找到 .env 文件"
  fi
fi

# 恢复脚本文件
if [ "$RESTORE_SCRIPT" = true ]; then
  echo "📜 恢复脚本文件..."
  
  if [ -f "$BACKUP_DIR/host_bot.py" ]; then
    cp -f "$BACKUP_DIR/host_bot.py" "$APP_DIR/"
    echo "  ✅ host_bot.py"
    RESTORED_COUNT=$((RESTORED_COUNT + 1))
  else
    echo "  ⚠️ 备份中未找到 host_bot.py 文件"
  fi
  
  if [ -f "$BACKUP_DIR/database.py" ]; then
    cp -f "$BACKUP_DIR/database.py" "$APP_DIR/"
    echo "  ✅ database.py"
    RESTORED_COUNT=$((RESTORED_COUNT + 1))
  fi
  
  if [ -f "$BACKUP_DIR/verify_server.py" ]; then
    cp -f "$BACKUP_DIR/verify_server.py" "$APP_DIR/"
    echo "  ✅ verify_server.py"
    RESTORED_COUNT=$((RESTORED_COUNT + 1))
  fi
  
  if [ -d "$BACKUP_DIR/templates" ]; then
    cp -r "$BACKUP_DIR/templates" "$APP_DIR/"
    echo "  ✅ templates/"
    RESTORED_COUNT=$((RESTORED_COUNT + 1))
  fi
fi

echo ""
echo "🚀 重启服务..."
systemctl start $SERVICE_NAME.service
systemctl start $VERIFY_SERVICE_NAME.service

# 清理临时恢复目录
echo "🧹 清理临时文件..."
rm -rf "$BACKUP_DIR"

if [ $RESTORED_COUNT -gt 0 ]; then
  echo ""
  echo "============================"
  echo "   恢复完成！"
  echo "============================"
  echo "✅ 已恢复 $RESTORED_COUNT 个文件"
  echo "💾 原数据备份于: $BACKUP_OLD_DIR"
  echo "🔧 服务已重启"
  echo "🧹 临时文件已清理"
  echo "============================"
else
  echo "⚠️ 未恢复任何文件"
  systemctl start $SERVICE_NAME.service
  systemctl start $VERIFY_SERVICE_NAME.service
fi
