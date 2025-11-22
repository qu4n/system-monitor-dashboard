.PHONY: help build start stop restart logs status clean rebuild up down

# Default target
help:
	@echo "System Monitor - Management Commands"
	@echo "====================================="
	@echo ""
	@echo "  make build     - Build the Docker image"
	@echo "  make start     - Start the monitor container"
	@echo "  make stop      - Stop the monitor container"
	@echo "  make restart   - Restart the monitor container"
	@echo "  make logs      - View container logs (follow mode)"
	@echo "  make status    - Check container status"
	@echo "  make clean     - Remove the container"
	@echo "  make rebuild   - Rebuild and restart the container"
	@echo "  make up        - Build and start using docker-compose"
	@echo "  make down      - Stop and remove using docker-compose"
	@echo ""
	@echo "Access the dashboard at: http://localhost:5000"

# Build the Docker image
build:
	@echo "Building system-monitor image..."
	docker build -t system-monitor .

# Start the container
start:
	@echo "Starting system-monitor..."
	docker start system-monitor || \
	docker run -d \
		--name system-monitor \
		--privileged \
		-v /sys/class/powercap:/sys/class/powercap:ro \
		--gpus all \
		-p 5000:5000 \
		system-monitor
	@echo "Monitor started at http://localhost:5000"

# Stop the container
stop:
	@echo "Stopping system-monitor..."
	docker stop system-monitor

# Restart the container
restart:
	@echo "Restarting system-monitor..."
	docker restart system-monitor
	@echo "Monitor restarted at http://localhost:5000"

# View logs
logs:
	@echo "Showing logs (press Ctrl+C to exit)..."
	docker logs -f system-monitor

# Check status
status:
	@echo "Container status:"
	@docker ps -a | grep system-monitor || echo "Container not found"

# Remove container
clean:
	@echo "Removing system-monitor container..."
	docker rm -f system-monitor 2>/dev/null || true
	@echo "Container removed"

# Rebuild and restart
rebuild: clean build start
	@echo "Rebuild complete!"

# Docker Compose commands
up:
	@echo "Starting with docker-compose..."
	docker compose up -d --build
	@echo "Monitor started at http://localhost:5000"

down:
	@echo "Stopping docker-compose services..."
	docker compose down
