from datetime import date, datetime
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints, computed_field

from app import config


def text(limit: int):
    return Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=limit)]


class Recipient(BaseModel):
    name: text(80)
    email: EmailStr


class JobCreate(BaseModel):
    title: text(60) = "Certificate of Completion"
    event_name: text(100)
    issuer: text(100)
    issued_on: date = Field(default_factory=date.today)
    recipients: list[Any] = Field(min_length=1, max_length=config.MAX_RECIPIENTS)


class JobOut(BaseModel):
    id: str
    status: str
    total: int
    succeeded: int
    failed: int
    pending: int
    progress: float
    created_at: datetime
    finished_at: datetime | None


class CertificateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    position: int
    name: str | None
    email: str | None
    status: str
    error: str | None

    @computed_field
    @property
    def download_url(self) -> str | None:
        return f"/certificates/{self.id}/file" if self.status == "success" else None
