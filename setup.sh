#!/bin/bash
set -e

APP_DIR="/opt/tg_multi_bot"
SETUP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_NAME="tg_multi_bot"
SCRIPT_NAME="host_bot.py"
SCRIPT_URL="https://raw.githubusercontent.com/ryty1/TG_Talk/v1.0.3/host_bot.py"
DATABASE_URL="https://raw.githubusercontent.com/ryty1/TG_Talk/v1.0.3/database.py"
VERIFY_SCRIPT_NAME="verify_server.py"
VERIFY_SERVICE_NAME="tg_verify_server"
VERIFY_SCRIPT_URL="https://raw.githubusercontent.com/ryty1/TG_Talk/v1.0.3/verify_server.py"
BACKUP_SCRIPT_URL="https://raw.githubusercontent.com/ryty1/TG_Talk/v1.0.3/backup.sh"
RESTORE_SCRIPT_URL="https://raw.githubusercontent.com/ryty1/TG_Talk/v1.0.3/restore.sh"
# 模板文件基础URL (假设在 templates 目录下)
TEMPLATES_BASE_URL="https://raw.githubusercontent.com/ryty1/TG_Talk/v1.0.3/templates"

function check_and_install() {
  PKG=$1
  if ! dpkg -s "$PKG" >/dev/null 2>&1; then
    echo "📦 安装 $PKG ..."
    apt install -y -qq "$PKG" >/dev/null 2>&1
  else
    echo "✅ 已安装 $PKG，跳过"
  fi
}

function check_python_version() {
  # 检查 Python 3.11+ 是否存在
  if command -v python3.11 >/dev/null 2>&1; then
    PYTHON_CMD="python3.11"
    echo "✅ 已安装 Python 3.11+，使用 $PYTHON_CMD"
    return 0
  elif command -v python3.12 >/dev/null 2>&1; then
    PYTHON_CMD="python3.12"
    echo "✅ 已安装 Python 3.12+，使用 $PYTHON_CMD"
    return 0
  elif command -v python3.13 >/dev/null 2>&1; then
    PYTHON_CMD="python3.13"
    echo "✅ 已安装 Python 3.13+，使用 $PYTHON_CMD"
    return 0
  elif command -v python3 >/dev/null 2>&1; then
    # 检查现有 python3 版本
    CURRENT_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    MAJOR=$(echo $CURRENT_VERSION | cut -d. -f1)
    MINOR=$(echo $CURRENT_VERSION | cut -d. -f2)
    
    if [ "$MAJOR" -ge 3 ] && [ "$MINOR" -ge 11 ]; then
      PYTHON_CMD="python3"
      echo "✅ 当前 Python 版本 $CURRENT_VERSION 满足要求"
      return 0
    else
      echo "⚠️ 当前 Python 版本 $CURRENT_VERSION 低于 3.11，需要升级"
      return 1
    fi
  else
    echo "⚠️ 未检测到 Python，需要安装"
    return 1
  fi
}

function install_python311() {
  echo "📦 开始安装 Python 3.11 ..."
  
  # 添加 deadsnakes PPA (Ubuntu/Debian)
  if command -v add-apt-repository >/dev/null 2>&1; then
    apt install -y -qq software-properties-common >/dev/null 2>&1
    add-apt-repository ppa:deadsnakes/ppa -y >/dev/null 2>&1
    apt update -qq >/dev/null 2>&1
  else
    apt update -qq >/dev/null 2>&1
  fi
  
  # 安装 Python 3.11
  apt install -y -qq python3.11 python3.11-venv python3.11-dev >/dev/null 2>&1
  
  if command -v python3.11 >/dev/null 2>&1; then
    PYTHON_CMD="python3.11"
    echo "✅ Python 3.11 安装成功"
  else
    echo "❌ Python 3.11 安装失败，请手动安装"
    exit 1
  fi
}

