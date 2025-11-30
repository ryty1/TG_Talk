# 🚀 Docker 快速开始指南（5分钟部署）

## 第一步：准备 Bot Token 和频道 ID

### 1.1 创建 Telegram Bot

1. 在 Telegram 搜索并打开 [@BotFather](https://t.me/BotFather)
2. 发送命令：`/newbot`
3. 设置机器人名称（如：My Customer Service Bot）
4. 设置用户名（如：my_cs_bot，必须以 bot 结尾）
5. **保存收到的 Token**（格式：`123456789:ABCdefGHI...`）

### 1.2 获取管理员频道 ID

方法一（推荐）：使用 [@userinfobot](https://t.me/userinfobot)
1. 将 @userinfobot 添加到你的频道/群组
2. 在频道/群组发送任意消息
3. 机器人会回复频道 ID（格式：`-100xxxxxxxxxx`）

方法二：手动获取
1. 将你的 Bot 添加到频道/群组
2. 在频道/群组发送一条消息
3. 访问：`https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates`
4. 在 JSON 响应中找到 `"chat":{"id":-100xxxxxxxxxx}`

---

## 第二步：部署服务

### 2.1 克隆项目

```bash
git clone https://github.com/your-repo/TG_Talk.git
cd TG_Talk
```

### 2.2 配置环境变量

```bash
# 复制配置模板
cp .env.example .env

# 编辑配置文件
nano .env  # 或使用 vim、vi 等编辑器
```

**填写以下内容：**

```env
# 替换为你的 Bot Token
MANAGER_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz

# 替换为你的频道 ID
ADMIN_CHANNEL=-1001234567890
```

保存并退出（nano: Ctrl+X → Y → Enter）

### 2.3 启动服务

```bash
# 一键启动
docker-compose up -d

# 查看启动日志
docker-compose logs -f
```

看到以下输出表示启动成功：
```
✅ 宿主管理Bot已启动
```

按 `Ctrl+C` 退出日志查看（服务继续运行）

---

## 第三步：使用机器人

### 3.1 开始使用

在 Telegram 中找到你的管理 Bot，发送：`/start`

### 3.2 添加子 Bot

1. 点击 "➕ 添加机器人"
2. 输入子 Bot 的 Token
3. 等待添加成功

### 3.3 配置子 Bot

1. 点击 "🤖 我的机器人"
2. 选择刚添加的 Bot
3. 可配置：
   - ✏️ 设置欢迎语
   - 🔁 切换模式（私聊/话题）
   - 🛠 设置话题群 ID（话题模式需要）

---

## 第四步：验证部署

### 4.1 检查服务状态

```bash
# 查看容器状态
docker-compose ps

# 应该显示：
# NAME            STATE    PORTS
# tg_multi_bot    Up       ...
```

### 4.2 查看数据库

```bash
# 检查数据目录
ls -la ./data

# 应该看到 bot_data.db 文件
```

### 4.3 测试功能

1. 用另一个账号向子 Bot 发送消息
2. 消息应该转发到你的管理频道
3. 在管理频道回复，消息应该发送给用户

---

## 常用命令速查

```bash
# 查看日志
docker-compose logs -f

# 重启服务
docker-compose restart

# 停止服务
docker-compose down

# 停止并删除所有数据（谨慎使用！）
docker-compose down -v
rm -rf ./data

# 更新代码并重启
git pull
docker-compose build
docker-compose up -d
```

---

## 🆘 遇到问题？

### 问题 1：容器启动失败

```bash
# 查看详细日志
docker-compose logs

# 常见原因：
# - .env 文件配置错误
# - Token 或频道 ID 格式不正确
# - Docker 未启动
```

### 问题 2：Bot 无响应

1. 检查 Token 是否正确
2. 确认已发送 `/start` 命令
3. 查看日志是否有错误：`docker-compose logs -f`

### 问题 3：权限错误

```bash
# 修复数据目录权限
sudo chown -R $(id -u):$(id -g) ./data
```

### 问题 4：端口占用

```bash
# Docker 不需要暴露端口，如果有端口占用，检查是否有其他服务冲突
docker ps -a
```

---

## 🎉 完成！

现在你可以：
- ✅ 添加多个子 Bot 进行托管
- ✅ 接收用户消息并回复
- ✅ 使用黑名单功能管理用户
- ✅ 切换私聊/话题模式
- ✅ 自定义欢迎语

📖 **详细文档**：[README_DOCKER.md](./README_DOCKER.md)

💬 **技术支持**：[@tg_multis_bot](https://t.me/tg_multis_bot)

---

**总耗时**：约 5 分钟 ⏱️
