import random

from fastapi import APIRouter, UploadFile
from fastapi.responses import Response

from app.api.dependencies import SettingsDep
from app.api.mappers import to_patient, to_patient_in
from app.api.schemas.scenarios import (
    ExportRequest,
    GenerateRequest,
    GenerateResponse,
    PatientsOut,
)
from app.domain.errors import DomainError, ErrorCode
from app.search.generator import generate_patients, patients_from_csv, patients_to_csv

router = APIRouter(prefix="/scenarios", tags=["scenarios"])


@router.post("/generate", response_model=GenerateResponse)
def generate(body: GenerateRequest) -> GenerateResponse:
    seed = (
        body.seed if body.seed is not None else random.SystemRandom().randrange(10**9)
    )
    patients = generate_patients(body.n, seed)
    return GenerateResponse(seed=seed, patients=[to_patient_in(p) for p in patients])


@router.post("/csv", response_model=PatientsOut)
async def import_csv(file: UploadFile, settings: SettingsDep) -> PatientsOut:
    content = await file.read(settings.max_csv_bytes + 1)
    if len(content) > settings.max_csv_bytes:
        raise DomainError(
            ErrorCode.INVALID_CSV, "El archivo es demasiado grande", "csv"
        )
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as error:
        raise DomainError(
            ErrorCode.INVALID_CSV, "El archivo debe estar en UTF-8", "csv"
        ) from error
    return PatientsOut(patients=[to_patient_in(p) for p in patients_from_csv(text)])


@router.post("/csv/export")
def export_csv(body: ExportRequest) -> Response:
    patients = [to_patient(p, i) for i, p in enumerate(body.patients)]
    return Response(
        content=patients_to_csv(patients),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="escenario.csv"'},
    )
