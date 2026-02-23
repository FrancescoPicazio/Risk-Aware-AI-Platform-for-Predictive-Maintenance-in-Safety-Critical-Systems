#!/bin/bash

# Risk-Aware AI Platform - Docker Management Script
# Bash script for managing the platform

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DOCKER_DIR="$PROJECT_ROOT/docker"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

show_help() {
    echo -e "${CYAN}Risk-Aware AI Platform - Docker Management${NC}"
    echo ""
    echo -e "${YELLOW}Usage: ./manage.sh [command]${NC}"
    echo ""
    echo -e "${GREEN}Commands:${NC}"
    echo "  build      Build all Docker images"
    echo "  up         Start all services"
    echo "  down       Stop all services"
    echo "  restart    Restart all services"
    echo "  logs       Show logs (follow mode)"
    echo "  ps         Show running containers"
    echo "  clean      Stop and remove all containers, volumes, and images"
    echo "  help       Show this help message"
    echo ""
}

build_images() {
    echo -e "${CYAN}Building Docker images...${NC}"
    cd "$DOCKER_DIR" || exit 1
    docker-compose build --parallel
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}Build completed successfully!${NC}"
    else
        echo -e "${RED}Build failed!${NC}"
        exit 1
    fi
}

start_services() {
    echo -e "${CYAN}Starting services...${NC}"
    cd "$DOCKER_DIR" || exit 1
    docker-compose up -d
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}Services started successfully!${NC}"
        echo ""
        docker-compose ps
    else
        echo -e "${RED}Failed to start services!${NC}"
        exit 1
    fi
}

stop_services() {
    echo -e "${CYAN}Stopping services...${NC}"
    cd "$DOCKER_DIR" || exit 1
    docker-compose down
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}Services stopped successfully!${NC}"
    else
        echo -e "${RED}Failed to stop services!${NC}"
        exit 1
    fi
}

restart_services() {
    echo -e "${CYAN}Restarting services...${NC}"
    stop_services
    start_services
}

show_logs() {
    echo -e "${CYAN}Showing logs (Ctrl+C to exit)...${NC}"
    cd "$DOCKER_DIR" || exit 1
    docker-compose logs -f
}

show_status() {
    echo -e "${CYAN}Container Status:${NC}"
    cd "$DOCKER_DIR" || exit 1
    docker-compose ps
}

clean_all() {
    echo -e "${RED}WARNING: This will remove all containers, volumes, and images!${NC}"
    read -p "Are you sure? (yes/no): " confirmation

    if [ "$confirmation" = "yes" ]; then
        echo -e "${CYAN}Cleaning up...${NC}"
        cd "$DOCKER_DIR" || exit 1
        docker-compose down -v --rmi all
        echo -e "${GREEN}Cleanup completed!${NC}"
    else
        echo -e "${YELLOW}Cleanup cancelled.${NC}"
    fi
}

# Main execution
case "${1:-help}" in
    build)
        build_images
        ;;
    up)
        start_services
        ;;
    down)
        stop_services
        ;;
    restart)
        restart_services
        ;;
    logs)
        show_logs
        ;;
    ps)
        show_status
        ;;
    clean)
        clean_all
        ;;
    help|*)
        show_help
        ;;
esac

