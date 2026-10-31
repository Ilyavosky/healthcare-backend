from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.domain.errors import DomainError, ErrorCode

STATUS_BY_CODE: dict[ErrorCode, int] = {
    ErrorCode.ROOM_NOT_FOUND: 404,
    ErrorCode.PATIENT_NOT_FOUND: 404,
    ErrorCode.SOLVE_NOT_FOUND: 404,
    ErrorCode.DUPLICATE_LABEL: 409,
    ErrorCode.ROOM_CLOSED: 409,
    ErrorCode.DATABASE_NOT_CONFIGURED: 503,
    ErrorCode.DATABASE_ERROR: 503,
}
FIELD_NAMES: dict[str, str] = {
    "doctors_free_at": "start.doctorsFreeAt",
    "csv": "file",
    "duration_min": "durationMin",
    "arrived_at": "arrivedAt",
    "attended_at": "attendedAt",
    "shift_started_at": "shiftStartedAt",
}
VALIDATION_MESSAGES: dict[str, str] = {
    "missing": "Falta este campo",
    "int_type": "Debe ser un número entero",
    "int_parsing": "Debe ser un número entero",
    "int_from_float": "Debe ser un número entero",
    "float_type": "Debe ser un número",
    "float_parsing": "Debe ser un número",
    "string_type": "Debe ser texto",
    "string_too_short": "No puede estar vacío",
    "string_too_long": "Es demasiado largo",
    "bool_type": "Debe ser verdadero o falso",
    "bool_parsing": "Debe ser verdadero o falso",
    "list_type": "Debe ser una lista",
    "too_short": "La lista no puede estar vacía",
    "enum": "Valor no permitido",
    "literal_error": "Valor no permitido",
    "json_invalid": "El JSON no es válido",
    "uuid_parsing": "Debe ser un UUID válido",
    "uuid_type": "Debe ser un UUID válido",
    "datetime_parsing": "Debe ser una fecha y hora ISO 8601",
    "datetime_type": "Debe ser una fecha y hora ISO 8601",
    "datetime_from_date_parsing": "Debe ser una fecha y hora ISO 8601",
    "timezone_aware": "La fecha debe incluir zona horaria (por ejemplo -06:00)",
    "model_type": "Debe ser un objeto",
    "model_attributes_type": "Debe ser un objeto",
}
LIMIT_MESSAGES: dict[str, str] = {
    "greater_than": "Debe ser mayor que {gt}",
    "greater_than_equal": "Debe ser mayor o igual que {ge}",
    "less_than": "Debe ser menor que {lt}",
    "less_than_equal": "Debe ser menor o igual que {le}",
}


def error_body(code: str, message: str, field: str | None) -> dict:
    return {"code": code, "message": message, "field": field}


def field_path(loc: tuple) -> str | None:
    parts = [part for part in loc if part not in ("body", "query", "path")]
    path = ""
    for part in parts:
        if isinstance(part, int):
            path += f"[{part}]"
        else:
            path += f".{part}" if path else str(part)
    return path or None


def validation_message(error: dict) -> str:
    kind = error.get("type", "")
    if kind in LIMIT_MESSAGES:
        return LIMIT_MESSAGES[kind].format(**error.get("ctx", {}))
    return VALIDATION_MESSAGES.get(kind, "Valor inválido")


async def domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
    field = FIELD_NAMES.get(exc.field, exc.field) if exc.field else None
    return JSONResponse(
        status_code=STATUS_BY_CODE.get(exc.code, 422),
        content=error_body(exc.code.value, exc.message, field),
    )


async def validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    first = exc.errors()[0]
    return JSONResponse(
        status_code=422,
        content=error_body(
            "VALIDATION_ERROR",
            validation_message(first),
            field_path(tuple(first["loc"])),
        ),
    )


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(DomainError, domain_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
