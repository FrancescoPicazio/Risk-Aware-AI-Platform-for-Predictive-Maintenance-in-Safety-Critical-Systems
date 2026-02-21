# Functional Requirements
---
## 1. Data Ingestion
- Support for batch and streaming data ingestion
- Robust data validation and schema enforcement
- Integration with simulated degradation data
- Scalable to handle large datasets and real-time streams
- Extensible to accommodate new data sources and formats
- Logging and monitoring of data quality and ingestion performance
- API for accessing ingested data for training and inference
- Support for incremental data updates and retraining triggers
- Fault tolerance and error handling in ingestion pipeline
- Documentation of data ingestion process and interfaces
- Test coverage for data ingestion components

## 2. Feature Engineering
- Support for temporal windowing and slicing of time series data
- Normalization and standardization of features per engine
- Computation of health indices and derived features
- Feature selection and dimensionality reduction capabilities
- Integration with data ingestion layer for seamless data flow
- Extensible to accommodate new feature engineering techniques
- Logging and monitoring of feature engineering performance

## 3. Modeling
- Implementation of baseline LSTM/GRU models for RUL prediction
- Support for training with cross-validation per engine
- Evaluation using RMSE and NASA scoring function
- Integration with uncertainty estimation techniques (e.g., MC Dropout)
- Extensible to accommodate new model architectures (e.g., Temporal CNN, Attention)
- Logging and monitoring of training performance and metrics

## 4. Uncertainty Quantification
- Implementation of MC Dropout or Deep Ensemble for uncertainty estimation
- Generation of prediction intervals for RUL estimates
- Calibration analysis (e.g., reliability diagrams, ECE)
- Integration with modeling layer for seamless uncertainty estimation
- Extensible to accommodate new uncertainty quantification techniques
- Logging and monitoring of uncertainty estimation performance

## 5. Risk & Cost Engine
- Definition of cost functions for early and late maintenance
- Optimization of intervention thresholds based on expected cost minimization
- Simulation of business impact and cost savings from optimized maintenance
- Integration with modeling and uncertainty layers for risk-aware decision making
- Extensible to accommodate new risk and cost modeling techniques
- Logging and monitoring of risk engine performance and cost impact

## 6. MLOps & Pipeline
- Modular training pipeline (data ingestion -> feature engineering -> modeling -> evaluation)
- Model versioning and artifact registry
- Logging of experiments and training runs (e.g., MLflow, CSV)
- Retraining trigger logic based on data drift or performance degradation
- Script CLI for training and evaluation
- Documentation of workflow and pipeline components
- Test coverage for pipeline components and integration
- Fault tolerance and error handling in pipeline execution
- Scalability to handle large datasets and multiple training runs
- Integration with monitoring and dashboard components for real-time performance tracking
- Support for deployment and inference in production environments (e.g., FastAPI, Docker)

---
# KPI Framework – RUL / Predictive Maintenance Model

---

## A. Model Performance (ML)

### RMSE on RUL
- **Realistic target:** RMSE < 15 cycles (FD001 dataset)  
- **Purpose:** measures temporal prediction accuracy of the model.

### NASA Scoring Function
- Penalizes critical underestimations more heavily
- **Objective:** achieve a competitive score compared to baseline models.

### Calibration Error
- Evaluates whether predicted uncertainty is well calibrated
- **Target:** Expected Calibration Error (ECE) < 0.1 (or chosen threshold)

---

## B. Probabilistic / Risk KPIs

### Early Failure Detection Accuracy
- Percentage of failures predicted at least **N cycles before failure**
- **Target:** > 80% at 30 cycles in advance

### False Negative Rate Near Failure
- Critical for safety-critical systems
- **Target:** < 10%

### Hazard Rate / Survival Curve Fidelity
- Validates the probabilistic behavior of the model
- Measures deviation between predicted survival curves and ground truth

---

## C. Business / Decision KPIs

### Cost Reduction (%)
- Estimated savings enabled by optimized maintenance
- **Baseline:** regular preventive or reactive maintenance
- **Target:** ≥ 15% reduction in total maintenance costs
- Quantifies the economic impact of maintenance decisions

### Expected Total Cost (E(Cost))

Formula:

```math
E(Cost) = P(late) \cdot C_{late} + P(early) \cdot C_{early}
```

### Optimal Intervention Threshold Coverage
- Percentage of recommended interventions that effectively reduce risk
- Target: > 85% of cases below the defined risk threshold