#!/bin/bash
set -e

APP_DIR="/opt/tg_multi_bot"
SERVICE_NAME="tg_multi_bot"
SCRIPT_NAME="host_bot.py"
SCRIPT_URL="https://raw.githubusercontent.com/ryty1/TG_Talk/main/host_bot.py"

# ------------------ 工具函数 ------------------
check_and_install() {
  PKG=$1
  if ! dpkg -s "$PKG" >/dev/null 2>&1; then
    echo "📦 安装 $PKG ..."
    apt install -y "$PKG"
  else
    echo "✅ 已安装 $PKG，跳过"
  fi
}

# ------------------ 系统依赖 ------------------
echo "📦 1. 检查系统依赖..."
apt update
check_and_install python3
check_and_install python3-venv
check_and_install python3-pip
check_and_install git
check_and_install curl

# ------------------ 项目目录 ------------------
echo "📂 2. 创建项目目录..."
mkdir -p "$APP_DIR"
cd "$APP_DIR"

# ------------------ 下载脚本 ------------------
echo "👾 3. 获取 $SCRIPT_NAME ..."
curl -L -o "$SCRIPT_NAME" "$SCRIPT_URL"
echo "  已下载最新 $SCRIPT_NAME"

# ------------------ 虚拟环境 ------------------
echo "🐍 4. 创建虚拟环境..."
if [ ! -d venv ]; then
  python3 -m venv venv
fi
source venv/bin/activate

# ------------------ Python 依赖 ------------------
echo "⬆️ 5. 检查 Python 依赖..."
pip install --upgrade pip

# 检查 python-telegram-bot 是否已安装且版本=20.7
PTB_VERSION=$(pip show python-telegram-bot 2>/dev/null | grep Version | awk '{print $2}' || true)
if [ "$PTB_VERSION" != "20.7" ]; then
  echo "📦 安装 python-telegram-bot==20.7 ..."
  pip install "python-telegram-bot==20.7"
else
  echo "✅ 已安装 python-telegram-bot==20.7，跳过"
fi

# dotenv 如果没装就安装
if ! pip show python-dotenv >/dev/null 2>&1; then
  pip install python-dotenv
else
  echo "✅ 已安装 python-dotenv，跳过"
fi

# ------------------ 环境变量 ------------------
echo "⚙️ 6. 生成环境变量 (.env)..."
read -p "请输入宿主 Bot 的 Token: " MANAGER_TOKEN
read -p "请输入管理频道/群 ID（可选，直接回车跳过）: " ADMIN_CHANNEL

cat > "$APP_DIR/.env" <<EOF
MANAGER_TOKEN=$MANAGER_TOKEN
ADMIN_CHANNEL=$ADMIN_CHANNEL
EOF
echo "  已覆盖生成 $APP_DIR/.env"

# ------------------ 脚本头部 ------------------
echo "🔖 7. 添加脚本 shebang & 授权执行..."
if ! head -n 1 "$SCRIPT_NAME" | grep -q "venv/bin/python"; then
  sed -i "1i #!$APP_DIR/venv/bin/python" "$SCRIPT_NAME"
fi
chmod +x "$SCRIPT_NAME"

# ------------------ systemd ------------------
echo "🛠️ 8. 创建 systemd 服务单元..."
cat > "/etc/systemd/system/$SERVICE_NAME.service" <<EOF
[Unit]
Description=Telegram Multi Bot Host
After=network.target

[Service]
Type=simple
WorkingDirectory=$APP_DIR
ExecStart=$APP_DIR/$SCRIPT_NAME
Restart=always
User=root
Environment="PYTHONUNBUFFERED=1"

[Install]
WantedBy=multi-user.target
EOF

# ------------------ 启动 ------------------
echo "🚀 9. 启动 & 启用服务..."
systemctl daemon-reload
systemctl enable "$SERVICE_NAME"
systemctl restart "$SERVICE_NAME"

echo "✅ 完成！服务正在运行。查看状态："
systemctl status "$SERVICE_NAME" -l
