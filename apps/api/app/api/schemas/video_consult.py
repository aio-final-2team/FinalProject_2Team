"""[제안][선택] T56 room 응답이에요. WebSocket 계약은 T13 v0.8을 따라요."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class VideoRoom(BaseModel):
    booking_id: UUID
    opens_at: datetime
    closes_at: datetime
    ice_servers: list[dict]
    signal_path: str
    ticket: str
    ticket_expires_at: datetime