function setup_github_backup() {
  echo ""
  echo "============================"
  echo "   GitHub 自动备份配置"
  echo "============================"
  echo ""
  
  # 确保 Git 已安装
  if ! command -v git >/dev/null 2>&1; then
    echo "📦 安装 Git..."
    apt update -qq >/dev/null 2>&1
    check_and_install git
  else
    echo "✅ Git 已安装"
  fi
  
  read -p "🔐 请输入 GitHub 用户名: " GH_USERNAME
  if [ -z "$GH_USERNAME" ]; then
    echo "❌ 用户名不能为空"
    return 1
  fi
  
  read -p "📦 请输入 GitHub 私有仓库名 (例: tg-bot-backup): " GH_REPO
  if [ -z "$GH_REPO" ]; then
    echo "❌ 仓库名不能为空"
    return 1
  fi
  
  echo ""
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "📘 如何获取 GitHub Personal Access Token"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo ""
  echo "1️⃣  访问 GitHub Settings"
  echo "   https://github.com/settings/tokens"
  echo ""
  echo "2️⃣  点击 'Generate new token' → 'Generate new token (classic)'"
  echo ""
  echo "3️⃣  填写 Token 信息："
  echo "   • Note: 填写备注（如：TG Bot Backup）"
  echo "   • Expiration: 选择过期时间（建议 No expiration）"
  echo ""
  echo "4️⃣  勾选权限（Scopes）："
  echo "   ✅ repo (完整仓库访问权限)"
  echo ""
  echo "5️⃣  点击页面底部 'Generate token'"
  echo ""
  echo "6️⃣  复制生成的 Token（只显示一次，请妥善保存）"
  echo ""
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo ""
  
  read -p "🔑 请输入 GitHub Personal Access Token: " GH_TOKEN
  if [ -z "$GH_TOKEN" ]; then
    echo "❌ Token 不能为空"
    return 1
  fi
  
  # 创建备份脚本（优先使用本地模板，找不到则从远程下载）
  if [ -f "$SETUP_DIR/backup.sh" ]; then
    cp -f "$SETUP_DIR/backup.sh" "$APP_DIR/backup.sh"
    echo "✅ 使用本地 backup.sh 模板"
  elif curl -sL -o "$APP_DIR/backup.sh" "$BACKUP_SCRIPT_URL"; then
    echo "✅ 已从远程下载 backup.sh"
  else
    echo "❌ 创建 backup.sh 失败，请检查网络或手动放置脚本"
    return 1
  fi

  # 设置脚本权限
  chmod +x "$APP_DIR/backup.sh"
  
  # 将 GitHub 配置写入 .env（检查是否已存在，避免重复）
  if grep -q "^GH_USERNAME=" "$APP_DIR/.env" 2>/dev/null; then
    echo "🔄 更新现有 GitHub 配置..."
    # 删除旧的 GitHub 配置
    sed -i '/^# GitHub 自动备份配置/d' "$APP_DIR/.env"
    sed -i '/^GH_USERNAME=/d' "$APP_DIR/.env"
    sed -i '/^GH_REPO=/d' "$APP_DIR/.env"
    sed -i '/^GH_TOKEN=/d' "$APP_DIR/.env"
  fi
  
  # 写入新的 GitHub 配置
  cat <<EOF >> "$APP_DIR/.env"

# GitHub 自动备份配置
GH_USERNAME=$GH_USERNAME
GH_REPO=$GH_REPO
GH_TOKEN=$GH_TOKEN
EOF
  
  echo "✅ 备份脚本已创建"
  
  # 创建恢复脚本
  setup_restore_script
  
  # 检查远程仓库是否有备份数据
  echo ""
  echo "🔍 检查远程仓库是否存在备份数据..."
  
  # 尝试克隆仓库（只获取信息，不影响本地）
  TEMP_CHECK_DIR="/tmp/tg_backup_check_$$"
  if git clone --depth 1 -q "https://$GH_TOKEN@github.com/$GH_USERNAME/$GH_REPO.git" "$TEMP_CHECK_DIR" 2>/dev/null; then
    # 检查是否有备份文件
    if [ -f "$TEMP_CHECK_DIR/bot_data.db" ] || [ -f "$TEMP_CHECK_DIR/backup_info.txt" ]; then
      echo "✅ 发现远程备份数据！"
      echo ""
      
      # 显示备份信息
      if [ -f "$TEMP_CHECK_DIR/backup_info.txt" ]; then
        echo "📋 备份信息："
        cat "$TEMP_CHECK_DIR/backup_info.txt"
        echo ""
      fi
      
      # 询问是否恢复
      read -p "❓ 是否从 GitHub 恢复备份数据？[y/N]: " RESTORE_CONFIRM
      
      if [[ "$RESTORE_CONFIRM" =~ ^[Yy]$ ]]; then
        echo ""
        echo "🔄 开始恢复备份数据..."
        
        # 停止服务（如果正在运行）
        systemctl stop $SERVICE_NAME.service 2>/dev/null || true
        
        # 备份当前数据（如果存在）
        if [ -f "$APP_DIR/bot_data.db" ]; then
          BACKUP_TIMESTAMP=$(date +%Y%m%d_%H%M%S)
          BACKUP_OLD_DIR="$APP_DIR/backup_before_restore_$BACKUP_TIMESTAMP"
          mkdir -p "$BACKUP_OLD_DIR"
          echo "💾 备份当前数据到: $BACKUP_OLD_DIR"
          cp -f "$APP_DIR/bot_data.db" "$BACKUP_OLD_DIR/" 2>/dev/null || true
          cp -f "$APP_DIR/.env" "$BACKUP_OLD_DIR/" 2>/dev/null || true
        fi
        
        # 恢复数据库文件
        if [ -f "$TEMP_CHECK_DIR/bot_data.db" ]; then
          cp -f "$TEMP_CHECK_DIR/bot_data.db" "$APP_DIR/"
          echo "  ✅ 已恢复 bot_data.db"
        fi
        
        # 恢复脚本文件（可选）
        if [ -f "$TEMP_CHECK_DIR/host_bot.py" ]; then
          read -p "   是否同时恢复 host_bot.py？[y/N]: " RESTORE_SCRIPT
          if [[ "$RESTORE_SCRIPT" =~ ^[Yy]$ ]]; then
            cp -f "$TEMP_CHECK_DIR/host_bot.py" "$APP_DIR/"
            echo "  ✅ 已恢复 host_bot.py"
          fi
        fi
        
        if [ -f "$TEMP_CHECK_DIR/database.py" ]; then
          read -p "   是否同时恢复 database.py？[y/N]: " RESTORE_DB_SCRIPT
          if [[ "$RESTORE_DB_SCRIPT" =~ ^[Yy]$ ]]; then
            cp -f "$TEMP_CHECK_DIR/database.py" "$APP_DIR/"
            echo "  ✅ 已恢复 database.py"
          fi
        fi
        
        # 重启服务
        systemctl start $SERVICE_NAME.service 2>/dev/null || true
        
        echo ""
        echo "✅ 备份数据恢复完成！"
      else
        echo "⏭️  跳过恢复，使用全新数据"
      fi
    else
      echo "ℹ️  远程仓库为空，这将是首次备份"
    fi
    
    # 清理临时目录
    rm -rf "$TEMP_CHECK_DIR"
  else
    echo "ℹ️  远程仓库不存在或为空，这将是首次备份"
    echo "   （仓库会在首次备份时自动创建）"
  fi
  
  echo ""
  
  # 配置 cron 定时任务（中国时间 23:59 备份）
  # 使用 TZ 环境变量指定中国时区，不影响系统时区
  CRON_CMD="59 23 * * * TZ='Asia/Shanghai' $APP_DIR/backup.sh >> $APP_DIR/backup.log 2>&1"
  
  # 检查 cron 是否已存在
  if crontab -l 2>/dev/null | grep -q "$APP_DIR/backup.sh"; then
    echo "✅ Cron 定时任务已存在"
  else
    (crontab -l 2>/dev/null; echo "$CRON_CMD") | crontab -
    echo "✅ 已设置每日 23:59 自动备份（中国时间 UTC+8）"
  fi
  
  echo ""
  echo "============================"
  echo "   备份配置完成！"
  echo "============================"
  echo "📦 仓库地址: https://github.com/$GH_USERNAME/$GH_REPO"
  echo "⏰ 备份时间: 每天 23:59（中国时间 UTC+8）"
  echo "📝 备份日志: $APP_DIR/backup.log"
  echo "🔧 手动备份: bash $APP_DIR/backup.sh"
  echo "🔄 恢复备份: bash $APP_DIR/restore.sh"
  echo "📲 备份通知: 已启用（推送到宿主机器人）"
  echo ""
  echo "⚠️  重要提示："
  echo "   配置仅保存参数，不会立即执行备份"
  echo "   首次备份将在今晚 23:59 自动执行（中国时间）"
  echo "   或手动运行: bash $APP_DIR/backup.sh"
  echo "============================"
  echo ""
}

