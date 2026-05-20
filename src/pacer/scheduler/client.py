import httpx
from pacer.config import get_settings


def post_system_event(event_type: str, student_id: int, payload: dict | None = None):
    settings = get_settings()
    # PACER_HOST may be 0.0.0.0 for binding; outbound calls must hit a real address.
    host = "127.0.0.1" if settings.host in ("0.0.0.0", "::", "") else settings.host
    url = f"http://{host}:{settings.port}/internal/system-event"
    httpx.post(
        url,
        json={"type": event_type, "student_id": student_id, "payload": payload or {}},
        headers={"X-Internal-Token": settings.internal_token},
        timeout=30.0,
    )
