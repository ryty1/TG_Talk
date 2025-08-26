#!/bin/bash
set -e

APP_DIR="/opt/tg_multi_bot"
SERVICE_NAME="tg_multi_bot"
SCRIPT_NAME="host_bot.py"
SCRIPT_URL="https://raw.githubusercontent.com/ryty1/TG_Talk/main/host_bot.py"

function check_and_install() {
  PKG=$1
  if ! dpkg -s "$PKG" >/dev/null 2>&1; then
    echo "📦 安装 $PKG ..."
    apt install -y -qq "$PKG" >/dev/null 2>&1
  else
    echo "✅ 已安装 $PKG，跳过"
  fi
}

function install_bot() {
  echo "📦 检查系统依赖..."
  apt update -qq >/dev/null 2>&1
  check_and_install python3
  check_and_install python3-venv
  check_and_install python3-pip
  check_and_install git
  check_and_install curl

  echo "📂 创建项目目录..."
  mkdir -p "$APP_DIR"
  cd "$APP_DIR"

  echo "👾 下载 $SCRIPT_NAME ..."
  curl -sL -o "$SCRIPT_NAME" "$SCRIPT_URL"
  echo "✅ 已下载最新 $SCRIPT_NAME"

  echo "🐍 创建虚拟环境..."
  if [ ! -d venv ]; then
    python3 -m venv venv >/dev/null 2>&1
  fi
  source venv/bin/activate

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

  # 写入 .env
  cat <<EOF > .env
MANAGER_TOKEN=$MANAGER_TOKEN
ADMIN_CHANNEL=$ADMIN_CHANNEL
EOF
  echo "✅ 已生成 .env 配置文件"

  # ------------------ Systemd 服务 ------------------
  echo "🛠️ 配置 systemd 服务..."
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

  echo "🚀 启动并设置开机自启..."
  systemctl daemon-reload >/dev/null 2>&1
  systemctl enable $SERVICE_NAME.service >/dev/null 2>&1
  systemctl restart $SERVICE_NAME.service >/dev/null 2>&1

  echo "✅ 部署完成！使用命令查看日志："
  echo "   journalctl -u $SERVICE_NAME.service -f"
}

function uninstall_bot() {
  echo "🛑 停止服务..."
  systemctl stop $SERVICE_NAME.service >/dev/null 2>&1 || true

  echo "❌ 禁用开机自启..."
  systemctl disable $SERVICE_NAME.service >/dev/null 2>&1 || true

  echo "🗑️ 删除 systemd 服务文件..."
  if [ -f "/etc/systemd/system/$SERVICE_NAME.service" ]; then
      rm -f "/etc/systemd/system/$SERVICE_NAME.service"
      systemctl daemon-reload >/dev/null 2>&1
      echo "✅ 已删除 $SERVICE_NAME.service"
  else
      echo "⚠️ 没有找到 systemd 服务文件"
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
  echo "============================"
  echo "   Telegram 多 Bot 管理脚本"
  echo "   双向 机器人 自用托管平台   "
  echo "============================"
  echo "1) 安装 Bot 管理平台"
  echo "2) 卸载 Bot 管理平台"
  echo "3) 退出"
  read -p "请选择操作 [1-3]: " choice

  case "$choice" in
    1)
      install_bot
      ;;
    2)
      uninstall_bot
      ;;
    3)
      echo "退出脚本"
      exit 0
      ;;
    *)
      echo "❌ 无效选择，请输入 1-3"
      ;;
  esac
done