function setup_restore_script() {
  # 创建恢复脚本（优先使用本地模板，找不到则从远程下载）
  if [ -f "$SETUP_DIR/restore.sh" ]; then
    cp -f "$SETUP_DIR/restore.sh" "$APP_DIR/restore.sh"
    echo "✅ 使用本地 restore.sh 模板"
  elif curl -sL -o "$APP_DIR/restore.sh" "$RESTORE_SCRIPT_URL"; then
    echo "✅ 已从远程下载 restore.sh"
  else
    echo "❌ 创建 restore.sh 失败，请检查网络或手动放置脚本"
    return 1
  fi

  chmod +x "$APP_DIR/restore.sh"
  echo "✅ 恢复脚本已创建: $APP_DIR/restore.sh"
}

function install_bot() {
  echo "📦 检查系统依赖..."
  apt update -qq >/dev/null 2>&1
  
  # 检查并安装基础依赖
  check_and_install git
  check_and_install curl
  
  # 检查 Python 版本
  if ! check_python_version; then
    install_python311
  fi
  
  # 确保 venv 模块存在（根据 Python 版本安装对应的 venv 包）
  echo "📦 安装 venv 模块..."
  if [[ "$PYTHON_CMD" == "python3.11" ]]; then
    check_and_install python3.11-venv
  elif [[ "$PYTHON_CMD" == "python3.12" ]]; then
    check_and_install python3.12-venv
  elif [[ "$PYTHON_CMD" == "python3.13" ]]; then
    check_and_install python3.13-venv
  else
    check_and_install python3-venv
  fi
  
  # 确保 pip 存在
  if ! command -v pip3 >/dev/null 2>&1; then
    apt install -y -qq python3-pip >/dev/null 2>&1
  fi

  echo "📂 创建项目目录..."
  mkdir -p "$APP_DIR"
  cd "$APP_DIR"

  echo "📥 下载项目文件..."
  
  # 下载 host_bot.py
  echo "  • 下载 host_bot.py ..."
  if curl -sL -o "$SCRIPT_NAME" "$SCRIPT_URL"; then
    echo "    ✅ host_bot.py"
  else
    echo "    ❌ host_bot.py 下载失败"
    exit 1
  fi
  
  # 下载 database.py
  echo "  • 下载 database.py ..."
  if curl -sL -o "database.py" "$DATABASE_URL"; then
    echo "    ✅ database.py"
  else
    echo "    ❌ database.py 下载失败，请手动上传到 $APP_DIR"
    exit 1
  fi

  # 下载 verify_server.py
  echo "  • 下载 $VERIFY_SCRIPT_NAME ..."
  if curl -sL -o "$VERIFY_SCRIPT_NAME" "$VERIFY_SCRIPT_URL"; then
    echo "    ✅ $VERIFY_SCRIPT_NAME"
  else
    echo "    ❌ $VERIFY_SCRIPT_NAME 下载失败，将创建一个空文件待手动上传"
    touch "$VERIFY_SCRIPT_NAME"
  fi

  # 创建模板目录并下载模板
  echo "📂 创建模板目录..."
  mkdir -p "$APP_DIR/templates"
  
  echo "  • 下载 HTML 模板..."
  # 模板文件列表
  TEMPLATES=("verify.html" "success.html" "error.html")
  
  for tmpl in "${TEMPLATES[@]}"; do
      if curl -sL -o "$APP_DIR/templates/$tmpl" "$TEMPLATES_BASE_URL/$tmpl"; then
        echo "    ✅ templates/$tmpl"
      else
        echo "    ⚠️ templates/$tmpl 下载失败，请手动上传"
      fi
  done

  echo "🐍 创建虚拟环境..."
  # 清理可能存在的失败虚拟环境
  if [ -d venv ] && [ ! -f venv/bin/activate ]; then
    echo "⚠️ 检测到损坏的虚拟环境，正在清理..."
    rm -rf venv
  fi
  
  # 创建虚拟环境
  if [ ! -d venv ]; then
    if $PYTHON_CMD -m venv venv; then
      echo "✅ 虚拟环境创建成功"
    else
      echo "❌ 虚拟环境创建失败"
      echo "请手动执行以下命令检查问题："
      echo "  cd $APP_DIR"
      echo "  $PYTHON_CMD -m venv venv"
      exit 1
    fi
  fi
  
  # 激活虚拟环境
  if [ -f venv/bin/activate ]; then
    source venv/bin/activate
    # 显示 Python 版本
    VENV_PYTHON_VERSION=$(python --version 2>&1)
    echo "✅ 虚拟环境 Python: $VENV_PYTHON_VERSION"
  else
    echo "❌ 虚拟环境激活文件不存在"
    exit 1
  fi

  echo "⬆️ 检查 Python 依赖..."
  pip install --upgrade pip >/dev/null 2>&1

  PTB_VERSION=$(pip show python-telegram-bot 2>/dev/null | grep Version | awk '{print $2}' || true)
  if [ "$PTB_VERSION" != "20.7" ]; then
    echo "📦 安装 python-telegram-bot==20.7 ..."
    pip install -q "python-telegram-bot==20.7"
  else
    echo "✅ 已安装 python-telegram-bot==20.7，跳过"
  fi

  if ! pip show python-dotenv >/dev/null 2>&1; then
    echo "📦 安装 python-dotenv ..."
    pip install -q python-dotenv
  else
    echo "✅ 已安装 python-dotenv，跳过"
  fi
  
  # 安装 verify_server 依赖
  echo "📦 安装 Flask (用于验证服务器) ..."
  pip install -q flask requests

  # ------------------ 环境变量 ------------------
  echo "⚙️ 生成环境变量 (.env)..."
  # 输入宿主 Bot Token
  while true; do
      read -p "请输入宿主 Bot 的 Token: " MANAGER_TOKEN
      if [ -n "$MANAGER_TOKEN" ]; then
          break
      else
          echo "❌ BOT_TOKEN 不能为空，请重新输入"
      fi
  done

  # 输入管理频道/群ID
  while true; do
      read -p "请输入宿主 TG_CHAT_ID : " ADMIN_CHANNEL
      if [ -n "$ADMIN_CHANNEL" ]; then
          break
      else
          echo "❌ 宿主 TG_CHAT_ID 不能为空，请重新输入"
      fi
  done

  echo ""
  echo "🔐 配置 Cloudflare Turnstile (可选，用于增强验证)"
  read -p "请输入 CF Site Key (留空跳过): " CF_SITE_KEY
  if [ -n "$CF_SITE_KEY" ]; then
      read -p "请输入 CF Secret Key: " CF_SECRET_KEY
      # 验证服务器 URL
      read -p "请输入验证服务器 URL (例如 https://verify.example.com，不带结尾斜杠): " VERIFY_URL
      if [ -z "$VERIFY_URL" ]; then
          # 尝试自动获取 IP
          PUBLIC_IP=$(curl -s ifconfig.me)
          VERIFY_URL="http://$PUBLIC_IP"
          echo "⚠️ 未输入 URL，默认使用 http://$PUBLIC_IP"
      fi

      # 验证服务器端口
      read -p "请输入验证服务器端口 (默认 80): " VERIFY_PORT
      if [ -z "$VERIFY_PORT" ]; then
          VERIFY_PORT=80
      fi
  else
      CF_SECRET_KEY=""
      VERIFY_URL="http://localhost:80"
      VERIFY_PORT=80
      echo "ℹ️ 跳过 CF 配置，使用默认值"
  fi

  # 写入 .env
  cat <<EOF > .env
MANAGER_TOKEN=$MANAGER_TOKEN
ADMIN_CHANNEL=$ADMIN_CHANNEL

# Cloudflare Turnstile 配置
CF_TURNSTILE_SITE_KEY=$CF_SITE_KEY
CF_TURNSTILE_SECRET_KEY=$CF_SECRET_KEY

# 验证服务器配置
VERIFY_SERVER_URL=$VERIFY_URL
VERIFY_SERVER_PORT=$VERIFY_PORT
EOF
  echo "✅ 已生成 .env 配置文件"

  # ------------------ Systemd 服务 ------------------
  echo "🛠️ 配置 systemd 服务 (Host Bot)..."
  cat <<EOF >/etc/systemd/system/$SERVICE_NAME.service
[Unit]
Description=Telegram Multi Bot Host
After=network.target

[Service]
Type=simple
WorkingDirectory=$APP_DIR
ExecStart=$APP_DIR/venv/bin/python $APP_DIR/$SCRIPT_NAME
Restart=always
RestartSec=3
EnvironmentFile=$APP_DIR/.env

[Install]
WantedBy=multi-user.target
EOF

  echo "�️ 配置 systemd 服务 (Verify Server)..."
  cat <<EOF >/etc/systemd/system/$VERIFY_SERVICE_NAME.service
[Unit]
Description=Telegram Verify Server
After=network.target

[Service]
Type=simple
WorkingDirectory=$APP_DIR
ExecStart=$APP_DIR/venv/bin/python $APP_DIR/$VERIFY_SCRIPT_NAME
Restart=always
RestartSec=3
EnvironmentFile=$APP_DIR/.env
# Flask on port 80 requires root or capabilities. 
User=root

[Install]
WantedBy=multi-user.target
EOF

  echo "�🚀 启动并设置开机自启..."
  systemctl daemon-reload >/dev/null 2>&1
  
  # Host Bot
  systemctl enable $SERVICE_NAME.service >/dev/null 2>&1
  systemctl restart $SERVICE_NAME.service >/dev/null 2>&1
  
  # Verify Server
  systemctl enable $VERIFY_SERVICE_NAME.service >/dev/null 2>&1
  systemctl restart $VERIFY_SERVICE_NAME.service >/dev/null 2>&1

  echo ""
  echo "✅ 部署完成！"
  echo ""
  
  # 询问是否需要配置 GitHub 自动备份
  echo "============================"
  read -p "📦 是否配置 GitHub 自动备份？[y/N]: " SETUP_BACKUP
  echo "============================"
  
  if [[ "$SETUP_BACKUP" =~ ^[Yy]$ ]]; then
    if setup_github_backup; then
      echo "✅ GitHub 自动备份配置成功"
    else
      echo "⚠️ GitHub 备份配置失败，可稍后手动配置"
    fi
  else
    echo "⏭️ 跳过 GitHub 备份配置"
  fi
  
  echo ""
  echo "============================"
  echo "   部署完成！"
  echo "============================"
  echo "📊 查看日志 (Host): journalctl -u $SERVICE_NAME.service -f"
  echo "� 查看日志 (Verify): journalctl -u $VERIFY_SERVICE_NAME.service -f"
  echo "�🔧 服务管理 (Host): systemctl status/restart $SERVICE_NAME"
  echo "🔧 服务管理 (Verify): systemctl status/restart $VERIFY_SERVICE_NAME"
  echo "📂 项目目录: $APP_DIR"
  if [[ "$SETUP_BACKUP" =~ ^[Yy]$ ]]; then
    echo "📦 备份脚本: $APP_DIR/backup.sh"
    echo "🔄 恢复脚本: $APP_DIR/restore.sh"
  fi
  echo "============================"
}

