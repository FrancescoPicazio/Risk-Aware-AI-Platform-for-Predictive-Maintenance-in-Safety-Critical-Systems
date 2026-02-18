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
