from pydantic import Field

from app.api.schemas.common import CamelModel, PatientIn


class GenerateRequest(CamelModel):
    n: int = Field(ge=1)
    seed: int | None = None


class PatientsOut(CamelModel):
    patients: list[PatientIn]


class GenerateResponse(PatientsOut):
    seed: int


class ExportRequest(CamelModel):
    patients: list[PatientIn] = Field(min_length=1)
