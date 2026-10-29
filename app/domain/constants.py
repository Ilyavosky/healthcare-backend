LEVEL_WEIGHTS: dict[int, int] = {1: 16, 2: 8, 3: 4, 4: 2, 5: 1}

LEVEL_LIMITS: dict[int, int] = {1: 0, 2: 10, 3: 60, 4: 120, 5: 240}
LEVEL_NAMES: dict[int, str] = {
    1: "Crítico",
    2: "Muy urgente",
    3: "Urgente",
    4: "Poco urgente",
    5: "No urgente",
}

MIN_LEVEL: int = 1
MAX_LEVEL: int = 5

CRITICAL_MAX_LEVEL: int = 2
MAX_PATIENTS: int = 15
NEAR_LIMIT_MARGIN: int = 10

GOAL_NODE: str = "META"
