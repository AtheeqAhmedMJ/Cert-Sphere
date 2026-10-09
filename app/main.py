import io
import re
import threading
import zipfile
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query, Response, UploadFile
from fastapi.responses import FileResponse
from pydantic import ValidationError
from sqlalchemy import insert, select
from sqlalchemy.orm import Session

from app import config
from app.db import (
    FAILED,
    FINAL,
    PENDING,
    PROCESSING,
    SUCCESS,
    Base,
    Certificate,
    Job,
    SessionLocal,
    engine,
    new_id,
    status_counts,
)
from app.csv_import import CsvRow, read_rows
from app.pdf import TITLES
from app.schemas import CertificateOut, JobCreate, JobOut, Recipient
from app.worker import process_job


def unfinished_jobs() -> list[str]:
    with SessionLocal() as db:
        return list(db.scalars(select(Job.id).where(Job.status.in_([PENDING, PROCESSING])).order_by(Job.created_at)))


def resume(job_ids: list[str]) -> None:
    for job_id in job_ids:
        process_job(job_id)


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(engine)
    config.STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    threading.Thread(target=resume, args=(unfinished_jobs(),), daemon=True).start()
    yield


app = FastAPI(title="Bulk Certificate Generator", lifespan=lifespan)


def get_db():
    with SessionLocal() as db:
        yield db


DB = Annotated[Session, Depends(get_db)]


def describe(exc: ValueError) -> str:
    if isinstance(exc, ValidationError):
        return "; ".join(f"{'.'.join(map(str, e['loc'])) or 'row'}: {e['msg']}" for e in exc.errors())
    return str(exc)


def raw_fields(raw: Any) -> dict[str, str]:
    if not isinstance(raw, dict):
        return {}
    return {k: str(raw[k])[:255] for k in ("name", "email") if raw.get(k) is not None}


def slug(value: str | None) -> str:
    return re.sub(r"\W+", "_", value or "").strip("_") or "certificate"


def utc(value: datetime | None) -> datetime | None:
    return value.replace(tzinfo=timezone.utc) if value and value.tzinfo is None else value


def job_out(db: Session, job: Job) -> JobOut:
    counts = status_counts(db, job.id)
    total = sum(counts.values())
    done, failed = counts.get(SUCCESS, 0), counts.get(FAILED, 0)
    return JobOut(
        id=job.id,
        status=job.status,
        created_at=utc(job.created_at),
        finished_at=utc(job.finished_at),
        total=total,
        succeeded=done,
        failed=failed,
        pending=total - done - failed,
        progress=round((done + failed) / total, 4) if total else 1.0,
    )


def find_job(db: Session, job_id: str) -> Job:
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(404, "job not found")
    return job


def cert_row(position: int, **values: Any) -> dict[str, Any]:
    return {
        "id": new_id(),
        "position": position,
        "name": None,
        "email": None,
        "title": None,
        "event_name": None,
        "category": None,
        "issuer": None,
        "issued_on": None,
        "logo": None,
        "status": PENDING,
        "error": None,
        "file_path": None,
        **values,
    }


def submit(db: Session, background: BackgroundTasks, response: Response, rows: list[dict[str, Any]]) -> JobOut:
    job = Job()
    db.add(job)
    db.flush()
    db.execute(insert(Certificate), [{**row, "job_id": job.id} for row in rows])
    db.commit()
    background.add_task(process_job, job.id)
    response.headers["Location"] = f"/jobs/{job.id}"
    return job_out(db, job)


@app.post("/jobs", response_model=JobOut, status_code=202)
def create_job(body: JobCreate, background: BackgroundTasks, response: Response, db: DB):
    shared = {"title": body.title, "event_name": body.event_name, "issuer": body.issuer, "issued_on": body.issued_on}
    seen: set[str] = set()
    rows = []
    for position, raw in enumerate(body.recipients):
        try:
            recipient = Recipient.model_validate(raw)
            key = recipient.email.lower()
            if key in seen:
                raise ValueError("duplicate email in this request")
            seen.add(key)
            rows.append(cert_row(position, name=recipient.name, email=recipient.email, **shared))
        except ValueError as exc:
            rows.append(cert_row(position, status=FAILED, error=describe(exc), **raw_fields(raw)))
    return submit(db, background, response, rows)


@app.post("/jobs/csv", response_model=JobOut, status_code=202)
def create_job_from_csv(file: UploadFile, background: BackgroundTasks, response: Response, db: DB):
    data = file.file.read(config.MAX_CSV_BYTES + 1)
    if len(data) > config.MAX_CSV_BYTES:
        raise HTTPException(413, "CSV file is too large")
    try:
        records = read_rows(data)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    if not records:
        raise HTTPException(422, "CSV has no data rows")
    if len(records) > config.MAX_RECIPIENTS:
        raise HTTPException(422, f"at most {config.MAX_RECIPIENTS} rows per upload")

    rows = []
    for position, raw in enumerate(records):
        try:
            r = CsvRow.model_validate(raw)
            rows.append(
                cert_row(
                    position,
                    name=r.name,
                    event_name=r.competition,
                    category=r.category,
                    title=TITLES[r.category],
                    issuer=r.issuer,
                    issued_on=r.issued_on,
                    logo=r.logo,
                )
            )
        except ValueError as exc:
            rows.append(cert_row(position, status=FAILED, error=describe(exc), **raw_fields(raw)))
    return submit(db, background, response, rows)


@app.get("/jobs/{job_id}", response_model=JobOut)
def get_job(job_id: str, db: DB):
    return job_out(db, find_job(db, job_id))


@app.get("/jobs/{job_id}/certificates", response_model=list[CertificateOut])
def list_certificates(
    job_id: str,
    db: DB,
    status: Literal["pending", "success", "failed"] | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    find_job(db, job_id)
    stmt = select(Certificate).where(Certificate.job_id == job_id)
    if status:
        stmt = stmt.where(Certificate.status == status)
    return db.scalars(stmt.order_by(Certificate.position).limit(limit).offset(offset)).all()


@app.get("/certificates/{cert_id}/file")
def download_certificate(cert_id: str, db: DB):
    cert = db.get(Certificate, cert_id)
    if cert is None:
        raise HTTPException(404, "certificate not found")
    if cert.status != SUCCESS or not Path(cert.file_path).is_file():
        raise HTTPException(404, "certificate file is not available")
    return FileResponse(cert.file_path, media_type="application/pdf", filename=f"{slug(cert.name)}.pdf")


@app.get("/jobs/{job_id}/archive")
def download_archive(job_id: str, db: DB):
    job = find_job(db, job_id)
    if job.status not in FINAL:
        raise HTTPException(409, "job is still running")
    rows = db.execute(
        select(Certificate.position, Certificate.name, Certificate.file_path)
        .where(Certificate.job_id == job_id, Certificate.status == SUCCESS)
        .order_by(Certificate.position)
    ).all()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as archive:
        for position, name, path in rows:
            archive.write(path, f"{position + 1:05d}_{slug(name)}.pdf")
    return Response(
        buf.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="certificates_{job_id}.zip"'},
    )
