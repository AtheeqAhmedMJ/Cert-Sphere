from sqlalchemy import select

from app import config
from app.db import (
    COMPLETED,
    COMPLETED_WITH_ERRORS,
    FAILED,
    FINAL,
    PENDING,
    PROCESSING,
    SUCCESS,
    Certificate,
    Job,
    SessionLocal,
    now,
    status_counts,
)
from app.logo import load as load_logo
from app.pdf import render


def logo_for(cache: dict[str, bytes | str], ref: str) -> bytes:
    if ref not in cache:
        try:
            cache[ref] = load_logo(ref)
        except Exception as exc:
            cache[ref] = f"logo: {exc}"
    if isinstance(cache[ref], str):
        raise ValueError(cache[ref])
    return cache[ref]


def process_job(job_id: str) -> None:
    with SessionLocal() as db:
        job = db.get(Job, job_id)
        if job is None or job.status in FINAL:
            return
        job.status = PROCESSING
        db.commit()

        folder = config.STORAGE_DIR / job.id
        folder.mkdir(parents=True, exist_ok=True)
        logos: dict[str, bytes | str] = {}
        pending = (
            select(Certificate)
            .where(Certificate.job_id == job_id, Certificate.status == PENDING)
            .order_by(Certificate.position)
            .limit(config.BATCH_SIZE)
        )

        while batch := db.scalars(pending).all():
            for cert in batch:
                try:
                    pdf = render(
                        cert_id=cert.id,
                        name=cert.name,
                        title=cert.title,
                        event_name=cert.event_name,
                        issuer=cert.issuer,
                        issued_on=cert.issued_on,
                        category=cert.category,
                        logo=logo_for(logos, cert.logo) if cert.logo else None,
                    )
                    path = folder / f"{cert.id}.pdf"
                    path.write_bytes(pdf)
                    cert.status, cert.file_path = SUCCESS, str(path)
                except Exception as exc:
                    cert.status, cert.error = FAILED, f"generation failed: {exc}"[:500]
            db.commit()

        counts = status_counts(db, job_id)
        if not counts.get(SUCCESS):
            job.status = FAILED
        elif counts.get(FAILED):
            job.status = COMPLETED_WITH_ERRORS
        else:
            job.status = COMPLETED
        job.finished_at = now()
        db.commit()
