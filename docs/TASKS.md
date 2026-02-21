# Task Operativi (Roadmap E2E)

Questa checklist deriva da `docs/ROADMAP.md` e organizza il lavoro in task atomici, ordinati per sviluppo.

## Fase 1 - Architettura & Governance
- [x] Definire requisiti funzionali e non-funzionali (affidabilità, latency, explainability) in `docs/REQUIREMENTS_AND_KPI.md.md`
- [x] Formalizzare componenti e interfacce (ingestion, FE, model, risk, API, monitoring) in `docs/ARCHITECTURE.md`
- [ ] Produrre diagramma architetturale (C4/Component) e salvarlo in `docs/ARCHITECTURE.md`
- [x] Inserire ADR principali (scelte modello, metriche, tooling) in `docs/ADR.md`
- [x] Definire KPI tecnici in `docs/REQUIREMENTS_AND_KPI.md.md`

## Fase 2 - Dati & Ingestion
- [x] Documentare dataset CMAPSS e schema in `docs/DATASET.md`
- [ ] Implementare loader robusto (train/test/RUL) in `src/data_ingestion/data_loader.py`
- [ ] Aggiungere validazione qualità dati (missing, range, unita) in `src/data_ingestion/`
- [ ] Creare test unitari per loader/validazione in `tests/`

## Fase 3 - Feature Engineering
- [ ] Normalizzazione/standardizzazione per engine in `src/feature_engineering/`
- [ ] Windowing temporale e slicing in `src/feature_engineering/`
- [ ] Health index computation in `src/feature_engineering/`
- [ ] Salvare dataset preprocessati in `data/processed/`
- [ ] Test per pipeline FE in `tests/`

## Fase 4 - Modeling (Baseline)
- [x] Scelta baseline LSTM documentata in `docs/ADR.md`
- [ ] Implementare baseline LSTM/GRU in `src/models/`
- [ ] Training loop e checkpoint in `src/models/`
- [ ] Cross-validation per engine in `src/models/`
- [ ] Calcolo RMSE e NASA score in `src/models/metrics.py`
- [ ] Report baseline in `docs/KPI.md`

## Fase 5 - Uncertainty & Probabilistic Layer
- [ ] MC Dropout o Deep Ensemble in `src/uncertainty/`
- [ ] Calibrazione predittiva (reliability diagram) in `src/uncertainty/`
- [ ] Prediction intervals per RUL in `src/uncertainty/`
- [ ] Implementare probabilistic failure modeling (hazard/survival) in `src/uncertainty/`
- [ ] Report calibrazione in `docs/KPI.md`

## Fase 6 - Risk & Cost Engine
- [ ] Definire funzione costo early/late in `src/risk_engine/`
- [ ] Ottimizzazione soglia intervento in `src/optimization/`
- [ ] Simulare impatto business (expected cost) in `src/risk_engine/`
- [ ] Report risultati in `docs/KPI.md`

## Fase 7 - MLOps & Pipeline
- [ ] Pipeline training modulare (ingest -> FE -> train -> eval) in `src/`
- [ ] Model versioning e artifact registry in `src/models/`
- [ ] Logging esperimenti (MLflow o CSV) in `src/`
- [ ] Retraining trigger logic in `src/monitoring/`
- [ ] Script CLI per training/eval in `main.py`
- [ ] Documentare workflow in `README.md`

## Fase 8 - API & Deployment
- [ ] Implementare FastAPI inference in `src/api/`
- [ ] Definire schema input/output (pydantic) in `src/api/`
- [ ] Aggiungere endpoint /predict /risk /health /metrics in `src/api/`
- [ ] Dockerfile e compose in `docker/`
- [ ] Healthcheck e versioning API in `src/api/`
- [ ] Documentare endpoint in `README.md`

## Fase 9 - Monitoring & Dashboard
- [ ] Metriche runtime (latency, drift, calibrazione) in `src/monitoring/`
- [ ] Drift detection batch (statistiche feature) in `src/monitoring/`
- [ ] Monitoring performance (RMSE/NASA) in `src/monitoring/`
- [ ] Dashboard (RUL, risk, CI, cost) e link in `docs/ARCHITECTURE.md`

## Fase 10 - Simulazione Degrado
- [ ] Progettare simulatore degradazione (inputs/outputs) in `docs/ARCHITECTURE.md`
- [ ] Implementare simulatore dati sintetici in `src/data_ingestion/`

## Fase 11 - Deliverable
- [ ] README bilingue (EN/IT) con link a `docs/*.md`
- [ ] Whitepaper outline e link a PDF in `docs/ROADMAP.md`
- [ ] Articolo LinkedIn draft in `docs/ROADMAP.md`
- [ ] Demo video breve (link in `docs/ROADMAP.md`)
