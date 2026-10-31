from fastapi import APIRouter

from app.api.dependencies import SettingsDep
from app.api.mappers import to_problem, to_solve_response
from app.api.schemas.solve import SolveRequest, SolveResponse
from app.services.solve_service import solve

router = APIRouter(tags=["solve"])


@router.post("/solve", response_model=SolveResponse)
def solve_problem(body: SolveRequest, settings: SettingsDep) -> SolveResponse:
    problem = to_problem(body)
    limit = (
        settings.search_time_limit_ms
        if body.time_limit_ms is None
        else body.time_limit_ms
    )
    outcome = solve(
        problem,
        body.algorithms,
        include_trace=body.include_trace,
        trace_limit=settings.trace_limit,
        time_limit_ms=limit or None,
        fallback_weights=tuple(settings.fallback_weights)
        if body.allow_approximate
        else (),
    )
    return to_solve_response(problem, outcome)
