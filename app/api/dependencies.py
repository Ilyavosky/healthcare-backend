from typing import Annotated

from fastapi import Depends

from app.config import Settings, get_settings
from app.domain.errors import DomainError, ErrorCode
from app.infra.supabase_client import get_supabase_client
from app.infra.supabase_room_repository import SupabaseRoomRepository
from app.ports.room_repository import RoomRepository
from app.services.room_service import Clock, RoomService, utc_now

SettingsDep = Annotated[Settings, Depends(get_settings)]


def get_clock() -> Clock:
    return utc_now


def get_room_repository(settings: SettingsDep) -> RoomRepository:
    key = settings.supabase_service_role_key.get_secret_value()
    if not settings.supabase_url or not key:
        raise DomainError(
            ErrorCode.DATABASE_NOT_CONFIGURED,
            "Falta configurar SUPABASE_URL y SUPABASE_SERVICE_ROLE_KEY en el .env",
        )
    return SupabaseRoomRepository(get_supabase_client(settings.supabase_url, key))


def get_room_service(
    repository: Annotated[RoomRepository, Depends(get_room_repository)],
    clock: Annotated[Clock, Depends(get_clock)],
) -> RoomService:
    return RoomService(repository, clock)


RoomServiceDep = Annotated[RoomService, Depends(get_room_service)]
