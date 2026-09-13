from ml.harness.evaluate import time_based_split


def test_split_is_chronological_and_disjoint() -> None:
    train, val, test = time_based_split(100, 0.7, 0.15)
    assert train == slice(0, 70)
    assert val == slice(70, 85)
    assert test == slice(85, 100)


def test_split_never_shuffles() -> None:
    """Regression guard for the single worst mistake available in this project."""
    train, val, test = time_based_split(1000)
    assert train.stop == val.start
    assert val.stop == test.start
