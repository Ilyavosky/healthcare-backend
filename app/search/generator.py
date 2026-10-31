import csv
import io
import random

from app.domain.errors import DomainError, ErrorCode
from app.domain.patient import Patient

LEVEL_PROBABILITIES: dict[int, int] = {1: 1, 2: 2, 3: 4, 4: 3, 5: 2}
WAIT_RANGES: dict[int, tuple[int, int]] = {
    1: (0, 10),
    2: (0, 30),
    3: (10, 90),
    4: (20, 150),
    5: (30, 200),
}
DURATION_RANGES: dict[int, tuple[int, int]] = {
    1: (25, 45),
    2: (15, 35),
    3: (10, 25),
    4: (5, 15),
    5: (5, 10),
}
CSV_COLUMNS: tuple[str, ...] = ("patient_id", "level", "wait", "duration")


def generate_patients(n: int, seed: int) -> list[Patient]:
    if n < 1:
        raise DomainError(
            ErrorCode.INVALID_PATIENT, "Debe haber al menos 1 paciente", "n"
        )
    rng = random.Random(seed)
    levels = list(LEVEL_PROBABILITIES)
    weights = list(LEVEL_PROBABILITIES.values())
    patients = []
    for i in range(1, n + 1):
        level = rng.choices(levels, weights)[0]
        wait = rng.randint(*WAIT_RANGES[level])
        duration = rng.randint(*DURATION_RANGES[level])
        patients.append(Patient(f"P{i}", level, wait, duration))
    return patients


def patients_to_csv(patients: list[Patient]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(CSV_COLUMNS)
    for p in patients:
        writer.writerow((p.patient_id, p.level, p.wait, p.duration))
    return buffer.getvalue()


def patients_from_csv(text: str) -> list[Patient]:
    reader = csv.DictReader(io.StringIO(text.lstrip("﻿")))
    if reader.fieldnames is None or set(CSV_COLUMNS) - {
        name.strip() for name in reader.fieldnames
    }:
        raise DomainError(
            ErrorCode.INVALID_CSV,
            f"El CSV debe tener las columnas {', '.join(CSV_COLUMNS)}",
            "csv",
        )
    patients = []
    for row_number, row in enumerate(reader, start=2):
        values = {key.strip(): (value or "").strip() for key, value in row.items()}
        try:
            patient = Patient(
                values["patient_id"],
                int(values["level"]),
                int(values["wait"]),
                int(values["duration"]),
            )
        except ValueError as error:
            message = (
                error.message
                if isinstance(error, DomainError)
                else "level, wait y duration deben ser números enteros"
            )
            raise DomainError(
                ErrorCode.INVALID_CSV, f"Fila {row_number}: {message}", "csv"
            ) from error
        if not patient.patient_id:
            raise DomainError(
                ErrorCode.INVALID_CSV, f"Fila {row_number}: falta el id", "csv"
            )
        patients.append(patient)
    if not patients:
        raise DomainError(ErrorCode.INVALID_CSV, "El CSV no tiene pacientes", "csv")
    return patients
