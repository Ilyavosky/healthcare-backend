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
