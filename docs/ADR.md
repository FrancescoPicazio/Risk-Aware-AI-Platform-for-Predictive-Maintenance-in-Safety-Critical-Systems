# Architecture Decision Record

---
### Title
Project Setting Up: Choosing LSTM for RUL Prediction

### Status
Accepted

### Context
In the context of predicting Remaining Useful Life (RUL) for safety-critical systems, we need a model that can:

- Capture long-term dependencies in sequential sensor data
- Handle variable-length time series for multiple engines
- Produce stable and interpretable predictions
- Integrate well with a modular architecture for streaming and batch data

Constraints:
- Safety-critical environment requires reliable and explainable predictions
- Data comes from CMAPSS dataset (simulated turbofan engines)
- Must allow for uncertainty estimation and risk-aware decision layers

### Decision
We have decided to use Long Short-Term Memory (LSTM) networks as the core modeling approach for RUL prediction. 

Rationale:
- LSTMs are designed for sequential data and can capture long-term dependencies better than standard RNNs.
- Widely used and well-supported in frameworks like PyTorch and TensorFlow.
- Compatible with ensemble strategies and probabilistic extensions (e.g., MC Dropout).
- Easier integration with monitoring and drift detection pipelines.

Alternative options considered:
- GRU: simpler, faster, but slightly less expressive
- Temporal CNN: good for fixed-length sequences, but less flexible
- Transformers: powerful but may require more data and compute

### Consequences
Positive:
- Accurate modeling of engine degradation patterns
- Easy integration with probabilistic uncertainty layer
- Well-understood training and evaluation workflow

Negative / Trade-offs:
- Training can be slower than GRU for very long sequences
- Memory consumption higher due to LSTM gates
- Requires careful hyperparameter tuning (layers, hidden size, learning rate)

Next Steps:
- Define hyperparameter search space
- Implement training pipeline with early stopping
- Integrate with feature engineering and simulator modules

### Date
18-02-2024

---

### Title
Deployment Architecture: Docker-Based Microservices with MQTT Communication

### Status
Accepted

### Context
The platform requires a production-ready deployment strategy that supports:

- **Modularity**: Independent services that can be developed, tested, and deployed separately
- **Scalability**: Ability to scale individual components based on load
- **Reliability**: Fault isolation and easy recovery from failures
- **Development velocity**: Fast iteration cycles for development teams
- **MLOps readiness**: Support for model versioning, monitoring, and retraining pipelines
- **Production deployment**: Easy transition from development to production environments

Constraints:
- Platform consists of 9 distinct functional components (Simulator, Ingestion, Feature Engineering, Training, Uncertainty, Risk Engine, API, Monitoring, Scheduler)
- Services need asynchronous communication for streaming data processing
- Must support both development (local) and production (cloud) deployments
- Need to minimize infrastructure complexity while maintaining professional standards
- Resource efficiency is important (CPU-only for MVP, GPU optional for production)

### Decision
We have decided to implement a **Docker-based microservices architecture** with **MQTT** for inter-service communication.

**Architecture Components:**
1. **9 Dockerized Microservices**: Each functional component runs in its own container
2. **Eclipse Mosquitto MQTT Broker**: Central message broker for asynchronous communication
3. **Docker Compose**: Local orchestration for development and testing
4. **Shared Volumes**: For data, models, and results persistence
5. **FastAPI**: For synchronous REST API endpoints
6. **CPU-optimized PyTorch**: For reduced image sizes and faster builds

**Service Communication Pattern:**
- **Asynchronous**: MQTT topics for data streaming and event-driven processing
- **Synchronous**: REST API for client-facing inference requests
- **Data sharing**: Docker volumes mounted across relevant containers

**MQTT Topic Structure:**
```
raw/sensors           → Simulator → Ingestion
validated/data        → Ingestion → Feature Engineering
processed/features    → Feature Engineering → Training/Inference
predictions/rul       → Model → Uncertainty
predictions/uncertainty → Uncertainty → Risk Engine
decisions/risk        → Risk Engine → API/Results
monitoring/metrics    → All services → Monitoring
```

**Docker Image Optimization:**
- **CPU-only PyTorch** (~200 MB vs ~4 GB CUDA version)
- **Multi-stage builds** for reduced image sizes
- **Alpine/slim base images** where appropriate
- **Layer caching** for faster rebuild times
- **Increased pip timeout** (300s) for reliable dependency installation

Alternatives Considered:

1. **Monolithic Architecture**
   - Pros: Simpler deployment, no network overhead
   - Cons: Poor separation of concerns, difficult to scale, hard to maintain
   - Rejected: Not suitable for complex ML pipelines with multiple distinct stages

2. **Kubernetes Native**
   - Pros: Advanced orchestration, auto-scaling, high availability
   - Cons: High complexity, steep learning curve, over-engineered for MVP
   - Rejected: Too complex for initial development phase; Docker Compose sufficient for MVP

3. **REST-only Communication**
   - Pros: Simple, widely understood, easy to debug
   - Cons: Synchronous blocking, not suitable for streaming data
   - Rejected: Inadequate for real-time sensor data streaming

