import pytest

from ytm_import.config import ImportConfig


@pytest.mark.parametrize(
    "kwargs",
    [
        {"privacy": "INVALID"},
        {"min_score": -0.1},
        {"min_score": 1.1},
        {"min_score": float("nan")},
        {"search_delay": -0.1},
        {"max_retries": 0},
    ],
)
def test_invalid_settings_are_rejected(kwargs):
    with pytest.raises(ValueError):
        ImportConfig(**kwargs)
