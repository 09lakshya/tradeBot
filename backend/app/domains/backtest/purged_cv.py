"""Purged K-Fold Cross-Validation and Embargo (López de Prado Methodology)."""
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta


@dataclass(frozen=True)
class PurgedCVFold:
    """A single Cross-Validation Fold with purged boundaries and embargo buffers."""
    fold_index: int
    train_ranges: list[tuple[date, date]]  # List of non-overlapping [start, end] date segments
    test_range: tuple[date, date]          # [start, end] date segment
    purged_ranges: list[tuple[date, date]]
    embargo_range: tuple[date, date] | None


class PurgedCrossValidation:
    """Generates Purged K-Fold splits with embargo buffers to eliminate look-ahead
    and serial correlation leakage across overlapping label horizons.
    """

    @staticmethod
    def get_purged_folds(
        unique_dates: Sequence[date],
        n_splits: int = 5,
        purge_window_days: int = 5,
        embargo_pct: float = 0.01,
    ) -> list[PurgedCVFold]:
        """Calculates exact date partition ranges for Purged K-Fold Cross Validation."""
        sorted_dates = sorted(unique_dates)
        total_dates = len(sorted_dates)
        if total_dates < (n_splits * 2):
            raise ValueError(f"Insufficient dates ({total_dates}) for {n_splits} purged CV splits.")

        chunk_size = total_dates // n_splits
        folds: list[PurgedCVFold] = []

        for fold_idx in range(n_splits):
            test_start_idx = fold_idx * chunk_size
            test_end_idx = (fold_idx + 1) * chunk_size if fold_idx < n_splits - 1 else total_dates
            
            test_start_date = sorted_dates[test_start_idx]
            test_end_date = sorted_dates[test_end_idx - 1]

            purged_ranges: list[tuple[date, date]] = []
            train_ranges: list[tuple[date, date]] = []

            # 1. Left Training Split (prior to test partition)
            if test_start_idx > 0:
                # Left split ends purge_window_days before test_start_date
                left_train_end = test_start_date - timedelta(days=purge_window_days)
                left_train_start = sorted_dates[0]
                if left_train_end >= left_train_start:
                    train_ranges.append((left_train_start, left_train_end))
                if purge_window_days > 0:
                    purged_ranges.append((left_train_end, test_start_date))

            # 2. Embargo Buffer & Right Training Split (after test partition)
            embargo_days = max(1, int(chunk_size * embargo_pct))
            embargo_end_date = test_end_date + timedelta(days=embargo_days)
            embargo_range = (test_end_date, embargo_end_date) if embargo_days > 0 else None

            if test_end_idx < total_dates:
                right_train_start = embargo_end_date + timedelta(days=1)
                right_train_end = sorted_dates[-1]
                if right_train_end >= right_train_start:
                    train_ranges.append((right_train_start, right_train_end))

            folds.append(
                PurgedCVFold(
                    fold_index=fold_idx,
                    train_ranges=train_ranges,
                    test_range=(test_start_date, test_end_date),
                    purged_ranges=purged_ranges,
                    embargo_range=embargo_range,
                )
            )

        return folds
