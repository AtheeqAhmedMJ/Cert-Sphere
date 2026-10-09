import uuid
from datetime import date, datetime, timezone

from sqlalchemy import Date, DateTime, ForeignKey, Index, String, Text, create_engine, event, func, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from app import config

PENDING, PROCESSING, SUCCESS, FAILED = "pending", "processing", "success", "failed"
COMPLETED, COMPLETED_WITH_ERRORS = "completed", "completed_with_errors"
FINAL = (COMPLETED, COMPLETED_WITH_ERRORS, FAILED)


def new_id() -> str:
    return uuid.uuid4().hex


def now() -> datetime:
    return datetime.now(timezone.utc)


sqlite = config.DATABASE_URL.startswith("sqlite")
engine = create_engine(
    config.DATABASE_URL,
    connect_args={"check_same_thread": False} if sqlite else {},
    pool_pre_ping=True,
)

if sqlite:

    @event.listens_for(engine, "connect")
    def _pragmas(conn, _):
        cur = conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA busy_timeout=5000")
        cur.close()


SessionLocal = sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    status: Mapped[str] = mapped_column(String(24), default=PENDING, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Certificate(Base):
    __tablename__ = "certificates"
    __table_args__ = (Index("ix_cert_job_status_pos", "job_id", "status", "position"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"))
    position: Mapped[int]
    name: Mapped[str | None] = mapped_column(String(255))
    email: Mapped[str | None] = mapped_column(String(255))
    title: Mapped[str | None] = mapped_column(String(100))
    event_name: Mapped[str | None] = mapped_column(String(100))
    category: Mapped[str | None] = mapped_column(String(16))
    issuer: Mapped[str | None] = mapped_column(String(100))
    issued_on: Mapped[date | None] = mapped_column(Date)
    logo: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default=PENDING)
    error: Mapped[str | None] = mapped_column(Text)
    file_path: Mapped[str | None] = mapped_column(String(500))


def status_counts(db: Session, job_id: str) -> dict[str, int]:
    rows = db.execute(
        select(Certificate.status, func.count()).where(Certificate.job_id == job_id).group_by(Certificate.status)
    ).all()
    return dict(rows)
