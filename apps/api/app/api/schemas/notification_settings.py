"""교직원 개인 조용한 시간은 한국 시간의 시·분으로 받아요."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator

Hour = Annotated[str, Field(pattern=r"^([01][0-9]|2[0-3]):[0-5][0-9]$")]


class NotificationSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    quiet_start: Hour | None
    quiet_end: Hour | None

    @model_validator(mode="after")
    def paired_hours(self):
        if (self.quiet_start is None) != (self.quiet_end is None) or (
                self.quiet_start is not None and self.quiet_start == self.quiet_end):
            raise ValueError("서로 다른 두 시각 또는 둘 다 null이 필요해요")
        return self
