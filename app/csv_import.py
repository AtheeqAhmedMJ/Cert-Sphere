import csv
import io
import re
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, field_validator

from app.schemas import text

ALIASES = {
    "name": ("name", "name_of_person", "person", "recipient"),
    "competition": ("competition", "the_competition", "event", "event_name"),
    "category": ("category",),
    "issued_on": ("issued_on", "issued_date", "final_issued_date", "issue_date", "date"),
    "issuer": ("issuer", "issued_by"),
    "logo": ("logo", "logo_url"),
}
REQUIRED = ("name", "competition", "category", "issued_on", "issuer")
DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y")


def field_for(header: str) -> str | None:
    key = re.sub(r"[^a-z0-9]+", "_", header.lower()).strip("_")
    for field, aliases in ALIASES.items():
        if any(key == a or key.startswith(a + "_") for a in aliases):
            return field
    return None


def read_rows(data: bytes) -> list[dict[str, str]]:
    try:
        reader = csv.reader(io.StringIO(data.decode("utf-8-sig"), newline=""))
        header = next(reader, None)
        if header is None:
            raise ValueError("CSV is empty")
        fields = [field_for(h) for h in header]
        missing = [f for f in REQUIRED if f not in fields]
        if missing:
            raise ValueError(f"missing columns: {', '.join(missing)}")
        return [
            {f: cell for f, cell in zip(fields, cells) if f}
            for cells in reader
            if any(c.strip() for c in cells)
        ]
    except (UnicodeDecodeError, csv.Error) as exc:
        raise ValueError(f"unreadable CSV, save it as UTF-8: {exc}")


class CsvRow(BaseModel):
    name: text(80)
    competition: text(100)
    category: Literal["winner", "place", "participation"]
    issued_on: date
    issuer: text(100)
    logo: str | None = None

    @field_validator("category", mode="before")
    @classmethod
    def lower_category(cls, v):
        return v.strip().lower() if isinstance(v, str) else v

    @field_validator("issued_on", mode="before")
    @classmethod
    def parse_date(cls, v):
        if not isinstance(v, str):
            return v
        for fmt in DATE_FORMATS:
            try:
                return datetime.strptime(v.strip(), fmt).date()
            except ValueError:
                pass
        raise ValueError("use YYYY-MM-DD or DD/MM/YYYY")

    @field_validator("logo", mode="before")
    @classmethod
    def clean_logo(cls, v):
        v = v.strip() if isinstance(v, str) else v
        if not v:
            return None
        if not v.startswith(("http://", "https://", "data:image/")):
            raise ValueError("must be an http(s) URL or a data:image URI")
        return v