4. **Apache Kafka**
   - Pros: High throughput, mature ecosystem, guaranteed delivery
   - Cons: Heavy infrastructure, complex setup, overkill for MVP scale
   - Rejected: MQTT provides sufficient capabilities with lower complexity

5. **Direct Container Communication**
   - Pros: Lower latency, no broker overhead
   - Cons: Tight coupling, difficult service discovery, no message buffering
   - Rejected: Reduces modularity and makes testing harder

### Consequences

**Positive:**
- ✅ **Service Independence**: Each component can be developed, tested, and deployed independently
- ✅ **Easy Local Development**: Docker Compose provides simple "one-command" startup
- ✅ **Production-Ready**: Same containers run in development and production
- ✅ **Fault Isolation**: Service failures don't cascade to other components
- ✅ **Horizontal Scalability**: Can run multiple instances of compute-intensive services
- ✅ **Technology Flexibility**: Each service can use different tech stacks if needed
- ✅ **CI/CD Friendly**: Easy integration with automated build and test pipelines
- ✅ **Resource Efficiency**: CPU-only PyTorch reduces build time from timeout to ~6 minutes
- ✅ **Image Size Reduction**: ~3.7 GB savings per service using PyTorch
- ✅ **Asynchronous Processing**: MQTT enables non-blocking, event-driven architecture
- ✅ **Message Buffering**: MQTT provides automatic message queuing during service restarts
- ✅ **Easy Monitoring**: Centralized log collection and metrics via Docker logging drivers
- ✅ **Environment Parity**: Dev/staging/production use identical container images

**Negative / Trade-offs:**
- ⚠️ **Increased Complexity**: More moving parts to configure and monitor
- ⚠️ **Network Overhead**: Inter-service communication introduces latency (minimal with MQTT)
- ⚠️ **Resource Usage**: Each container has overhead (~50-100 MB base per service)
- ⚠️ **Learning Curve**: Team needs Docker and MQTT knowledge
- ⚠️ **MQTT Broker**: Single point of failure if not properly configured (mitigated with persistence)
- ⚠️ **Debugging**: Distributed tracing more complex than monolithic debugging
- ⚠️ **Initial Setup Time**: Docker builds take ~6 minutes for first run (cached afterwards)

**Mitigation Strategies:**
- **Complexity**: Provide `manage.ps1` / `manage.sh` scripts for common operations
- **MQTT Reliability**: Enable persistence and configure appropriate QoS levels
- **Debugging**: Comprehensive logging with container banners for easy identification
- **Resource Usage**: Use slim base images and share layers where possible
- **Learning Curve**: Complete documentation in `docker/README.md` and `DOCKER_SETUP.md`

**Implementation Details:**
- **Base Images**: `python:3.11-slim` for minimal size
- **MQTT Broker**: Eclipse Mosquitto 2.0 (lightweight, production-ready)
- **Volume Mounts**: 
  - `data/raw` → Simulator, Ingestion (read)
  - `data/processed` → Feature Engineering, Training (read/write)
  - `data/model_artifacts` → Training (write), API/Uncertainty (read)
  - `data/results` → Risk Engine, API (read/write)
  - `logs` → All services (write)
- **Network**: Single Docker bridge network `risk-aware-network`
- **Health Checks**: API service includes health endpoint with Docker HEALTHCHECK
- **Restart Policies**: `unless-stopped` for continuous services, `no` for training

**Migration Path:**
- **Phase 1 (Current)**: Docker Compose for local development ✅
- **Phase 2**: Docker Compose for single-server production deployment
- **Phase 3**: Kubernetes migration if/when scaling requirements justify complexity
- **Phase 4**: Cloud-native services (AWS ECS/Fargate, GCP Cloud Run, Azure Container Instances)

**Build Optimization Results:**
- **Before**: Build timeout after 3+ minutes (downloading 4 GB CUDA packages)
- **After**: Successful build in ~6 minutes (downloading 300 MB CPU-only packages)
- **Savings**: ~3.7 GB per PyTorch-using service (API, Training, Uncertainty)
- **Total Image Size**: ~5.8 GB for all 9 services (vs ~15+ GB with CUDA)

### Next Steps
1. ✅ Complete Docker setup with all 9 services
2. ✅ Implement MQTT communication patterns
3. ✅ Create management scripts (manage.ps1 / manage.sh)
4. 🔄 Implement service business logic (Simulator, Feature Engineering, etc.)
5. 🔄 Add Prometheus metrics collection
6. 📋 Add Grafana dashboards for monitoring
7. 📋 Implement automated testing in CI/CD pipeline
8. 📋 Document Kubernetes migration path
9. 📋 Add distributed tracing (OpenTelemetry/Jaeger)

### References
- Docker documentation: https://docs.docker.com/
- Docker Compose: https://docs.docker.com/compose/
- Eclipse Mosquitto: https://mosquitto.org/
- FastAPI: https://fastapi.tiangolo.com/
- MLOps best practices: https://ml-ops.org/

### Date
23-02-2026

---

