"""75~77번 API: 아이 프로필 사진과 급식 참고 사진."""

from datetime import date

from pydantic import BaseModel, Field


class ProfilePhoto(BaseModel):
    file_url: str = Field(description="로그인 토큰을 붙여 받는 주소예요(75번 API)")


class MealPhoto(BaseModel):
    meal_date: date
    main_dish: str
    file_url: str = Field(description="로그인 토큰을 붙여 받는 주소예요(77번 API)")


class MealPhotoList(BaseModel):
    items: list[MealPhoto]
