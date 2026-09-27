"""Notifications REST API — query and acknowledge regime-shift alerts."""

from fastapi import APIRouter, HTTPException, Query

from app.services.notification_service import (
    NotificationService,
    RecentNotificationsResponse,
)

router = APIRouter(prefix="/notifications", tags=["notifications"])

# Module-level singleton — set by main.py lifespan
_notification_service: NotificationService | None = None


def set_notification_service(svc: NotificationService) -> None:
    global _notification_service
    _notification_service = svc


def get_notification_service() -> NotificationService:
    if _notification_service is None:
        raise HTTPException(
            status_code=503,
            detail="Notification service not initialized",
        )
    return _notification_service


@router.get("", response_model=RecentNotificationsResponse)
async def list_notifications(
    limit: int = Query(default=50, ge=1, le=200),
) -> RecentNotificationsResponse:
    """Return the most recent unacknowledged notifications (newest first)."""
    svc = get_notification_service()
    items = svc.recent(limit=limit)
    return RecentNotificationsResponse(items=items)


@router.post("/{notification_id}/ack")
async def acknowledge_notification(
    notification_id: str,
) -> dict[str, bool]:
    """Mark a notification as acknowledged."""
    svc = get_notification_service()
    ok = svc.acknowledge(notification_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Notification not found")
    return {"ok": True}
