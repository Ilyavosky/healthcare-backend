from pydantic import BaseModel, ConfigDict, Field, StrictInt
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel, populate_by_name=True, str_strip_whitespace=True
    )


class PatientIn(CamelModel):
    id: str = Field(min_length=1, max_length=40)
    level: StrictInt = Field(ge=1, le=5)
    wait: StrictInt
    duration: StrictInt = Field(gt=0)


class StepOut(CamelModel):
    patient: str
    level: int
    doctor: int
    start: int
    end: int
    delay: int
    penalty: int
    after_goal: bool


class AlertOut(CamelModel):
    patient: str
    code: str
    minutes: int


class ErrorOut(CamelModel):
    code: str
    message: str
    field: str | None = None
