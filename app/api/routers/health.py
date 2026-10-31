from fastapi import APIRouter

from app.api.dependencies import SettingsDep

router = APIRouter(tags=["health"])


@router.get("/health")
def health(settings: SettingsDep) -> dict[str, str]:
    configured = bool(
        settings.supabase_url and settings.supabase_service_role_key.get_secret_value()
    )
    return {
        "status": "ok",
        "database": "configured" if configured else "not_configured",
    }
