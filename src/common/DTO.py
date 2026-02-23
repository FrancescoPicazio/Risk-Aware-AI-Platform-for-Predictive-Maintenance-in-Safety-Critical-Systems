"""
CMAPSS Data Loader Module
Handles loading and preprocessing of NASA C-MAPSS turbofan engine dataset
"""

import pandas as pd
from pathlib import Path
from typing import Tuple, Dict, List


class CMAPSSDataLoader:
    """
    Load and prepare CMAPSS dataset for training and testing.

    Supports all 4 subsets:
    - FD001: Single operating condition, single fault mode (HPC degradation)
    - FD002: Six operating conditions, single fault mode (HPC degradation)
    - FD003: Single operating condition, two fault modes (HPC + Fan degradation)
    - FD004: Six operating conditions, two fault modes (HPC + Fan degradation)
    """

    def __init__(self, data_dir: str = "data"):
        """
        Initialize data loader.

        Args:
            data_dir: Path to directory containing CMAPSS data files
        """
        self.data_dir = Path(data_dir)

        # Column names as per DATASET.md documentation
        self.sensor_cols = [f"sensor_{i}" for i in range(1, 22)]  # 21 sensors
        self.setting_cols = ["setting_1", "setting_2", "setting_3"]
        self.index_cols = ["unit", "time"]

        self.all_cols = self.index_cols + self.setting_cols + self.sensor_cols

    def load_train_data(self, subset: str = "FD001") -> pd.DataFrame:
        """
        Load training data for specified subset.

        Args:
            subset: Dataset subset (FD001, FD002, FD003, FD004)

        Returns:
            DataFrame with training data including calculated RUL
        """
        file_path = self.data_dir / f"train_{subset}.txt"

        if not file_path.exists():
            raise FileNotFoundError(f"Training file not found: {file_path}")

        # Load data - space-separated, no header
        df = pd.read_csv(file_path, sep=r"\s+", header=None, names=self.all_cols)

        # Calculate and add RUL (Remaining Useful Life)
        df = self._add_rul(df)

        return df

    def load_test_data(self, subset: str = "FD001") -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        Load test data and ground truth RUL for specified subset.

        Args:
            subset: Dataset subset (FD001, FD002, FD003, FD004)

        Returns:
            Tuple of (test_dataframe, rul_ground_truth_dataframe)
        """
        test_path = self.data_dir / f"test_{subset}.txt"
        rul_path = self.data_dir / f"RUL_{subset}.txt"

        if not test_path.exists():
            raise FileNotFoundError(f"Test file not found: {test_path}")
        if not rul_path.exists():
            raise FileNotFoundError(f"RUL file not found: {rul_path}")

        # Load test data
        df_test = pd.read_csv(test_path, sep=r"\s+", header=None, names=self.all_cols)

        # Load ground truth RUL
        rul_true = pd.read_csv(rul_path, sep=r"\s+", header=None, names=["RUL"])
        rul_true["unit"] = rul_true.index + 1  # Add unit numbers (1-indexed)

        return df_test, rul_true

    def _add_rul(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate Remaining Useful Life (RUL) for each observation in training data.

        RUL = max_cycle_of_engine - current_cycle

        Args:
            df: Training dataframe

        Returns:
            DataFrame with added RUL column
        """
        # Find maximum cycle (failure point) for each engine
        max_cycles = df.groupby("unit")["time"].max().reset_index()
        max_cycles.columns = ["unit", "max_cycle"]

        # Merge and calculate RUL
        df = df.merge(max_cycles, on="unit", how="left")
        df["RUL"] = df["max_cycle"] - df["time"]
        df = df.drop(columns=["max_cycle"])

        return df

    def load_all_subsets(self, data_type: str = "train") -> Dict[str, pd.DataFrame]:
        """
        Load all four dataset subsets at once.

        Args:
            data_type: Either 'train' or 'test'

        Returns:
            Dictionary mapping subset name to DataFrame
        """
        subsets = ["FD001", "FD002", "FD003", "FD004"]
        data = {}

        for subset in subsets:
            try:
                if data_type == "train":
                    data[subset] = self.load_train_data(subset)
                elif data_type == "test":
                    df_test, rul_true = self.load_test_data(subset)
                    data[subset] = (df_test, rul_true)
                else:
                    raise ValueError(f"Invalid data_type: {data_type}. Use 'train' or 'test'.")
            except FileNotFoundError as e:
                print(f"Warning: Could not load {subset} - {e}")

        return data

    def get_dataset_info(self) -> Dict[str, Dict]:
        """
        Get information about all available datasets.

        Returns:
            Dictionary with dataset characteristics
        """
        info = {
            "FD001": {
                "conditions": "ONE (Sea Level)",
                "fault_modes": "ONE (HPC Degradation)",
                "train_trajectories": 100,
                "test_trajectories": 100
            },
            "FD002": {
                "conditions": "SIX",
                "fault_modes": "ONE (HPC Degradation)",
                "train_trajectories": 260,
                "test_trajectories": 259
            },
            "FD003": {
                "conditions": "ONE (Sea Level)",
                "fault_modes": "TWO (HPC Degradation, Fan Degradation)",
                "train_trajectories": 100,
                "test_trajectories": 100
            },
            "FD004": {
                "conditions": "SIX",
                "fault_modes": "TWO (HPC Degradation, Fan Degradation)",
                "train_trajectories": 248,
                "test_trajectories": 249
            }
        }
        return info

