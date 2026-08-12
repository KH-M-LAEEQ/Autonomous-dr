from ml.harness.evaluate import time_based_split


def test_split_is_chronological_and_disjoint() -> None:
    train, test = time_based_split(100, 0.7)
    assert train == slice(0, 70)
    assert test == slice(70, 100)


def test_split_never_shuffles() -> None:
    """Regression guard for the single worst mistake available in this project."""
    train, test = time_based_split(1000)
    assert train.stop == test.start
