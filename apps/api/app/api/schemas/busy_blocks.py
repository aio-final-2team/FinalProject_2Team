"""담임 바쁜 시간은 시간대가 있는 시작·끝으로 주고받아요."""

from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, model_validator


class BusyBlockIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    start_at: AwareDatetime
    end_at: AwareDatetime
    kind: Literal["class", "meeting", "duty", "off", "other"]

    @model_validator(mode="after")
    def ordered(self):
        if self.start_at >= self.end_at:
            raise ValueError("start_at은 end_at보다 빨라야 해요")
        return self


class BusyBlockOut(BusyBlockIn):
    id: int
    user_id: UUID


class BusyBlocksOut(BaseModel):
    items: list[BusyBlockOut]
