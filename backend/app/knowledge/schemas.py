from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class DocumentCreate(BaseModel):
    title: str
    category: str = "other"
    content: str


class DocumentUpdate(BaseModel):
    title: Optional[str] = None
    category: Optional[str] = None
    content: Optional[str] = None
    is_active: Optional[bool] = None


class DocumentOut(BaseModel):
    id: str
    title: str
    category: str
    content: str
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DocumentSummaryOut(BaseModel):
    id: str
    title: str
    category: str
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SearchHitOut(BaseModel):
    document_id: str
    document_title: str
    chunk_id: str
    chunk_index: int
    content: str
    rank: float
