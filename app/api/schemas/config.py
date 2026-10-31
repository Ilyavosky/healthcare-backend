from app.api.schemas.common import CamelModel


class LevelOut(CamelModel):
    level: int
    name: str
    weight: int
    limit: int


class DefaultsOut(CamelModel):
    doctors: int
    t0: int
    critical_first: bool
    time_limit_ms: int
    allow_approximate: bool
    fallback_weights: list[float]
    near_limit_margin: int


class ConfigOut(CamelModel):
    levels: list[LevelOut]
    goal_types: list[str]
    algorithms: list[str]
    alert_codes: list[str]
    csv_columns: list[str]
    defaults: DefaultsOut
