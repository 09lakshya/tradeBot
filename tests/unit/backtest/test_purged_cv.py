"""Unit tests for Purged K-Fold Cross Validation."""
from datetime import date, timedelta
import pytest

from app.domains.backtest.purged_cv import PurgedCrossValidation


def test_purged_cross_validation_folds():
    start = date(2023, 1, 1)
    dates = [start + timedelta(days=i) for i in range(100)]

    folds = PurgedCrossValidation.get_purged_folds(
        unique_dates=dates,
        n_splits=5,
        purge_window_days=3,
        embargo_pct=0.02,
    )

    assert len(folds) == 5

    for fold in folds:
        test_s, test_e = fold.test_range
        assert test_s >= dates[0]
        assert test_e <= dates[-1]

        for train_s, train_e in fold.train_ranges:
            assert train_e < test_s or train_s > test_e
