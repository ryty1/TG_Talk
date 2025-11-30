# 使用 Python 3.11 官方镜像作为基础镜像
FROM python:3.11-slim

# 设置工作目录
WORKDIR /app

# 安装系统依赖
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件并安装 Python 依赖
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir \
    python-telegram-bot==20.7 \
    python-dotenv

# 复制应用程序文件
COPY host_bot.py /app/
COPY database.py /app/

# 创建数据目录
RUN mkdir -p /app/data

# 设置环境变量
ENV PYTHONUNBUFFERED=1 \
    TG_BOT_DATA_DIR=/app/data

# 暴露端口（如果需要健康检查）
# EXPOSE 8080

# 启动应用
CMD ["python", "host_bot.py"]
