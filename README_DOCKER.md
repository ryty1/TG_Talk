# Telegram 多 Bot 管理平台 - Docker 部署指南

## 📦 项目简介

支持多个 Telegram Bot 的托管管理平台，提供私聊模式和话题模式两种消息转发方式。

## 🚀 三步快速部署

### 前置要求

- Docker 20.10+
- Docker Compose 1.29+

### 步骤 1：下载配置文件

```bash
# 创建项目目录
mkdir tg_multi_bot && cd tg_multi_bot

# 下载 docker-compose.yml
curl -O https://raw.githubusercontent.com/zeroornull/TG_Talk/main/docker-compose.yml
```

### 步骤 2：修改配置

编辑 `docker-compose.yml` 文件，修改两个必需参数：

```bash
nano docker-compose.yml  # 或使用 vim、vi 等编辑器
```

找到并修改以下两行：

```yaml
MANAGER_TOKEN: "YOUR_BOT_TOKEN_HERE"        # 改为你的 Bot Token
ADMIN_CHANNEL: "-1001234567890"             # 改为你的频道/群组 ID
```

#### 🤖 如何获取 Bot Token？

1. 在 Telegram 搜索 [@BotFather](https://t.me/BotFather)
2. 发送 `/newbot` 创建新机器人
3. 按提示设置名称和用户名
4. 复制收到的 Token（格式：`123456789:ABCdefGHIjklMNOpqrsTUVwxyz`）

#### 📢 如何获取频道/群组 ID？

1. 将机器人添加到目标频道/群组
2. 在频道/群组发送一条消息
3. 浏览器访问：`https://api.telegram.org/bot你的TOKEN/getUpdates`
4. 在 JSON 中查找：`"chat":{"id":-100xxxxxxxxxx}`
5. 复制该 ID（格式：`-1001234567890`）

### 步骤 3：启动服务

```bash
# 启动容器
docker-compose up -d

# 查看日志
docker-compose logs -f
```

✅ **完成！** 现在你的机器人已经运行了。

---

## 💡 一键部署命令

```bash
# 下载配置文件 → 编辑配置 → 启动服务
mkdir tg_multi_bot && cd tg_multi_bot && \
curl -O https://raw.githubusercontent.com/zeroornull/TG_Talk/main/docker-compose.yml && \
nano docker-compose.yml && \
docker-compose up -d
```

---

## 🐳 Docker 镜像说明

### 可用镜像标签

项目通过 GitHub Actions 自动构建并发布到 GitHub Container Registry (ghcr.io)：

| 标签 | 说明 | 使用场景 |
|------|------|---------|
| `latest` | 最新稳定版本 | 生产环境推荐 ⭐ |
| `v1.0.0` | 特定版本号 | 版本锁定 |
| `main` | main 分支最新代码 | 测试新功能 |

### 切换镜像版本

编辑 `docker-compose.yml`，修改 `image` 行：

```yaml
# 使用特定版本
image: ghcr.io/zeroornull/tg_talk:v1.0.0

# 使用最新版本（默认）
image: ghcr.io/zeroornull/tg_talk:latest
```

### 更新到最新版本

```bash
# 停止容器
docker-compose down

# 拉取最新镜像
docker-compose pull

# 启动新版本
docker-compose up -d
```

---

## 🛠️ 常用命令

### 容器管理

```bash
# 启动容器
docker-compose up -d

# 停止容器
docker-compose down

# 重启容器
docker-compose restart

# 查看容器状态
docker-compose ps

# 查看实时日志
docker-compose logs -f

# 查看最近 100 行日志
docker-compose logs --tail=100

# 进入容器
docker-compose exec tg-bot-host /bin/bash
```

### 数据备份与恢复

```bash
# 备份数据目录
tar -czf tg_bot_backup_$(date +%Y%m%d).tar.gz ./data

# 恢复数据
tar -xzf tg_bot_backup_20240101.tar.gz
```

---

## 📋 环境变量说明

### 必需配置

| 变量名 | 说明 | 示例 |
|--------|------|------|
| `MANAGER_TOKEN` | 管理机器人 Token | `123456789:ABC...` |
| `ADMIN_CHANNEL` | 管理员频道/群组 ID | `-1001234567890` |

### 可选配置

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `GH_USERNAME` | GitHub 用户名（备份） | - |
| `GH_REPO` | GitHub 仓库名（备份） | - |
| `GH_TOKEN` | GitHub Token（备份） | - |

### 通过命令行设置环境变量

如果你不想编辑 `docker-compose.yml`，也可以通过命令行设置：

```bash
# 方式 1：使用 -e 参数
docker run -d \
  --name tg_multi_bot \
  --restart unless-stopped \
  -e MANAGER_TOKEN="你的TOKEN" \
  -e ADMIN_CHANNEL="-1001234567890" \
  -v ./data:/app/data \
  ghcr.io/zeroornull/tg_talk:latest

# 方式 2：使用环境变量文件
echo "MANAGER_TOKEN=你的TOKEN" > .env
echo "ADMIN_CHANNEL=-1001234567890" >> .env
docker-compose --env-file .env up -d
```

---

## 🔧 故障排查

### 查看日志

```bash
# 查看所有日志
docker-compose logs

# 查看最近 100 行日志
docker-compose logs --tail=100

# 实时跟踪日志
docker-compose logs -f
```

### 容器无法启动

1. 检查 `MANAGER_TOKEN` 和 `ADMIN_CHANNEL` 是否配置正确
2. 检查 Docker 和 Docker Compose 版本
3. 查看容器日志：`docker-compose logs`
4. 检查端口占用

### Token 无效

```bash
# 测试 Token 是否有效
curl https://api.telegram.org/bot你的TOKEN/getMe
```

### 数据库问题

```bash
# 进入容器检查数据库
docker-compose exec tg-bot-host /bin/bash
cd /app/data
ls -la bot_data.db

# 测试数据库连接
python3 << 'PYTHON'
import sqlite3
conn = sqlite3.connect('/app/data/bot_data.db')
cursor = conn.cursor()
cursor.execute("SELECT COUNT(*) FROM bots")
print(f"Bot count: {cursor.fetchone()[0]}")
conn.close()
PYTHON
```

### 权限问题

```bash
# 修复数据目录权限
sudo chown -R $(id -u):$(id -g) ./data
```

---

## 📊 健康检查

容器内置健康检查机制，每 30 秒检查一次：

```bash
# 查看健康状态
docker-compose ps

# 手动执行健康检查
docker exec tg_multi_bot python -c "import os; exit(0 if os.path.exists('/app/data/bot_data.db') else 1)"
```

---

## 🔐 安全建议

1. **Token 安全**：
   - 不要将 Token 提交到公开的代码仓库
   - 定期更换 Bot Token
   - 使用 `.gitignore` 排除配置文件

2. **备份策略**：
   - 定期备份 `./data` 目录
   - 使用 GitHub 私有仓库存储备份
   - 设置自动备份计划

3. **访问控制**：
   - 仅管理员可访问管理功能
   - 使用黑名单功能屏蔽恶意用户

---

## 📁 目录结构

```
tg_multi_bot/
├── docker-compose.yml      # Docker Compose 配置文件
└── data/                   # 数据目录（自动创建）
    └── bot_data.db         # SQLite 数据库
```

---

## 🆚 部署方式对比

| 特性 | Docker 部署 | 传统部署 (setup.sh) |
|------|-------------|---------------------|
| 环境隔离 | ✅ 完全隔离 | ❌ 依赖系统环境 |
| 部署难度 | ⭐ 简单 | ⭐⭐ 中等 |
| 跨平台 | ✅ 支持 | ❌ 仅 Linux |
| 维护成本 | ⭐ 低 | ⭐⭐ 中等 |
| 资源占用 | 较低 | 最低 |
| 推荐场景 | 生产环境、跨平台 | Linux 服务器 |

---

## 🔄 从传统部署迁移到 Docker

如果已使用 `setup.sh` 部署，可按以下步骤迁移：

### 1. 停止传统服务

```bash
sudo systemctl stop tg_multi_bot
sudo systemctl disable tg_multi_bot
```

### 2. 备份数据

```bash
# 备份数据库
cp /opt/tg_multi_bot/bot_data.db ~/bot_data.db.backup

# 备份环境变量
cp /opt/tg_multi_bot/.env ~/tg_bot.env.backup
```

### 3. 创建 Docker 项目

```bash
# 创建目录
mkdir ~/tg_multi_bot && cd ~/tg_multi_bot

# 下载配置文件
curl -O https://raw.githubusercontent.com/zeroornull/TG_Talk/main/docker-compose.yml

# 创建数据目录并迁移数据库
mkdir -p ./data
cp ~/bot_data.db.backup ./data/bot_data.db
```

### 4. 编辑配置并启动

```bash
# 编辑 docker-compose.yml，填入原来的 Token 和 Channel ID
nano docker-compose.yml

# 启动 Docker 服务
docker-compose up -d
```

### 5. 验证迁移

```bash
# 查看日志
docker-compose logs -f

# 验证数据
docker-compose exec tg-bot-host ls -la /app/data
```

---

## 🌐 本地构建镜像（高级）

如果需要修改代码或本地构建：

```bash
# 克隆项目
git clone https://github.com/zeroornull/TG_Talk.git
cd TG_Talk

# 编辑 docker-compose.yml，注释 image 行，取消注释 build 行
# image: ghcr.io/zeroornull/tg_talk:latest  # 注释这行
# build: .                                    # 取消注释这行

# 构建并启动
docker-compose up -d --build
```

---

## 📞 技术支持

- **GitHub Issues**: [提交问题](https://github.com/zeroornull/TG_Talk/issues)
- **Telegram Bot**: [@tg_multis_bot](https://t.me/tg_multis_bot)
- **开发者**: [@SerokBot_bot](https://t.me/SerokBot_bot)

---

## 📄 许可证

本项目采用 [MIT License](LICENSE)

---

💡 **提示**：首次部署建议先在测试环境验证，确保配置正确后再部署到生产环境。
