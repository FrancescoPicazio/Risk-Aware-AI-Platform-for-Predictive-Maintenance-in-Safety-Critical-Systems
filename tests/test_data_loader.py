"""
Unit tests for CMAPSS Data Loader
"""

import sys
sys.path.append('..')

from src.data_ingestion.data_ingestion_layer import CMAPSSDataLoader
import pandas as pd


def test_load_train_data():
    """Test loading training data."""
    print("\n" + "="*70)
    print("TEST 1: Loading Training Data")
    print("="*70)

    loader = CMAPSSDataLoader(data_dir='../data')

    try:
        df = loader.load_train_data("FD001")

        assert not df.empty, "DataFrame should not be empty"
        assert "RUL" in df.columns, "RUL column should exist"
        assert "unit" in df.columns, "unit column should exist"
        assert "time" in df.columns, "time column should exist"

        n_engines = df["unit"].nunique()
        print("Train data loaded successfully")
        print(f"   - Rows: {len(df):,}")
        print(f"   - Engines: {n_engines}")
        print(f"   - Columns: {len(df.columns)}")
        print(f"   - RUL range: [{df['RUL'].min()}, {df['RUL'].max()}]")

        return True
    except Exception as e:
        print(f"Test failed: {e}")
        return False


def test_load_test_data():
    """Test loading test data."""
    print("\n" + "="*70)
    print("TEST 2: Loading Test Data")
    print("="*70)

    loader = CMAPSSDataLoader(data_dir='../data')

    try:
        df_test, rul_true = loader.load_test_data("FD001")

        assert not df_test.empty, "Test DataFrame should not be empty"
        assert not rul_true.empty, "RUL DataFrame should not be empty"
        assert len(rul_true) == df_test["unit"].nunique(), "RUL count should match engine count"

        print("Test data loaded successfully")
        print(f"   - Test rows: {len(df_test):,}")
        print(f"   - Test engines: {df_test['unit'].nunique()}")
        print(f"   - RUL ground truth entries: {len(rul_true)}")

        return True
    except Exception as e:
        print(f"Test failed: {e}")
        return False


def test_load_all_subsets():
    """Test loading all subsets."""
    print("\n" + "="*70)
    print("TEST 3: Loading All Subsets")
    print("="*70)

    loader = CMAPSSDataLoader(data_dir='../data')

    try:
        all_data = loader.load_all_subsets(data_type='train')

        expected_subsets = ["FD001", "FD002", "FD003", "FD004"]

        print("All subsets loaded successfully")
        for subset in expected_subsets:
            if subset in all_data:
                df = all_data[subset]
                print(f"   - {subset}: {len(df):,} rows, {df['unit'].nunique()} engines")

        return True
    except Exception as e:
        print(f"Test failed: {e}")
        return False


def test_rul_calculation():
    """Test RUL calculation correctness."""
    print("\n" + "="*70)
    print("TEST 4: RUL Calculation Correctness")
    print("="*70)

    loader = CMAPSSDataLoader(data_dir='../data')

    try:
        df = loader.load_train_data("FD001")

        # Check RUL for first engine
        engine_1 = df[df['unit'] == 1].sort_values('time')

        # RUL should start at max and decrease to 0
        assert engine_1['RUL'].iloc[0] == engine_1['RUL'].max(), "First RUL should be maximum"
        assert engine_1['RUL'].iloc[-1] == 0, "Last RUL should be 0 (failure point)"

        # RUL should decrease monotonically
        rul_diff = engine_1['RUL'].diff().dropna()
        assert all(rul_diff == -1), "RUL should decrease by 1 each cycle"

        print("RUL calculation is correct")
        print(f"   - Engine 1 lifecycle: {len(engine_1)} cycles")
        print(f"   - Initial RUL: {engine_1['RUL'].iloc[0]}")
        print(f"   - Final RUL: {engine_1['RUL'].iloc[-1]}")

        return True
    except Exception as e:
        print(f"Test failed: {e}")
        return False


def test_dataset_info():
    """Test dataset info retrieval."""
    print("\n" + "="*70)
    print("TEST 5: Dataset Information")
    print("="*70)

    loader = CMAPSSDataLoader(data_dir='../data')

    try:
        info = loader.get_dataset_info()

        assert len(info) == 4, "Should have info for 4 subsets"

        print("Dataset info retrieved successfully")
        for subset, details in info.items():
            print(f"\n   {subset}:")
            print(f"      Conditions: {details['conditions']}")
            print(f"      Fault Modes: {details['fault_modes']}")
            print(f"      Train/Test: {details['train_trajectories']}/{details['test_trajectories']}")

        return True
    except Exception as e:
        print(f"Test failed: {e}")
        return False


def run_all_tests():
    """Run all tests and report results."""
    print("\n" + "="*70)
    print("RUNNING DATA LOADER TESTS")
    print("="*70)

    tests = [
        test_load_train_data,
        test_load_test_data,
        test_load_all_subsets,
        test_rul_calculation,
        test_dataset_info
    ]

    results = []
    for test in tests:
        try:
            result = test()
            results.append(result)
        except Exception as e:
            print(f"Test crashed: {e}")
            results.append(False)

    # Summary
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)
    passed = sum(results)
    total = len(results)
    print(f"\nPassed: {passed}/{total}")

    if passed == total:
        print("\nALL TESTS PASSED!")
    else:
        print(f"\n{total - passed} test(s) failed")

    print("="*70 + "\n")


if __name__ == "__main__":
    run_all_tests()

