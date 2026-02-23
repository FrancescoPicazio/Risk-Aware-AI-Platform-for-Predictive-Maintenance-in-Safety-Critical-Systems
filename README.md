# Risk-Aware AI Platform for Predictive Maintenance in Safety-Critical Systems

[![Python](https://img.shields.io/badge/Python-3.11-blue.svg)](https://www.python.org/)
[![PyTorch](https://img.shields.io/badge/PyTorch-2.10-red.svg)](https://pytorch.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.131-green.svg)](https://fastapi.tiangolo.com/)
[![Docker](https://img.shields.io/badge/Docker-Compose-blue.svg)](https://www.docker.com/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Status](https://img.shields.io/badge/Status-In%20Development-yellow.svg)]()

---

## 🌍 Language / Lingua

- [**English Version**](#english-version)
- [**Versione Italiana**](#versione-italiana)

---

# English Version

## 📖 Overview

This platform is an **end-to-end AI lifecycle architecture** designed for **safety-critical predictive maintenance systems**. 

Unlike traditional approaches that focus solely on prediction accuracy, this system transforms raw degradation signals into:

- ✅ **Remaining Useful Life (RUL)** estimates
- ✅ **Uncertainty-aware failure probabilities**
- ✅ **Risk-adjusted maintenance decisions**
- ✅ **Economic optimization outputs**

The platform is **modular**, **production-oriented**, and designed for extensibility across **aerospace**, **automotive**, **rail**, and **energy** domains.

---

## 🎯 Why This Project?

Standard predictive maintenance models fail in safety-critical environments because:

1. They provide **deterministic predictions** without uncertainty quantification
2. They optimize for **accuracy metrics** (RMSE), not **risk mitigation**
3. They ignore the **economic impact** of early vs. late interventions
4. They lack **production-ready architecture** and MLOps integration

This platform addresses all these limitations.

---

## 🚀 Quick Start

### Prerequisites

- **Python 3.11+**
- **Docker & Docker Compose** (for containerized deployment)
- **8GB RAM minimum** (16GB recommended)
- **10GB free disk space**

### Option 1: Docker Deployment (Recommended)

The fastest way to run the entire platform:

```bash
# 1. Clone the repository
git clone <repository-url>
cd Risk-Aware-AI-Platform-for-Predictive-Maintenance-in-Safety-Critical-Systems

# 2. Build all services
./manage.ps1 build    # Windows
./manage.sh build     # Linux/Mac

# 3. Start the platform
./manage.ps1 up       # Windows
./manage.sh up        # Linux/Mac

# 4. Check services status
./manage.ps1 ps       # Windows
./manage.sh ps        # Linux/Mac

# 5. View logs
./manage.ps1 logs     # Windows
./manage.sh logs      # Linux/Mac
```

**Access the API**: http://localhost:8000
- Health check: `http://localhost:8000/health`
- API docs: `http://localhost:8000/docs`
- Metrics: `http://localhost:8000/metrics`

### Option 2: Local Development

For development without Docker:

```bash
# 1. Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
.venv\Scripts\activate     # Windows

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run local orchestration
python main.py
```

**Note**: Local mode runs components sequentially without containerization. For production use, Docker deployment is recommended.

---

## 📁 Project Structure

```
Risk-Aware-AI-Platform/
├── data/                          # Data directory
│   ├── raw/                       # CMAPSS dataset files
│   ├── processed/                 # Processed features
│   ├── model_artifacts/           # Trained models
│   ├── results/                   # Prediction results
│   └── metrics/                   # Performance metrics
├── docker/                        # Docker configuration
│   ├── Dockerfile.*               # Service-specific Dockerfiles
│   ├── docker-compose.yml         # Orchestration configuration
│   ├── mosquitto/                 # MQTT broker config
│   └── README.md                  # Docker deployment guide
├── docs/                          # Documentation
│   ├── ARCHITECTURE.md            # System architecture (C4 model)
│   ├── ADR.md                     # Architecture Decision Records
│   ├── REQUIREMENTS_AND_KPI.md    # Requirements and KPIs
│   ├── DATASET.md                 # Dataset documentation
│   ├── ROADMAP.md                 # Development roadmap
│   └── TASKS.md                   # Task breakdown
├── src/                           # Source code
│   ├── streaming/                 # Data streaming simulator
│   ├── data_ingestion/            # Data ingestion layer
│   ├── feature_engineering/       # Feature engineering
│   ├── model/                     # ML models (LSTM)
│   ├── uncertainty_and_failure/   # Uncertainty quantification
│   ├── risk_and_cost/             # Risk & cost engine
│   ├── api/                       # FastAPI inference service
│   ├── monitoring/                # Drift detection & monitoring
│   ├── scheduler/                 # Task orchestration
│   └── common/                    # Shared components
├── tests/                         # Unit tests
├── configs/                       # Configuration files
├── main.py                        # Local development entry point
├── requirements.txt               # Python dependencies (local)
├── requirements-docker.txt        # Python dependencies (Docker)
├── manage.ps1                     # Docker management (Windows)
└── manage.sh                      # Docker management (Linux/Mac)
```

---

## 🏗️ Architecture

The system follows a **modular, microservices-based architecture** with clear separation of concerns:

```
Data Ingestion → Feature Engineering → RUL Modeling → 
Uncertainty Quantification → Probabilistic Failure Modeling → 
Risk-Aware Decision Engine → Economic Optimization → Inference API
```

For a detailed architectural breakdown, see:
- 📐 **[ARCHITECTURE.md](docs/ARCHITECTURE.md)** – Complete system design and component details
- 📋 **[ADR.md](docs/ADR.md)** – Architecture Decision Records

---

## 🧠 Core Components

### 1. Digital Degradation Simulator
Simulates engine degradation lifecycle with controlled noise and drift

### 2. Data Ingestion Layer
Streaming and batch data loading with validation

### 3. Feature Engineering Module
Health index computation, rolling windows, normalization

### 4. RUL Modeling Engine
LSTM-based baseline with cross-validation (RMSE < 15 cycles target)

### 5. Uncertainty Quantification Layer
MC Dropout, prediction intervals, calibration analysis

### 6. Probabilistic Failure Modeling
Converts RUL + uncertainty into failure probability curves

### 7. Risk-Aware Decision Engine
Risk score calculation and maintenance urgency classification

### 8. Economic Optimization Layer
Cost-based intervention threshold optimization

### 9. Inference API
FastAPI-based REST API for real-time predictions

### 10. Monitoring & Drift Detection
Continuous performance tracking and retraining triggers

---

## 📊 Key Performance Indicators

The platform is evaluated using a comprehensive KPI framework:

### Model Performance
- **RMSE** < 15 cycles (FD001 dataset)
- **NASA Scoring Function** optimization
- **Calibration Error** (ECE) < 0.1

### Risk Metrics
- **Early Failure Detection** > 80% at 30 cycles in advance
- **False Negative Rate** < 10% near failure
- **Hazard Rate Fidelity**

### Business Impact
- **Cost Reduction** ≥ 15%
- **Expected Total Cost** minimization
- **Optimal Intervention Coverage** > 85%

For complete KPI details, see:
- 📈 **[KPI.md](docs/REQUIREMENTS_AND_KPI.md)** – Comprehensive metrics framework

---

## 🚀 Getting Started

### Prerequisites

```bash
Python 3.10
PyTorch 2.10
FastAPI
Docker (optional, for deployment)
```

### Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/Risk-Aware-AI-Platform.git
cd Risk-Aware-AI-Platform

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### Dataset

This project uses the **NASA CMAPSS (C-MAPSS) dataset** for turbofan engine degradation.

Dataset files are located in the `data/` directory:
- Training data: `train_FD001.txt` to `train_FD004.txt`
- Test data: `test_FD001.txt` to `test_FD004.txt`
- Ground truth RUL: `RUL_FD001.txt` to `RUL_FD004.txt`

---

## 📁 Project Structure

```
Risk-Aware-AI-Platform/
│
├── data/                          # CMAPSS dataset files
├── docs/                          # Documentation
│   ├── ARCHITECTURE.md           # System architecture design
│   ├── ADR.md                    # Architecture Decision Records
│   ├── REQUIREMENTS_AND_KPI.md   # Key Performance Indicators and requirements
│   └── DATASET.md                # Dataset documentation
│
├── src/                          
│   ├── data_ingestion/
│   ├── feature_engineering/
│   ├── models/
│   ├── uncertainty/
│   ├── risk_engine/
│   ├── optimization/
│   └── api/
│
├── tests/                        # Unit and integration tests
├── notebooks/                    # Jupyter notebooks for exploration
├── configs/                      # Configuration files
├── docker/                       # Docker configuration
├── README.md                     # This file
└── requirements.txt              # Python dependencies
```

---

## 📄 Documentation

- 📐 **[Architecture](docs/ARCHITECTURE.md)** – Complete system design
- 📋 **[ADR](docs/ADR.md)** – Decision records and rationale
- 📈 **[KPI](docs/REQUIREMENTS_AND_KPI.md)** – Performance metrics framework
- 📊 **[Dataset](docs/DATASET.md)** – Data description and preprocessing

---

## 🤝 Contributing

This is a professional research project. Contributions are welcome following these guidelines:

1. Fork the repository
2. Create a feature branch
3. Follow the architectural principles defined in ARCHITECTURE.md
4. Submit a pull request with clear documentation

---

## 📝 License

This project is licensed under the MIT License - see the LICENSE file for details.

---

## 📧 Contact

For questions, suggestions, or collaboration opportunities, please open an issue or contact the maintainer.

---

## 🎓 Citation

If you use this work in your research or project, please cite:

```bibtex
@misc{risk_aware_ai_platform,
  title={Risk-Aware AI Platform for Predictive Maintenance in Safety-Critical Systems},
  author={Your Name},
  year={2026},
  url={https://github.com/yourusername/Risk-Aware-AI-Platform}
}
```

---

# Versione Italiana

## 📖 Panoramica

Questa piattaforma è un'**architettura AI end-to-end** progettata per **sistemi di manutenzione predittiva safety-critical**.

A differenza degli approcci tradizionali che si concentrano solo sull'accuratezza delle previsioni, questo sistema trasforma i segnali grezzi di degrado in:

- ✅ Stime di **Remaining Useful Life (RUL)**
- ✅ **Probabilità di guasto** con quantificazione dell'incertezza
- ✅ **Decisioni di manutenzione** basate sul rischio
- ✅ **Output di ottimizzazione economica**

La piattaforma è **modulare**, **production-oriented** e progettata per essere estesa in ambiti **aerospaziale**, **automotive**, **ferroviario** ed **energetico**.

---

## 🎯 Perché questo progetto?

I modelli standard di manutenzione predittiva falliscono in ambienti safety-critical perché:

1. Forniscono **previsioni deterministiche** senza quantificazione dell'incertezza
2. Ottimizzano per **metriche di accuratezza** (RMSE), non per **mitigazione del rischio**
3. Ignorano l'**impatto economico** degli interventi anticipati vs. tardivi
4. Mancano di **architettura production-ready** e integrazione MLOps

Questa piattaforma affronta tutte queste limitazioni.

---

## 🏗️ Architettura

Il sistema segue un'**architettura modulare basata su pipeline** con chiara separazione delle responsabilità:

```
Ingestione Dati → Feature Engineering → Modellazione RUL → 
Quantificazione Incertezza → Modellazione Probabilistica Guasti → 
Motore Decisionale Risk-Aware → Ottimizzazione Economica → API di Inferenza
```

Per una descrizione architettonica dettagliata, vedi:
- 📐 **[ARCHITECTURE.md](docs/ARCHITECTURE.md)** – Design completo del sistema e dettagli dei componenti
- 📋 **[ADR.md](docs/ADR.md)** – Architecture Decision Records

---

## 🧠 Componenti Principali

### 1. Simulatore Digitale di Degrado
Simula il ciclo di vita del degrado dei motori con rumore e drift controllati

### 2. Layer di Ingestione Dati
Caricamento dati streaming e batch con validazione

### 3. Modulo di Feature Engineering
Calcolo health index, finestre temporali, normalizzazione

### 4. Motore di Modellazione RUL
Baseline LSTM con cross-validation (target RMSE < 15 cicli)

### 5. Layer di Quantificazione Incertezza
MC Dropout, intervalli di previsione, analisi di calibrazione

### 6. Modellazione Probabilistica dei Guasti
Converte RUL + incertezza in curve di probabilità di guasto

### 7. Motore Decisionale Risk-Aware
Calcolo risk score e classificazione urgenza manutenzione

### 8. Layer di Ottimizzazione Economica
Ottimizzazione soglia di intervento basata sui costi

### 9. API di Inferenza
REST API basata su FastAPI per previsioni in tempo reale

### 10. Monitoraggio & Rilevamento Drift
Tracking continuo delle performance e trigger per retraining

---

## 📊 Indicatori Chiave di Performance

La piattaforma è valutata utilizzando un framework KPI completo:

### Performance del Modello
- **RMSE** < 15 cicli (dataset FD001)
- Ottimizzazione **NASA Scoring Function**
- **Errore di Calibrazione** (ECE) < 0.1

### Metriche di Rischio
- **Rilevamento Guasti Anticipato** > 80% a 30 cicli di anticipo
- **Tasso Falsi Negativi** < 10% in prossimità del guasto
- **Fedeltà Hazard Rate**

### Impatto Business
- **Riduzione Costi** ≥ 15%
- Minimizzazione **Costo Totale Atteso**
- **Copertura Interventi Ottimali** > 85%

Per i dettagli completi dei KPI, vedi:
- 📈 **[KPI.md](docs/REQUIREMENTS_AND_KPI.md)** – Framework completo delle metriche

---


## 🚀 Iniziare

### Prerequisiti

```bash
Python 3.8+
PyTorch 2.0+
FastAPI
Docker (opzionale, per il deployment)
```

### Installazione

```bash
# Clona il repository
git clone https://github.com/tuousername/Risk-Aware-AI-Platform.git
cd Risk-Aware-AI-Platform

# Crea ambiente virtuale
python -m venv venv
source venv/bin/activate  # Su Windows: venv\Scripts\activate

# Installa le dipendenze
pip install -r requirements.txt
```

### Dataset

Questo progetto utilizza il **dataset NASA CMAPSS (C-MAPSS)** per il degrado dei motori turbofan.

I file del dataset si trovano nella directory `data/`:
- Dati di training: `train_FD001.txt` a `train_FD004.txt`
- Dati di test: `test_FD001.txt` a `test_FD004.txt`
- RUL ground truth: `RUL_FD001.txt` a `RUL_FD004.txt`

---

## 📁 Struttura del Progetto

```
Risk-Aware-AI-Platform/
│
├── data/                          # File dataset CMAPSS
├── docs/                          # Documentazione
│   ├── ARCHITECTURE.md           # Design architettura sistema
│   ├── ADR.md                    # Architecture Decision Records
│   ├── REQUIREMENTS_AND_KPI.md   # Indicatori Chiave di Performance e requisiti
│   └── DATASET.md                # Documentazione dataset
│
├── src/                          # Codice sorgente (da sviluppare)
│   ├── data_ingestion/
│   ├── feature_engineering/
│   ├── models/
│   ├── uncertainty/
│   ├── risk_engine/
│   ├── optimization/
│   └── api/
│
├── tests/                        # Test unitari e di integrazione
├── notebooks/                    # Jupyter notebooks per esplorazione
├── configs/                      # File di configurazione
├── docker/                       # Configurazione Docker
├── README.md                     # Questo file
└── requirements.txt              # Dipendenze Python
```

---

## 🔬 Ricerca & Innovazione

Questo progetto rappresenta un **approccio production-first** all'AI in sistemi safety-critical:

- **Non una soluzione Kaggle**: progettato per deployment reale
- **Risk-aware oltre accuracy-only**: focus sull'impatto business
- **Probabilistico by design**: abbraccia la quantificazione dell'incertezza
- **Production-oriented**: include MLOps e monitoring dal primo giorno

---

## 📄 Documentazione

- 📐 **[Architettura](docs/ARCHITECTURE.md)** – Design completo del sistema
- 📋 **[ADR](docs/ADR.md)** – Record delle decisioni e razionale
- 📈 **[KPI](docs/REQUIREMENTS_AND_KPI.md)** – Framework metriche di performance
- 📊 **[Dataset](docs/DATASET.md)** – Descrizione dati e preprocessing

---

## 🤝 Contribuire

Questo è un progetto di ricerca professionale. I contributi sono benvenuti seguendo queste linee guida:

1. Fai un fork del repository
2. Crea un branch per la feature
3. Segui i principi architetturali definiti in ARCHITECTURE.md
4. Invia una pull request con documentazione chiara

---

## 📝 Licenza

Questo progetto è rilasciato sotto licenza MIT - vedi il file LICENSE per i dettagli.

---

## 📧 Contatti

Per domande, suggerimenti o opportunità di collaborazione, apri un issue o contatta il maintainer.

---

## 🎓 Citazione

Se utilizzi questo lavoro nella tua ricerca o progetto, per favore cita:

```bibtex
@misc{risk_aware_ai_platform,
  title={Risk-Aware AI Platform for Predictive Maintenance in Safety-Critical Systems},
  author={Il Tuo Nome},
  year={2026},
  url={https://github.com/tuousername/Risk-Aware-AI-Platform}
}
```

---

**⭐ Se questo progetto ti è utile, lascia una stella su GitHub!**

