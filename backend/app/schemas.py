from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=10000)
    session_id: str | None = None
    stream: bool = False


class DecisionRequest(BaseModel):
    stream: bool = False


class ToolActivity(BaseModel):
    name: str
    summary: str
    status: str = "completed"


class ActivityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    task_id: str
    name: str
    summary: str
    status: str
    arguments: str | None = None
    result: str | None = None
    created_at: datetime



class Confirmation(BaseModel):
    call_id: str
    name: str
    arguments: dict[str, Any]
    permission: str


class ChatResponse(BaseModel):
    task_id: str
    session_id: str | None = None
    message: str
    status: str
    activities: list[ToolActivity] = []
    confirmations: list[Confirmation] = []


class TaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    title: str
    status: str
    request: str
    response: str
    session_id: str | None = None
    created_at: datetime


class SessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    title: str
    created_at: datetime
    updated_at: datetime
    task_count: int = 0
    preview: str = ""


class SessionCreate(BaseModel):
    title: str | None = Field(default=None, max_length=240)


class ToolOut(BaseModel):
    name: str
    description: str
    permission: str
class MemoryCreate(BaseModel):
    content: str = Field(min_length=1, max_length=4000)
    category: str = "note"


class MemoryOut(MemoryCreate):
    model_config = ConfigDict(from_attributes=True)
    id: str
    created_at: datetime
