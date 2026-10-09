import io
import zipfile

from pypdf import PdfReader

from app import main, worker


def test_create_job_returns_202_and_finishes(client, payload):
    r = client.post("/jobs", json=payload)
    assert r.status_code == 202
    job_id = r.json()["id"]
    assert r.headers["location"] == f"/jobs/{job_id}"

    job = client.get(f"/jobs/{job_id}").json()
    assert job["status"] == "completed"
    assert (job["total"], job["succeeded"], job["failed"], job["pending"]) == (3, 3, 0, 0)
    assert job["progress"] == 1.0
    assert job["finished_at"] is not None


def test_request_level_validation(client, payload):
    assert client.post("/jobs", json={**payload, "recipients": []}).status_code == 422
    assert client.post("/jobs", json={**payload, "event_name": ""}).status_code == 422
    assert client.post("/jobs", json={k: v for k, v in payload.items() if k != "issuer"}).status_code == 422
    too_many = [{"name": f"P{i}", "email": f"p{i}@acme.in"} for i in range(51)]
    assert client.post("/jobs", json={**payload, "recipients": too_many}).status_code == 422


def test_bad_recipients_are_recorded_and_good_ones_still_generated(client, payload):
    payload["recipients"] += [
        {"name": "No Mail"},
        {"name": "Bad Mail", "email": "not-an-email"},
        {"name": "  ", "email": "blank@acme.in"},
        {"name": "Dup", "email": "ASHA@acme.in"},
        "just a string",
    ]
    job = client.post("/jobs", json=payload).json()
    job = client.get(f"/jobs/{job['id']}").json()
    assert job["status"] == "completed_with_errors"
    assert (job["total"], job["succeeded"], job["failed"]) == (8, 3, 5)

    failed = client.get(f"/jobs/{job['id']}/certificates", params={"status": "failed"}).json()
    assert [f["position"] for f in failed] == [3, 4, 5, 6, 7]
    assert all(f["error"] and f["download_url"] is None for f in failed)
    assert "duplicate" in failed[3]["error"]


def test_job_with_only_invalid_recipients_is_failed(client, payload):
    payload["recipients"] = [{"name": "x"}, {"email": "y@acme.in"}]
    job = client.post("/jobs", json=payload).json()
    job = client.get(f"/jobs/{job['id']}").json()
    assert job["status"] == "failed"
    assert job["failed"] == 2 and job["succeeded"] == 0


def test_certificate_contains_recipient_data(client, payload):
    job = client.post("/jobs", json=payload).json()
    cert = client.get(f"/jobs/{job['id']}/certificates").json()[0]
    r = client.get(cert["download_url"])
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    text = PdfReader(io.BytesIO(r.content)).pages[0].extract_text()
    assert "Asha Rao" in text
    assert "Python Bootcamp 2026" in text
    assert "Acme Academy" in text
    assert cert["id"] in text


def test_very_long_name_still_renders(client, payload):
    payload["recipients"] = [{"name": "W" * 80, "email": "long@acme.in"}]
    job = client.post("/jobs", json=payload).json()
    assert client.get(f"/jobs/{job['id']}").json()["status"] == "completed"


def test_progress_while_pending_then_after_processing(client, payload, monkeypatch):
    monkeypatch.setattr(main, "process_job", lambda job_id: None)
    job = client.post("/jobs", json=payload).json()
    state = client.get(f"/jobs/{job['id']}").json()
    assert state["status"] == "pending"
    assert (state["pending"], state["progress"]) == (3, 0.0)
    assert client.get(f"/jobs/{job['id']}/archive").status_code == 409

    worker.process_job(job["id"])
    state = client.get(f"/jobs/{job['id']}").json()
    assert state["status"] == "completed" and state["progress"] == 1.0


def test_one_certificate_failure_does_not_stop_the_rest(client, payload, monkeypatch):
    real = worker.render

    def flaky(**kw):
        if kw["name"] == "Ravi Kumar":
            raise RuntimeError("font exploded")
        return real(**kw)

    monkeypatch.setattr(worker, "render", flaky)
    job = client.post("/jobs", json=payload).json()
    state = client.get(f"/jobs/{job['id']}").json()
    assert state["status"] == "completed_with_errors"
    assert (state["succeeded"], state["failed"]) == (2, 1)

    failed = client.get(f"/jobs/{job['id']}/certificates", params={"status": "failed"}).json()
    assert len(failed) == 1
    assert failed[0]["name"] == "Ravi Kumar" and "font exploded" in failed[0]["error"]
    assert client.get(f"/certificates/{failed[0]['id']}/file").status_code == 404

    ok = client.get(f"/jobs/{job['id']}/certificates", params={"status": "success"}).json()
    assert [c["name"] for c in ok] == ["Asha Rao", "Meera Iyer"]
    assert all(client.get(c["download_url"]).status_code == 200 for c in ok)


def test_listing_filters_and_pagination(client, payload):
    job = client.post("/jobs", json=payload).json()
    url = f"/jobs/{job['id']}/certificates"
    assert len(client.get(url).json()) == 3
    page = client.get(url, params={"limit": 2, "offset": 2}).json()
    assert [c["name"] for c in page] == ["Meera Iyer"]
    assert client.get(url, params={"status": "bogus"}).status_code == 422
    assert client.get(url, params={"limit": 0}).status_code == 422


def test_archive_contains_only_successful_certificates(client, payload):
    payload["recipients"].append({"name": "Broken"})
    job = client.post("/jobs", json=payload).json()
    r = client.get(f"/jobs/{job['id']}/archive")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/zip"
    names = zipfile.ZipFile(io.BytesIO(r.content)).namelist()
    assert names == ["00001_Asha_Rao.pdf", "00002_Ravi_Kumar.pdf", "00003_Meera_Iyer.pdf"]


def test_unknown_ids_return_404(client):
    for url in ("/jobs/nope", "/jobs/nope/certificates", "/jobs/nope/archive", "/certificates/nope/file"):
        assert client.get(url).status_code == 404


def test_unfinished_jobs_are_resumed(client, payload, monkeypatch):
    monkeypatch.setattr(main, "process_job", lambda job_id: None)
    job = client.post("/jobs", json=payload).json()
    assert main.unfinished_jobs() == [job["id"]]
    monkeypatch.setattr(main, "process_job", worker.process_job)
    main.resume(main.unfinished_jobs())
    assert client.get(f"/jobs/{job['id']}").json()["status"] == "completed"
    assert main.unfinished_jobs() == []


def test_timestamps_are_always_timezone_aware(client, payload):
    created = client.post("/jobs", json=payload).json()
    fetched = client.get(f"/jobs/{created['id']}").json()
    assert created["created_at"].endswith("Z") and fetched["created_at"].endswith("Z")
    assert fetched["finished_at"].endswith("Z")
