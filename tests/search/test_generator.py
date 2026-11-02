import pytest

from app.domain.errors import DomainError
from app.search.generator import (
    DURATION_RANGES,
    LEVEL_PROBABILITIES,
    WAIT_RANGES,
    generate_patients,
)


def test_same_seed_same_patients():
    assert generate_patients(20, 7) == generate_patients(20, 7)


def test_different_seed_changes_patients():
    assert generate_patients(20, 7) != generate_patients(20, 8)


def test_ids_are_sequential():
    assert [p.patient_id for p in generate_patients(5, 1)] == [
        "P1",
        "P2",
        "P3",
        "P4",
        "P5",
    ]


@pytest.mark.parametrize("seed", range(1, 21))
def test_values_are_within_ranges(seed):
    for p in generate_patients(40, seed):
        assert p.level in LEVEL_PROBABILITIES
        low, high = WAIT_RANGES[p.level]
        assert low <= p.wait <= high
        low, high = DURATION_RANGES[p.level]
        assert low <= p.duration <= high


def test_any_size_is_allowed():
    assert len(generate_patients(500, 3)) == 500


def test_level_three_is_most_common():
    levels = [p.level for p in generate_patients(2000, 11)]
    counts = {level: levels.count(level) for level in LEVEL_PROBABILITIES}
    assert max(counts, key=counts.get) == 3
    assert min(counts, key=counts.get) == 1


@pytest.mark.parametrize("n", [0, -3])
def test_needs_at_least_one_patient(n):
    with pytest.raises(DomainError) as error:
        generate_patients(n, 1)
    assert error.value.field == "n"
