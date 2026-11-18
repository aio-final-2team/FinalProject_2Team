"""로그인·내 정보(API 설계 문서 1.2, 3.7)."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class LoginIn(BaseModel):
    login_id: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class UserOut(BaseModel):
    id: UUID
    role: Literal["parent", "teacher", "director"]
    display_name: str
    org_id: UUID
    classroom_ids: list[UUID] = Field(default_factory=list, description="담임만. 대체 담임은 기간 안인 반만")


class ChildOut(BaseModel):
    id: UUID
    display_name: str
    classroom_id: UUID


class MeOut(BaseModel):
    user: UserOut
    children: list[ChildOut] = Field(default_factory=list, description="학부모만")


class LoginOut(MeOut):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
