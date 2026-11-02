import random

from fastapi import APIRouter

from app.api.mappers import to_patient_in
from app.api.schemas.scenarios import GenerateRequest, GenerateResponse
from app.search.generator import generate_patients

router = APIRouter(prefix="/scenarios", tags=["scenarios"])


@router.post("/generate", response_model=GenerateResponse)
def generate(body: GenerateRequest) -> GenerateResponse:
    seed = (
        body.seed if body.seed is not None else random.SystemRandom().randrange(10**9)
    )
    patients = generate_patients(body.n, seed)
    return GenerateResponse(seed=seed, patients=[to_patient_in(p) for p in patients])
