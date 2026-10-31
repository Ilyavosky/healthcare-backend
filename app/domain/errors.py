from enum import Enum


class ErrorCode(str, Enum):
    INVALID_PATIENT = "INVALID_PATIENT"
    DUPLICATE_PATIENT_ID = "DUPLICATE_PATIENT_ID"
    UNKNOWN_PATIENT = "UNKNOWN_PATIENT"
    INVALID_GOAL_VALUE = "INVALID_GOAL_VALUE"
    PATIENT_NOT_ARRIVED = "PATIENT_NOT_ARRIVED"
    NO_PENDING_PATIENTS = "NO_PENDING_PATIENTS"
    INVALID_DOCTORS = "INVALID_DOCTORS"
    ROOM_NOT_FOUND = "ROOM_NOT_FOUND"
    PATIENT_NOT_FOUND = "PATIENT_NOT_FOUND"
    DUPLICATE_LABEL = "DUPLICATE_LABEL"


class DomainError(ValueError):
    def __init__(self, code: ErrorCode, message: str, field: str | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.field = field
