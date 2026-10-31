import pytest

from app.domain.errors import DomainError, ErrorCode
from app.search.generator import (
    CSV_COLUMNS,
    DURATION_RANGES,
    LEVEL_PROBABILITIES,
    WAIT_RANGES,
    generate_patients,
    patients_from_csv,
    patients_to_csv,
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


def test_csv_round_trip():
    patients = generate_patients(15, 4)
    text = patients_to_csv(patients)
    assert text.splitlines()[0] == ",".join(CSV_COLUMNS)
    assert patients_from_csv(text) == patients


def test_csv_accepts_spaces_bom_and_any_column_order():
    text = "﻿duration, level ,patient_id,wait\n 20 , 2 , P1 , 5 \n5,3,P2,40\n"
    patients = patients_from_csv(text)
    assert [(p.patient_id, p.level, p.wait, p.duration) for p in patients] == [
        ("P1", 2, 5, 20),
        ("P2", 3, 40, 5),
    ]


@pytest.mark.parametrize(
    "text, fragment",
    [
        ("", "columnas"),
        ("patient_id,level,wait\nP1,2,5\n", "columnas"),
        ("patient_id,level,wait,duration\n", "no tiene pacientes"),
        ("patient_id,level,wait,duration\nP1,9,5,20\n", "Fila 2"),
        ("patient_id,level,wait,duration\nP1,2,5,0\n", "Fila 2"),
        ("patient_id,level,wait,duration\nP1,2,5,20\nP2,x,1,5\n", "Fila 3"),
        ("patient_id,level,wait,duration\n,2,5,20\n", "falta el id"),
    ],
)
def test_invalid_csv(text, fragment):
    with pytest.raises(DomainError) as error:
        patients_from_csv(text)
    assert error.value.code == ErrorCode.INVALID_CSV
    assert error.value.field == "csv"
    assert fragment in error.value.message
