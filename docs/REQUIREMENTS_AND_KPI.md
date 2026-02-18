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