import asyncio
import threading
from functools import partial

from fastapi import APIRouter, Request, Response
from starlette.concurrency import run_in_threadpool

from app.api.dependencies import SettingsDep
from app.api.mappers import to_problem, to_solve_response
from app.api.schemas.solve import SolveRequest, SolveResponse
from app.search.engine import SearchCancelledError
from app.services.solve_service import solve

router = APIRouter(tags=["solve"])

CLIENT_CLOSED_REQUEST = 499
DISCONNECT_POLL_SECONDS = 0.1


async def run_until_disconnected(request: Request, work, cancelled: threading.Event):
    task = asyncio.ensure_future(run_in_threadpool(work))
    while not task.done():
        done, _ = await asyncio.wait({task}, timeout=DISCONNECT_POLL_SECONDS)
        if not done and await request.is_disconnected():
            cancelled.set()
    return task.result()


@router.post("/solve", response_model=SolveResponse)
async def solve_problem(
    request: Request, body: SolveRequest, settings: SettingsDep
) -> SolveResponse | Response:
    problem = to_problem(body)
    limit = (
        settings.search_time_limit_ms
        if body.time_limit_ms is None
        else body.time_limit_ms
    )
    cancelled = threading.Event()
    work = partial(
        solve,
        problem,
        body.algorithms,
        include_trace=body.include_trace,
        trace_limit=min(
            body.trace_limit or settings.trace_limit, settings.max_trace_limit
        ),
        time_limit_ms=limit or None,
        fallback_weights=tuple(settings.fallback_weights)
        if body.allow_approximate
        else (),
        should_stop=cancelled.is_set,
    )
    try:
        outcome = await run_until_disconnected(request, work, cancelled)
    except SearchCancelledError:
        return Response(status_code=CLIENT_CLOSED_REQUEST)
    return to_solve_response(problem, outcome)
