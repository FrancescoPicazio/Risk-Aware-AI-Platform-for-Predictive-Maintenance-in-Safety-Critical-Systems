"""
RUL Modeling Engine
====================
Provides the LSTM-based Remaining Useful Life (RUL) prediction model and all
surrounding utilities:

* ``RULDataset``        – PyTorch Dataset for sliding-window sequences
* ``LSTMRULModel``      – LSTM with optional MC-Dropout heads
* ``ModelEngine``       – train / evaluate / predict / save / load logic
* ``MetricsStore``      – read/write JSON metrics to data/results
"""

import json
import logging
import os
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Optional PyTorch import (graceful degradation)
# ------------------------------------------------------------------
try:
    import torch
    import torch.nn as nn
    from torch.utils.data import DataLoader, Dataset
    TORCH_AVAILABLE = True
except ImportError:
    torch = None      # type: ignore[assignment]
    nn = None         # type: ignore[assignment]
    DataLoader = None # type: ignore[assignment]
    Dataset = None    # type: ignore[assignment]
    TORCH_AVAILABLE = False
    logger.warning("PyTorch not installed – model training/inference disabled.")

# ------------------------------------------------------------------
# Constants
# ------------------------------------------------------------------
SEQ_LEN: int = 30          # sequence length for LSTM input
HIDDEN_SIZE: int = 64
NUM_LAYERS: int = 2
DROPOUT: float = 0.2
BATCH_SIZE: int = 256
EPOCHS: int = 50
LR: float = 1e-3
RUL_CLIP: int = 125         # CMAPSS piecewise RUL clip (NASA convention)
MC_SAMPLES: int = 30        # Monte Carlo dropout samples for uncertainty
MIN_TRAINING_ROWS: int = 2000  # minimum processed rows before training


# ==================================================================
# Dataset
# ==================================================================
if TORCH_AVAILABLE:
    class RULDataset(Dataset):
        """Sliding window sequences over processed feature DataFrame."""

        def __init__(self, df: pd.DataFrame, feature_cols: List[str],
                     seq_len: int = SEQ_LEN, rul_clip: int = RUL_CLIP):
            self.sequences: List[np.ndarray] = []
            self.targets: List[float] = []

            for _, group in df.groupby("unit_id"):
                g = group.sort_values("cycle").reset_index(drop=True)
                X = g[feature_cols].values.astype(np.float32)
                max_cycle = g["cycle"].max()
                rul = np.clip(max_cycle - g["cycle"].values, 0, rul_clip).astype(np.float32)

                for i in range(len(g) - seq_len):
                    self.sequences.append(X[i: i + seq_len])
                    self.targets.append(rul[i + seq_len - 1])

        def __len__(self) -> int:
            return len(self.sequences)

        def __getitem__(self, idx: int):
            return (
                torch.tensor(self.sequences[idx]),
                torch.tensor([self.targets[idx]])
            )


# ==================================================================
# LSTM model
# ==================================================================
if TORCH_AVAILABLE:
    class LSTMRULModel(nn.Module):
        """
        Two-layer LSTM with a fully-connected regression head.
        Dropout is applied after each LSTM layer **and** kept active during
        inference to enable Monte Carlo Dropout uncertainty estimation.
        """

        def __init__(self, input_size: int, hidden_size: int = HIDDEN_SIZE,
                     num_layers: int = NUM_LAYERS, dropout: float = DROPOUT):
            super().__init__()
            self.hidden_size = hidden_size
            self.num_layers = num_layers
            self.lstm = nn.LSTM(
                input_size=input_size,
                hidden_size=hidden_size,
                num_layers=num_layers,
                batch_first=True,
                dropout=dropout if num_layers > 1 else 0.0,
            )
            self.dropout = nn.Dropout(dropout)
            self.fc = nn.Sequential(
                nn.Linear(hidden_size, 32),
                nn.ReLU(),
                nn.Linear(32, 1)
            )

        def forward(self, x: "torch.Tensor") -> "torch.Tensor":
            out, _ = self.lstm(x)          # (B, T, H)
            out = self.dropout(out[:, -1, :])  # last time step
            return self.fc(out)            # (B, 1)