function uninstall_bot() {
  echo "🛑 停止服务..."
  systemctl stop $SERVICE_NAME.service >/dev/null 2>&1 || true
  systemctl stop $VERIFY_SERVICE_NAME.service >/dev/null 2>&1 || true

  echo "❌ 禁用开机自启..."
  systemctl disable $SERVICE_NAME.service >/dev/null 2>&1 || true
  systemctl disable $VERIFY_SERVICE_NAME.service >/dev/null 2>&1 || true

  echo "🗑️ 删除 systemd 服务文件..."
  if [ -f "/etc/systemd/system/$SERVICE_NAME.service" ]; then
      rm -f "/etc/systemd/system/$SERVICE_NAME.service"
      echo "✅ 已删除 $SERVICE_NAME.service"
  fi
  
  if [ -f "/etc/systemd/system/$VERIFY_SERVICE_NAME.service" ]; then
      rm -f "/etc/systemd/system/$VERIFY_SERVICE_NAME.service"
      echo "✅ 已删除 $VERIFY_SERVICE_NAME.service"
  fi
  
  systemctl daemon-reload >/dev/null 2>&1

  # 移除 cron 定时任务
  if crontab -l 2>/dev/null | grep -q "$APP_DIR/backup.sh"; then
    echo "🗑️ 移除 GitHub 备份定时任务..."
    crontab -l 2>/dev/null | grep -v "$APP_DIR/backup.sh" | crontab -
    echo "✅ 已移除备份定时任务"
  fi

  echo "🗂️ 删除项目目录 $APP_DIR ..."
  if [ -d "$APP_DIR" ]; then
      rm -rf "$APP_DIR"
      echo "✅ 已删除 $APP_DIR"
  else
      echo "⚠️ 项目目录不存在"
  fi

  echo "✅ 卸载完成！"
}

