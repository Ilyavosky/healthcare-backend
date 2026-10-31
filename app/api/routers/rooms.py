from uuid import UUID

from fastapi import APIRouter, Response, status

from app.api.dependencies import RoomServiceDep, SettingsDep
from app.api.mappers import (
    to_goal,
    to_patient_out,
    to_room_detail_out,
    to_room_out,
    to_room_solve_response,
    to_solve_detail_out,
    to_solve_summary_out,
)
from app.api.schemas.rooms import (
    AttendRequest,
    PatientCreate,
    PatientOut,
    PatientUpdate,
    RoomCreate,
    RoomDetailOut,
    RoomOut,
    RoomSolveRequest,
    RoomSolveResponse,
    RoomUpdate,
    SolveDetailOut,
    SolveSummaryOut,
)
from app.domain.errors import DomainError, ErrorCode
from app.services.room_service import SolveOptions

router = APIRouter(prefix="/rooms", tags=["rooms"])


@router.post("", response_model=RoomOut, status_code=status.HTTP_201_CREATED)
def create_room(body: RoomCreate, service: RoomServiceDep) -> RoomOut:
    return to_room_out(
        service.create_room(body.name, body.shift_started_at, body.doctors)
    )


@router.get("", response_model=list[RoomOut])
def list_rooms(service: RoomServiceDep) -> list[RoomOut]:
    return [to_room_out(room) for room in service.list_rooms()]


@router.get("/{room_id}", response_model=RoomDetailOut)
def get_room(room_id: UUID, service: RoomServiceDep) -> RoomDetailOut:
    room, patients = service.get_room(room_id)
    try:
        snapshot = service.snapshot(room_id)
    except DomainError as error:
        if error.code != ErrorCode.SHIFT_NOT_STARTED:
            raise
        snapshot = None
    return to_room_detail_out(room, patients, snapshot)


@router.patch("/{room_id}", response_model=RoomOut)
def update_room(room_id: UUID, body: RoomUpdate, service: RoomServiceDep) -> RoomOut:
    changes = body.model_dump(exclude_unset=True, exclude_none=True)
    return to_room_out(service.update_room(room_id, changes))


@router.delete("/{room_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_room(room_id: UUID, service: RoomServiceDep) -> Response:
    service.delete_room(room_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{room_id}/patients",
    response_model=PatientOut,
    status_code=status.HTTP_201_CREATED,
)
def add_patient(
    room_id: UUID, body: PatientCreate, service: RoomServiceDep
) -> PatientOut:
    patient = service.add_patient(
        room_id, body.label, body.level, body.duration_min, body.arrived_at
    )
    return to_patient_out(patient)


@router.patch("/{room_id}/patients/{patient_id}", response_model=PatientOut)
def update_patient(
    room_id: UUID, patient_id: UUID, body: PatientUpdate, service: RoomServiceDep
) -> PatientOut:
    changes = body.model_dump(exclude_unset=True)
    for key in ("label", "level", "duration_min", "arrived_at"):
        if key in changes and changes[key] is None:
            raise DomainError(
                ErrorCode.INVALID_PATIENT, "Este campo no puede ser nulo", key
            )
    return to_patient_out(service.update_patient(room_id, patient_id, changes))


@router.post("/{room_id}/patients/{patient_id}/attend", response_model=PatientOut)
def attend_patient(
    room_id: UUID, patient_id: UUID, body: AttendRequest, service: RoomServiceDep
) -> PatientOut:
    return to_patient_out(
        service.attend_patient(room_id, patient_id, body.doctor, body.at)
    )


@router.delete(
    "/{room_id}/patients/{patient_id}", status_code=status.HTTP_204_NO_CONTENT
)
def delete_patient(
    room_id: UUID, patient_id: UUID, service: RoomServiceDep
) -> Response:
    service.delete_patient(room_id, patient_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{room_id}/solve",
    response_model=RoomSolveResponse,
    status_code=status.HTTP_201_CREATED,
)
def solve_room(
    room_id: UUID,
    body: RoomSolveRequest,
    service: RoomServiceDep,
    settings: SettingsDep,
) -> RoomSolveResponse:
    limit = (
        settings.search_time_limit_ms
        if body.time_limit_ms is None
        else body.time_limit_ms
    )
    options = SolveOptions(
        algorithms=tuple(body.algorithms),
        critical_first=body.critical_first,
        include_trace=body.include_trace,
        trace_limit=settings.trace_limit,
        time_limit_ms=limit or None,
        fallback_weights=tuple(settings.fallback_weights)
        if body.allow_approximate
        else (),
    )
    result = service.solve_room(room_id, to_goal(body.goal), options, body.at)
    return to_room_solve_response(result)


@router.get("/{room_id}/solves", response_model=list[SolveSummaryOut])
def list_solves(room_id: UUID, service: RoomServiceDep) -> list[SolveSummaryOut]:
    return [to_solve_summary_out(s) for s in service.list_solves(room_id)]


@router.get("/{room_id}/solves/{solve_id}", response_model=SolveDetailOut)
def get_solve(room_id: UUID, solve_id: UUID, service: RoomServiceDep) -> SolveDetailOut:
    solve, results = service.get_solve(room_id, solve_id)
    return to_solve_detail_out(solve, results)
