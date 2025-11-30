# 🚀 Docker 快速部署（3步搞定）

## 第一步：下载配置文件

```bash
mkdir tg_multi_bot && cd tg_multi_bot
curl -O https://raw.githubusercontent.com/zeroornull/TG_Talk/main/docker-compose.yml
```

## 第二步：修改配置

```bash
nano docker-compose.yml
```

找到并修改这两行：

```yaml
MANAGER_TOKEN: "YOUR_BOT_TOKEN_HERE"        # 改成你的 Bot Token
ADMIN_CHANNEL: "-1001234567890"             # 改成你的频道/群组 ID
```

### 🤖 获取 Bot Token
1. 搜索 @BotFather
2. 发送 `/newbot`
3. 复制收到的 Token

### 📢 获取频道 ID
1. 将 Bot 添加到频道/群组
2. 访问：`https://api.telegram.org/bot你的TOKEN/getUpdates`
3. 找到 `"chat":{"id":-100xxxxxxxxxx}`

## 第三步：启动

```bash
docker-compose up -d
```

✅ **完成！** 查看日志：`docker-compose logs -f`

---

## 💡 一键命令

```bash
mkdir tg_multi_bot && cd tg_multi_bot && \
curl -O https://raw.githubusercontent.com/zeroornull/TG_Talk/main/docker-compose.yml && \
nano docker-compose.yml && \
docker-compose up -d
```

---

## 📋 常用命令

```bash
docker-compose logs -f          # 查看日志
docker-compose restart          # 重启
docker-compose down            # 停止
docker-compose pull && docker-compose up -d  # 更新
```

---

详细文档：[README_DOCKER.md](./README_DOCKER.md)
