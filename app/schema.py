from typing import Literal

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=1000, examples=["Kiểm tra hóa đơn I-77"])


class ReviewRequest(BaseModel):
    decision: Literal["approved", "rejected"]
