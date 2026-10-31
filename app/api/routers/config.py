from fastapi import APIRouter

from app.api.dependencies import SettingsDep
from app.api.schemas.config import ConfigOut, DefaultsOut, LevelOut
from app.domain.constants import (
    LEVEL_LIMITS,
    LEVEL_NAMES,
    LEVEL_WEIGHTS,
    NEAR_LIMIT_MARGIN,
)
from app.domain.goal import GoalType
from app.search.generator import CSV_COLUMNS
from app.search.heuristics import AlgorithmName
from app.search.report import AlertCode

router = APIRouter(tags=["config"])


@router.get("/config", response_model=ConfigOut)
def read_config(settings: SettingsDep) -> ConfigOut:
    return ConfigOut(
        levels=[
            LevelOut(
                level=level,
                name=LEVEL_NAMES[level],
                weight=LEVEL_WEIGHTS[level],
                limit=LEVEL_LIMITS[level],
            )
            for level in sorted(LEVEL_NAMES)
        ],
        goal_types=[goal.value for goal in GoalType],
        algorithms=[name.value for name in AlgorithmName],
        alert_codes=[code.value for code in AlertCode],
        csv_columns=list(CSV_COLUMNS),
        defaults=DefaultsOut(
            doctors=1,
            t0=0,
            critical_first=True,
            time_limit_ms=settings.search_time_limit_ms,
            allow_approximate=True,
            fallback_weights=settings.fallback_weights,
            near_limit_margin=NEAR_LIMIT_MARGIN,
        ),
    )
