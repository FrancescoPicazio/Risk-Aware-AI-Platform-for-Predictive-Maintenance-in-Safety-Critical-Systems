# Docker Setup Summary

## 📋 Service Architecture

```
┌─────────────────────────────────────────────────────────┐
│                  Risk-Aware AI Platform                 │
└─────────────────────────────────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        │                   │                   │
   ┌────▼────┐         ┌────▼────┐        ┌────▼────┐
   │Simulator│         │   MQTT  │        │  API    │
   │  :raw   │────────▶│ Broker  │◀───────│  :8000  │
   └─────────┘         │ :1883   │        └─────────┘
                       └────┬────┘
        ┌──────────────────┼──────────────────┐
        │                  │                  │
   ┌────▼────┐       ┌─────▼─────┐     ┌─────▼─────┐
   │Ingestion│       │  Feature  │     │Uncertainty│
   │         │──────▶│Engineering│────▶│  Engine   │
   └─────────┘       └───────────┘     └─────┬─────┘
                                              │
                     ┌────────────────────────┘
                     │
              ┌──────▼──────┐        ┌──────────┐
              │    Risk     │        │Monitoring│
              │   Engine    │        │ & Drift  │
              └─────────────┘        └──────────┘
                     │
              ┌──────▼──────┐
              │  Scheduler  │
              └─────────────┘
```

1. **MQTT Broker** (Eclipse Mosquitto) - Message broker for inter-service communication
2. **Simulator** - Streams simulated sensor data from raw files
3. **Data Ingestion** - Validates and processes incoming sensor streams
4. **Feature Engineering** - Extracts features from validated data
5. **Training Pipeline** - Trains and updates RUL prediction models
6. **Uncertainty Engine** - Computes prediction uncertainty and confidence intervals
7. **Risk & Cost Engine** - Calculates risk scores and maintenance recommendations
8. **Inference API** - FastAPI service exposing prediction endpoints
9. **Monitoring** - Tracks drift, performance, and KPIs
10. **Scheduler** - Orchestrates periodic tasks (training, monitoring)


## 🚀 Quick Start

### Windows (PowerShell)
```powershell
# Build all images
.\manage.ps1 build

# Start all services
.\manage.ps1 up

# Check status
.\manage.ps1 ps

# View logs
.\manage.ps1 logs

# Stop services
.\manage.ps1 down
```

### Linux/Mac (Bash)
```bash
# Make script executable
chmod +x manage.sh

# Build all images
./manage.sh build

# Start all services
./manage.sh up

# Check status
./manage.sh ps

# View logs
./manage.sh logs

# Stop services
./manage.sh down
```

### Manual (Docker Compose)
```bash
cd docker
docker-compose build
docker-compose up -d
docker-compose ps
docker-compose logs -f
docker-compose down
```

## 📊 Exposed Ports

| Service | Port | Protocol | Description |
|---------|------|----------|-------------|
| API | 8000 | HTTP | REST API endpoints |
| MQTT Broker | 1883 | MQTT | Message broker |
| MQTT WebSocket | 9001 | WebSocket | MQTT over WebSocket |

## 📁 Volume Mounts

| Host Path | Container Path | Purpose |
|-----------|---------------|---------|
| `./data/raw` | `/app/data/raw` | Raw sensor data |
| `./data/processed` | `/app/data/processed` | Processed features |
| `./data/model_artifacts` | `/app/data/model_artifacts` | Trained models |
| `./data/results` | `/app/data/results` | Prediction results |
| `./data/metrics` | `/app/data/metrics` | System metrics |
| `./logs` | `/app/logs` | Application logs |
| `./configs` | `/app/configs` | Configuration files |

## 📝 Notes

- All services use MQTT for inter-service communication
- Services are designed to be stateless (data persisted to volumes)
- Scheduler service is optional for MVP
- Training service runs on-demand (not always running)
- All Python services use Python 3.11-slim base image
- PyTorch is installed from CPU-only wheel to reduce image size