# ------------------ 菜单 ------------------
while true; do
  echo ""
  echo "============================"
  echo "   Telegram 多 Bot 管理脚本"
  echo "   双向 机器人 自用托管平台   "
  echo "============================"
  echo "1) 安装 Bot 管理平台"
  echo "2) 卸载 Bot 管理平台"
  echo "3) 配置 GitHub 自动备份"
  echo "4) 手动执行备份"
  echo "5) 从 GitHub 恢复备份"
  echo "6) 返回 VIP 工具箱"
  echo "7) 退出"
  echo "============================"
  read -p "请选择操作 [1-7]: " choice

  case "$choice" in
    1)
      install_bot
      ;;
    2)
      uninstall_bot
      ;;
    3)
      if [ -d "$APP_DIR" ]; then
        setup_github_backup
      else
        echo "❌ 请先安装 Bot 管理平台"
      fi
      ;;
    4)
      if [ -f "$APP_DIR/backup.sh" ]; then
        echo "🚀 执行手动备份..."
        "$APP_DIR/backup.sh"
      else
        echo "❌ 备份脚本不存在，请先配置 GitHub 自动备份"
      fi
      ;;
    5)
      if [ -f "$APP_DIR/restore.sh" ]; then
        "$APP_DIR/restore.sh"
      else
        echo "❌ 恢复脚本不存在，请先配置 GitHub 自动备份"
      fi
      ;;
    6)
      bash <(curl -Ls https://raw.githubusercontent.com/ryty1/Checkin/refs/heads/main/vip.sh)
      ;;
    7)
      echo ""
      echo "👋 感谢使用 Telegram 多 Bot 管理脚本！"
      echo "💡 提示：您可以随时重新运行此脚本进行管理"
      echo ""
      exit 0
      ;;
    *)
      echo "❌ 无效选择，请输入 1-7"
      ;;
  esac
done
