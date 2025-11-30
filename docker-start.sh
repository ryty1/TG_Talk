#!/bin/bash

# Telegram Multi-Bot Docker 管理脚本

set -e

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 项目目录
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

# 打印带颜色的消息
print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

# 检查 Docker 和 Docker Compose
check_docker() {
    if ! command -v docker &> /dev/null; then
        print_error "Docker 未安装，请先安装 Docker"
        exit 1
    fi

    if ! command -v docker-compose &> /dev/null; then
        print_error "Docker Compose 未安装，请先安装 Docker Compose"
        exit 1
    fi

    print_success "Docker 环境检查通过"
}

# 检查配置文件
check_env() {
    if [ ! -f ".env" ]; then
        print_warning "未找到 .env 文件，正在创建..."
        if [ -f ".env.example" ]; then
            cp .env.example .env
            print_info "已从 .env.example 创建 .env 文件"
            print_warning "请编辑 .env 文件，填写必需的配置项："
            print_info "  - MANAGER_TOKEN: 管理机器人 Token"
            print_info "  - ADMIN_CHANNEL: 管理员频道/群组 ID"
            echo ""
            read -p "按 Enter 键继续编辑 .env 文件..."
            ${EDITOR:-nano} .env
        else
            print_error ".env.example 文件不存在"
            exit 1
        fi
    fi

    # 验证必需的环境变量
    source .env
    if [ -z "$MANAGER_TOKEN" ] || [ "$MANAGER_TOKEN" = "123456789:ABCdefGHIjklMNOpqrsTUVwxyz" ]; then
        print_error "MANAGER_TOKEN 未配置或使用示例值，请编辑 .env 文件"
        exit 1
    fi

    if [ -z "$ADMIN_CHANNEL" ] || [ "$ADMIN_CHANNEL" = "-1001234567890" ]; then
        print_error "ADMIN_CHANNEL 未配置或使用示例值，请编辑 .env 文件"
        exit 1
    fi

    print_success "配置文件检查通过"
}

# 创建数据目录
create_data_dir() {
    if [ ! -d "data" ]; then
        mkdir -p data
        print_success "已创建数据目录: ./data"
    fi
}

# 启动服务
start_service() {
    print_info "正在启动服务..."
    docker-compose up -d
    print_success "服务启动成功"
    echo ""
    print_info "使用以下命令查看日志："
    echo "  docker-compose logs -f"
}

# 停止服务
stop_service() {
    print_info "正在停止服务..."
    docker-compose down
    print_success "服务已停止"
}

# 重启服务
restart_service() {
    print_info "正在重启服务..."
    docker-compose restart
    print_success "服务已重启"
}

# 查看日志
view_logs() {
    print_info "查看服务日志（Ctrl+C 退出）..."
    docker-compose logs -f
}

# 查看状态
view_status() {
    print_info "服务状态："
    docker-compose ps
    echo ""

    if [ -f "data/bot_data.db" ]; then
        db_size=$(du -h data/bot_data.db | cut -f1)
        print_info "数据库文件: data/bot_data.db ($db_size)"
    else
        print_warning "数据库文件不存在"
    fi
}

# 备份数据
backup_data() {
    BACKUP_NAME="tg_bot_backup_$(date +%Y%m%d_%H%M%S).tar.gz"
    print_info "正在备份数据到 $BACKUP_NAME ..."
    tar -czf "$BACKUP_NAME" data/ .env
    print_success "备份完成: $BACKUP_NAME"
}

# 更新并重启
update_service() {
    print_info "正在拉取最新代码..."
    git pull

    print_info "正在重新构建镜像..."
    docker-compose build

    print_info "正在重启服务..."
    docker-compose up -d

    print_success "更新完成"
}

# 完全清理
clean_all() {
    print_warning "⚠️  此操作将删除所有容器、镜像和数据！"
    read -p "确认删除？(yes/no): " confirm

    if [ "$confirm" = "yes" ]; then
        print_info "正在清理..."
        docker-compose down -v
        rm -rf data/
        print_success "清理完成"
    else
        print_info "已取消清理操作"
    fi
}

# 主菜单
show_menu() {
    echo ""
    echo "=================================="
    echo "  Telegram Multi-Bot Docker 管理"
    echo "=================================="
    echo "1) 启动服务"
    echo "2) 停止服务"
    echo "3) 重启服务"
    echo "4) 查看日志"
    echo "5) 查看状态"
    echo "6) 备份数据"
    echo "7) 更新并重启"
    echo "8) 编辑配置 (.env)"
    echo "9) 完全清理（删除所有数据）"
    echo "0) 退出"
    echo "=================================="
}

# 主程序
main() {
    # 如果有命令行参数，直接执行对应操作
    if [ $# -gt 0 ]; then
        case "$1" in
            start)
                check_docker
                check_env
                create_data_dir
                start_service
                ;;
            stop)
                stop_service
                ;;
            restart)
                restart_service
                ;;
            logs)
                view_logs
                ;;
            status)
                view_status
                ;;
            backup)
                backup_data
                ;;
            update)
                update_service
                ;;
            clean)
                clean_all
                ;;
            *)
                print_error "未知命令: $1"
                print_info "可用命令: start, stop, restart, logs, status, backup, update, clean"
                exit 1
                ;;
        esac
        exit 0
    fi

    # 交互式菜单
    while true; do
        show_menu
        read -p "请选择操作 [0-9]: " choice

        case $choice in
            1)
                check_docker
                check_env
                create_data_dir
                start_service
                ;;
            2)
                stop_service
                ;;
            3)
                restart_service
                ;;
            4)
                view_logs
                ;;
            5)
                view_status
                ;;
            6)
                backup_data
                ;;
            7)
                update_service
                ;;
            8)
                ${EDITOR:-nano} .env
                print_success "配置已更新，请重启服务使配置生效"
                ;;
            9)
                clean_all
                ;;
            0)
                print_info "退出脚本"
                exit 0
                ;;
            *)
                print_error "无效选择，请输入 0-9"
                ;;
        esac

        echo ""
        read -p "按 Enter 键继续..."
    done
}

# 运行主程序
main "$@"