## Prerequisites

- Docker Engine 20.10+
- Docker Compose 2.0+
- At least 8GB RAM
- 10GB free disk space

## Quick Start

### 1. Build all containers

```bash
cd docker
docker-compose build
```

### 2. Start the platform

```bash
docker-compose up
```

Or run in detached mode:

```bash
docker-compose up -d
```

### 3. Check container status

```bash
docker-compose ps
```

### 4. View logs

```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f api
docker-compose logs -f simulator
```

### 5. Stop the platform

```bash
docker-compose down
```

To also remove volumes:

```bash
docker-compose down -v
```

## Service Endpoints

- **API**: http://localhost:8000
  - `/health` - Health check
  - `/predict` - RUL prediction
  - `/risk` - Risk assessment
  - `/metrics` - Prometheus metrics

- **MQTT Broker**: 
  - MQTT: `localhost:1883`
  - WebSocket: `localhost:9001`

## Configuration

Copy `.env.example` to `.env` and customize:

```bash
cp .env.example .env
```

Edit environment variables as needed.

## MQTT Topics

- `raw/sensors` - Raw sensor data from simulator
- `validated/data` - Validated sensor data
- `processed/features` - Engineered features
- `predictions/rul` - RUL predictions
- `predictions/uncertainty` - Uncertainty quantification
- `decisions/risk` - Risk scores and recommendations
- `monitoring/metrics` - System metrics

## Volume Mounts

The following host directories are mounted:

- `../data/raw` - Raw training data
- `../data/processed` - Processed features
- `../data/model_artifacts` - Trained models
- `../data/results` - Prediction results
- `../data/metrics` - Monitoring metrics
- `../logs` - Application logs
- `../configs` - Configuration files

## Troubleshooting

### Container fails to start

```bash
docker-compose logs <service-name>
```

### Reset everything

```bash
docker-compose down -v
docker-compose build --no-cache
docker-compose up
```

### Check MQTT messages

```bash
# Subscribe to all topics
docker exec -it risk-aware-mqtt mosquitto_sub -h localhost -t '#' -v
```

### Enter a container

```bash
docker exec -it risk-aware-api bash
```

## Development Mode

For development, you can mount source code as volumes:

```yaml
volumes:
  - ../src:/app/src:ro
```

Then restart the service:

```bash
docker-compose restart <service-name>
```

## Production Considerations

Before deploying to production:

1. **Security**:
   - Configure MQTT authentication (`mosquitto.conf`)
   - Use TLS/SSL certificates
   - Set `allow_anonymous false`

2. **Resource Limits**:
   - Add memory and CPU limits to services
   - Configure restart policies

3. **Logging**:
   - Use centralized logging (ELK, Loki)
   - Configure log rotation

4. **Monitoring**:
   - Add Prometheus + Grafana services
   - Configure alerting rules

5. **Data Persistence**:
   - Use named volumes for critical data
   - Configure backup strategies

## Architecture Diagram

See `../docs/ARCHITECTURE.md` for detailed architecture diagrams.

## 🔍 Troubleshooting

### Service won't start
```bash
docker-compose logs <service-name>
```

### MQTT connection issues
```bash
# Check broker is running
docker-compose ps mqtt-broker

# Test MQTT connection
docker exec -it risk-aware-mqtt mosquitto_sub -h localhost -t '#' -v
```

### Permission issues on volumes
```bash
# Linux/Mac: Fix permissions
sudo chown -R $USER:$USER data/ logs/
```

### Clear everything and restart
```bash
# Windows
.\manage.ps1 clean
.\manage.ps1 build
.\manage.ps1 up

# Linux/Mac
./manage.sh clean
./manage.sh build
./manage.sh up
```

## 📚 References

- Docker documentation: https://docs.docker.com/
- Docker Compose: https://docs.docker.com/compose/
- Eclipse Mosquitto: https://mosquitto.org/
- FastAPI: https://fastapi.tiangolo.com/
- PyTorch: https://pytorch.org/

