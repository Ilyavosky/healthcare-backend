from pydantic import Field, StrictInt

from app.api.schemas.common import CamelModel, PatientIn

MAX_GENERATED_PATIENTS = 100_000


class GenerateRequest(CamelModel):
    n: StrictInt = Field(ge=1, le=MAX_GENERATED_PATIENTS)
    seed: StrictInt | None = None


class GenerateResponse(CamelModel):
    seed: int
    patients: list[PatientIn]
