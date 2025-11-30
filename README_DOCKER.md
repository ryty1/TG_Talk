# Telegram 多 Bot 管理平台 - Docker 部署指南

## 📦 项目简介

支持多个 Telegram Bot 的托管管理平台，提供私聊模式和话题模式两种消息转发方式。

## 🚀 快速开始

### 前置要求

- Docker 20.10+
- Docker Compose 1.29+

### 1. 克隆项目

```bash
git clone <repository_url>
cd TG_Talk
```

### 2. 配置环境变量

复制环境变量模板并填写配置：

```bash
cp .env.example .env
```

编辑 `.env` 文件，填写以下必需配置：

```env
# 管理机器人 Token（从 @BotFather 获取）
MANAGER_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz

# 管理员频道/群组 ID
ADMIN_CHANNEL=-1001234567890
```

#### 获取 Telegram Bot Token

1. 在 Telegram 中搜索 [@BotFather](https://t.me/BotFather)
2. 发送 `/newbot` 命令创建新机器人
3. 按提示设置机器人名称和用户名
4. 复制收到的 Token 到 `MANAGER_TOKEN`

#### 获取管理员频道/群组 ID

1. 将机器人添加到目标频道/群组
2. 在频道/群组发送一条消息
3. 访问 `https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates`
4. 在返回的 JSON 中查找 `"chat":{"id":-100xxxxxxxxxx}`
5. 复制该 ID 到 `ADMIN_CHANNEL`

### 3. 启动服务

```bash
# 构建并启动容器
docker-compose up -d

# 查看日志
docker-compose logs -f

# 停止服务
docker-compose down
```

### 4. 数据持久化

数据库文件存储在 `./data` 目录下，会自动创建并持久化。

```bash
# 查看数据目录
ls -la ./data
```

## 📋 Docker 环境变量说明

### 必需配置

| 变量名 | 说明 | 示例 |
|--------|------|------|
| `MANAGER_TOKEN` | 管理机器人 Token | `123456789:ABC...` |
| `ADMIN_CHANNEL` | 管理员频道/群组 ID | `-1001234567890` |

### 可选配置

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `TG_BOT_DATA_DIR` | 数据存储目录 | `/app/data` |
| `BACKUP_SCRIPT_PATH` | 备份脚本路径 | `/app/backup.sh` |
| `GH_USERNAME` | GitHub 用户名（备份用） | - |
| `GH_REPO` | GitHub 仓库名（备份用） | - |
| `GH_TOKEN` | GitHub Token（备份用） | - |

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

### 更新部署

```bash
# 拉取最新代码
git pull

# 重新构建镜像
docker-compose build

# 重启服务
docker-compose up -d
```

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

1. 检查 `.env` 文件是否配置正确
2. 检查 Docker 和 Docker Compose 版本
3. 查看容器日志：`docker-compose logs`
4. 检查端口占用

### 数据库问题

```bash
# 进入容器检查数据库
docker-compose exec tg-bot-host /bin/bash
cd /app/data
ls -la bot_data.db

# 测试数据库连接
python3 << EOF
import sqlite3
conn = sqlite3.connect('/app/data/bot_data.db')
cursor = conn.cursor()
cursor.execute("SELECT COUNT(*) FROM bots")
print(f"Bot count: {cursor.fetchone()[0]}")
conn.close()
EOF
```

### 权限问题

```bash
# 修复数据目录权限
sudo chown -R $(id -u):$(id -g) ./data
```

## 📊 健康检查

容器内置健康检查机制，每 30 秒检查一次：

```bash
# 查看健康状态
docker-compose ps

# 手动执行健康检查
docker exec tg_multi_bot python -c "import os; exit(0 if os.path.exists('/app/data/bot_data.db') else 1)"
```

## 🔐 安全建议

1. **环境变量保护**：
   - 不要将 `.env` 文件提交到版本控制
   - 使用 `.gitignore` 排除敏感文件

2. **Token 安全**：
   - 定期更换 Bot Token
   - 使用强密码保护管理员账号

3. **备份策略**：
   - 定期备份 `./data` 目录
   - 使用 GitHub 私有仓库存储备份

4. **访问控制**：
   - 仅管理员可访问管理功能
   - 使用黑名单功能屏蔽恶意用户

## 📁 目录结构

```
TG_Talk/
├── Dockerfile              # Docker 镜像构建文件
├── docker-compose.yml      # Docker Compose 配置
├── .env.example           # 环境变量模板
├── .dockerignore          # Docker 构建忽略文件
├── host_bot.py            # 主程序
├── database.py            # 数据库模块
├── setup.sh               # 传统部署脚本（可选）
├── README_DOCKER.md       # Docker 部署文档
└── data/                  # 数据目录（自动创建）
    └── bot_data.db        # SQLite 数据库
```

## 🆚 部署方式对比

| 特性 | Docker 部署 | 传统部署 (setup.sh) |
|------|-------------|---------------------|
| 环境隔离 | ✅ 完全隔离 | ❌ 依赖系统环境 |
| 部署难度 | ⭐ 简单 | ⭐⭐ 中等 |
| 跨平台 | ✅ 支持 | ❌ 仅 Linux |
| 维护成本 | ⭐ 低 | ⭐⭐ 中等 |
| 资源占用 | 较低 | 最低 |
| 推荐场景 | 生产环境、跨平台 | Linux 服务器 |

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

### 3. 克隆项目并迁移数据

```bash
# 克隆项目
git clone <repository_url>
cd TG_Talk

# 创建数据目录
mkdir -p ./data

# 迁移数据库
cp ~/bot_data.db.backup ./data/bot_data.db

# 配置环境变量
cp ~/tg_bot.env.backup ./.env
```

### 4. 启动 Docker 服务

```bash
docker-compose up -d
```

### 5. 验证迁移

```bash
# 查看日志
docker-compose logs -f

# 验证数据
docker-compose exec tg-bot-host ls -la /app/data
```

## 📞 技术支持

- GitHub Issues: [提交问题](https://github.com/your-repo/TG_Talk/issues)
- Telegram: [@tg_multis_bot](https://t.me/tg_multis_bot)

## 📄 许可证

本项目采用 [MIT License](LICENSE)

---

💡 **提示**：首次部署建议先在测试环境验证，确保配置正确后再部署到生产环境。