# ==================================================================
# Metrics store
# ==================================================================
class MetricsStore:
    """
    Persists model metrics as JSON in data/results/.
    Each training run appends an entry keyed by run timestamp.
    """

    def __init__(self, results_dir: str):
        self.path = Path(results_dir) / "model_metrics.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> List[dict]:
        if self.path.exists():
            with open(self.path) as f:
                return json.load(f)
        return []

    def append(self, metrics: dict) -> None:
        records = self._load()
        records.append(metrics)
        with open(self.path, "w") as f:
            json.dump(records, f, indent=2)
        logger.info(f"MetricsStore: saved metrics → {self.path}")

    def best_model(self) -> Optional[dict]:
        """Return the record with the lowest RMSE (best model)."""
        records = self._load()
        if not records:
            return None
        return min(records, key=lambda r: r.get("rmse", float("inf")))

    def all(self) -> List[dict]:
        return self._load()


# ==================================================================
# ModelEngine
# ==================================================================
class ModelEngine:
    """
    Orchestrates training, evaluation, saving and loading of the LSTM model.
    """

    def __init__(self, artifacts_dir: str, results_dir: str,
                 seq_len: int = SEQ_LEN):
        self.artifacts_dir = Path(artifacts_dir)
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        self.seq_len = seq_len
        self.metrics_store = MetricsStore(results_dir)
        if TORCH_AVAILABLE:
            self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        else:
            self.device = None
        self._model: Optional["LSTMRULModel"] = None
        self._feature_cols: Optional[List[str]] = None

    # ------------------------------------------------------------------
    # Feature columns helper
    # ------------------------------------------------------------------
    @staticmethod
    def get_feature_cols(df: pd.DataFrame) -> List[str]:
        """Return all numeric feature columns (exclude metadata)."""
        exclude = {"unit_id", "cycle", "timestamp", "source_file", "RUL"}
        return [c for c in df.columns
                if c not in exclude and pd.api.types.is_numeric_dtype(df[c])]

    # ------------------------------------------------------------------
    # Train
    # ------------------------------------------------------------------
    def train(self, df: pd.DataFrame) -> dict:
        """
        Train the LSTM on the provided (processed) DataFrame.

        Returns
        -------
        dict with keys: run_id, rmse, nasa_score, epochs, n_samples, model_path
        """
        if not TORCH_AVAILABLE:
            raise RuntimeError("PyTorch is required for training.")

        self._feature_cols = self.get_feature_cols(df)
        input_size = len(self._feature_cols)
        logger.info(f"ModelEngine: training with {input_size} features, "
                    f"{len(df)} rows on {self.device}")

        dataset = RULDataset(df, self._feature_cols, self.seq_len)
        loader = DataLoader(dataset, batch_size=BATCH_SIZE, shuffle=True,
                            num_workers=0, pin_memory=False)

        model = LSTMRULModel(input_size).to(self.device)
        optimiser = torch.optim.Adam(model.parameters(), lr=LR, weight_decay=1e-4)
        criterion = nn.MSELoss()

        model.train()
        for epoch in range(1, EPOCHS + 1):
            epoch_loss = 0.0
            for x_batch, y_batch in loader:
                x_batch = x_batch.to(self.device)
                y_batch = y_batch.to(self.device)
                optimiser.zero_grad()
                pred = model(x_batch)
                loss = criterion(pred, y_batch)
                loss.backward()
                optimiser.step()
                epoch_loss += loss.item() * len(x_batch)

            avg_loss = epoch_loss / len(dataset)
            if epoch % 10 == 0:
                logger.info(f"Epoch {epoch}/{EPOCHS} – MSE loss: {avg_loss:.4f}")

        # Evaluate on same data (proxy – no held-out split for streaming scenario)
        rmse, nasa = self._evaluate(model, loader)
        logger.info(f"ModelEngine: RMSE={rmse:.2f}  NASA={nasa:.2f}")

        # Persist model
        run_id = f"run_{int(time.time())}"
        model_path = str(self.artifacts_dir / f"{run_id}.pt")
        feature_path = str(self.artifacts_dir / f"{run_id}_features.json")

        torch.save(model.state_dict(), model_path)
        with open(feature_path, "w") as f:
            json.dump(self._feature_cols, f)

        metrics = {
            "run_id": run_id,
            "rmse": round(rmse, 4),
            "nasa_score": round(nasa, 4),
            "epochs": EPOCHS,
            "n_samples": len(dataset),
            "model_path": model_path,
            "feature_path": feature_path,
            "trained_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        self.metrics_store.append(metrics)
        self._model = model
        return metrics

    # ------------------------------------------------------------------
    # Evaluate
    # ------------------------------------------------------------------
    def _evaluate(self, model: "LSTMRULModel",
                  loader: "DataLoader") -> Tuple[float, float]:
        model.eval()
        all_preds, all_targets = [], []
        with torch.no_grad():
            for x_batch, y_batch in loader:
                x_batch = x_batch.to(self.device)
                preds = model(x_batch).cpu().numpy().flatten()
                all_preds.extend(preds)
                all_targets.extend(y_batch.numpy().flatten())

        preds_arr = np.array(all_preds)
        tgts_arr = np.array(all_targets)
        rmse = float(np.sqrt(np.mean((preds_arr - tgts_arr) ** 2)))
        nasa = float(_nasa_score(preds_arr, tgts_arr))
        model.train()
        return rmse, nasa

    # ------------------------------------------------------------------
    # Load best model
    # ------------------------------------------------------------------
    def load_best(self) -> bool:
        """
        Load the best-performing model from model_artifacts.
        Returns True if a model was loaded, False otherwise.
        """
        if not TORCH_AVAILABLE:
            return False
        best = self.metrics_store.best_model()
        if best is None:
            logger.warning("ModelEngine: no trained model found.")
            return False

        feature_path = best.get("feature_path")
        model_path = best.get("model_path")

        if not (feature_path and os.path.exists(feature_path)):
            logger.error(f"ModelEngine: feature file not found: {feature_path}")
            return False
        if not os.path.exists(model_path):
            logger.error(f"ModelEngine: model file not found: {model_path}")
            return False

        with open(feature_path) as f:
            self._feature_cols = json.load(f)

        model = LSTMRULModel(len(self._feature_cols))
        model.load_state_dict(torch.load(model_path, map_location=self.device))
        model.to(self.device)
        model.eval()
        self._model = model
        logger.info(f"ModelEngine: loaded best model → {model_path} "
                    f"(RMSE={best['rmse']})")
        return True

    # ------------------------------------------------------------------
    # Predict (inference)
    # ------------------------------------------------------------------
    def predict(self, df: pd.DataFrame,
                mc_samples: int = MC_SAMPLES) -> Dict[str, float]:
        """
        Run MC-Dropout inference on the last ``seq_len`` cycles of ``df``
        for a single engine unit.

        Returns
        -------
        dict with: rul_mean, rul_std, rul_lower, rul_upper
        """
        if not TORCH_AVAILABLE or self._model is None:
            raise RuntimeError("No model loaded. Call load_best() first.")

        feature_cols = self._feature_cols
        df_sorted = df.sort_values("cycle").tail(self.seq_len)

        if len(df_sorted) < self.seq_len:
            # Pad with the first available row if not enough history
            pad = pd.concat(
                [df_sorted.iloc[[0]]] * (self.seq_len - len(df_sorted)) + [df_sorted],
                ignore_index=True
            )
        else:
            pad = df_sorted

        X = pad[feature_cols].values.astype(np.float32)
        tensor = torch.tensor(X).unsqueeze(0).to(self.device)  # (1, T, F)

        # Enable dropout for MC sampling
        self._model.train()
        with torch.no_grad():
            samples = [
                self._model(tensor).cpu().item()
                for _ in range(mc_samples)
            ]
        self._model.eval()

        arr = np.array(samples)
        return {
            "rul_mean": float(np.mean(arr)),
            "rul_std": float(np.std(arr)),
            "rul_lower": float(np.percentile(arr, 5)),
            "rul_upper": float(np.percentile(arr, 95)),
        }


# ==================================================================
# NASA scoring function
# ==================================================================
def _nasa_score(predicted: np.ndarray, actual: np.ndarray) -> float:
    """
    NASA asymmetric scoring function for RUL estimation:
    penalises late predictions more heavily than early ones.
    """
    diff = predicted - actual
    score = np.where(
        diff < 0,
        np.exp(-diff / 13) - 1,
        np.exp(diff / 10) - 1
    )
    return float(np.sum(score))

