import base64
import io
import zipfile

import pytest
from PIL import Image
from pypdf import PdfReader

from app import config, worker
from app.logo import MAX_BYTES, load

HEADER = "Name Of Person,The Competition,Category - Winner/Place/Participation,Final Issued Date,Issuer,Logo\n"


def png_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGBA", (120, 40), (200, 30, 30, 255)).save(buf, "PNG")
    return buf.getvalue()


def data_uri(raw: bytes | None = None) -> str:
    return "data:image/png;base64," + base64.b64encode(raw or png_bytes()).decode()


def upload(client, body, name="certs.csv"):
    data = body.encode() if isinstance(body, str) else body
    return client.post("/jobs/csv", files={"file": (name, data, "text/csv")})


def finished(client, response):
    assert response.status_code == 202
    return client.get(f"/jobs/{response.json()['id']}").json()


def pages(client, job_id):
    certs = client.get(f"/jobs/{job_id}/certificates", params={"status": "success"}).json()
    return [PdfReader(io.BytesIO(client.get(c["download_url"]).content)).pages[0] for c in certs]


def test_csv_upload_generates_certificate_per_category(client):
    body = HEADER + (
        "Asha Rao,Hackathon 2026,Winner,2026-09-05,Acme Academy,\n"
        "Ravi Kumar,Hackathon 2026,place,05/09/2026,Acme Academy,\n"
        "Meera Iyer,Quiz Night,PARTICIPATION,05-09-2026,Acme Academy,\n"
    )
    r = upload(client, body)
    assert r.headers["location"] == f"/jobs/{r.json()['id']}"
    job = finished(client, r)
    assert (job["status"], job["total"], job["succeeded"]) == ("completed", 3, 3)

    text = [p.extract_text() for p in pages(client, job["id"])]
    assert "CERTIFICATE OF ACHIEVEMENT" in text[0] and "Asha Rao" in text[0] and "winner" in text[0]
    assert "CERTIFICATE OF MERIT" in text[1] and "place" in text[1]
    assert "CERTIFICATE OF PARTICIPATION" in text[2] and "Quiz Night" in text[2]
    assert all("05 September 2026" in t and "Acme Academy" in t for t in text)


def test_logo_is_optional_and_drawn_only_when_present(client):
    body = HEADER + (
        f'With Logo,Hackathon,Winner,2026-09-05,Acme,"{data_uri()}"\n'
        "No Logo,Hackathon,Winner,2026-09-05,Acme,\n"
    )
    job = finished(client, upload(client, body))
    assert job["status"] == "completed"
    with_logo, without_logo = pages(client, job["id"])
    assert len(with_logo.images) == 1
    assert len(without_logo.images) == 0


def test_template_without_logo_matches_json_layout(client, payload):
    csv_job = finished(client, upload(client, HEADER + "Asha Rao,Python Bootcamp 2026,Winner,2026-09-05,Acme Academy,\n"))
    json_job = client.post("/jobs", json=payload).json()
    csv_page = pages(client, csv_job["id"])[0]
    json_page = pages(client, json_job["id"])[0]
    assert csv_page.mediabox == json_page.mediabox
    assert not csv_page.images and not json_page.images


def test_flexible_headers_and_bom(client):
    body = "\ufeffname,competition,category,date,issued by\nAsha,Quiz,winner,2026-01-02,Acme\n"
    assert finished(client, upload(client, body))["status"] == "completed"


def test_bad_rows_are_reported_and_good_rows_still_generated(client):
    body = HEADER + (
        "Good One,Hackathon,Winner,2026-09-05,Acme,\n"
        ",Hackathon,Winner,2026-09-05,Acme,\n"
        "No Cat,Hackathon,Champion,2026-09-05,Acme,\n"
        "Bad Date,Hackathon,Winner,31/31/2026,Acme,\n"
        "Bad Logo,Hackathon,Winner,2026-09-05,Acme,ftp://x/y.png\n"
        "Short Row,Hackathon,Winner\n"
        "\n"
        "Also Good,Hackathon,Participation,2026-09-05,Acme,\n"
    )
    job = finished(client, upload(client, body))
    assert job["status"] == "completed_with_errors"
    assert (job["total"], job["succeeded"], job["failed"]) == (7, 2, 5)

    failed = client.get(f"/jobs/{job['id']}/certificates", params={"status": "failed"}).json()
    assert [f["position"] for f in failed] == [1, 2, 3, 4, 5]
    assert "name" in failed[0]["error"]
    assert "category" in failed[1]["error"]
    assert "YYYY-MM-DD" in failed[2]["error"]
    assert "logo" in failed[3]["error"]
    assert "issued_on" in failed[4]["error"] and "issuer" in failed[4]["error"]


@pytest.mark.parametrize(
    "body, message",
    [
        (b"", "empty"),
        (HEADER, "no data rows"),
        ("Name,Competition\nAsha,Quiz\n", "category"),
        (b"\xff\xfe\x00\x01", "UTF-8"),
    ],
)
def test_file_level_validation(client, body, message):
    r = upload(client, body)
    assert r.status_code == 422
    assert message in r.json()["detail"]


def test_row_cap_and_size_cap(client, monkeypatch):
    rows = "".join(f"P{i},Quiz,Winner,2026-09-05,Acme,\n" for i in range(51))
    assert upload(client, HEADER + rows).status_code == 422
    monkeypatch.setattr(config, "MAX_CSV_BYTES", 10)
    assert upload(client, HEADER + rows).status_code == 413


def test_missing_file_is_rejected(client):
    assert client.post("/jobs/csv").status_code == 422


def test_same_logo_is_fetched_once_per_job(client, monkeypatch):
    calls = []
    monkeypatch.setattr(worker, "load_logo", lambda ref: calls.append(ref) or png_bytes())
    body = HEADER + "".join(f"P{i},Quiz,Winner,2026-09-05,Acme,https://cdn.acme.in/logo.png\n" for i in range(3))
    job = finished(client, upload(client, body))
    assert job["status"] == "completed"
    assert calls == ["https://cdn.acme.in/logo.png"]
    assert all(len(p.images) == 1 for p in pages(client, job["id"]))


def test_unreachable_logo_fails_only_those_rows_and_is_not_retried(client, monkeypatch):
    calls = []

    def broken(ref):
        calls.append(ref)
        raise OSError("connection refused")

    monkeypatch.setattr(worker, "load_logo", broken)
    body = HEADER + (
        "A,Quiz,Winner,2026-09-05,Acme,https://cdn.acme.in/logo.png\n"
        "B,Quiz,Winner,2026-09-05,Acme,https://cdn.acme.in/logo.png\n"
        "C,Quiz,Winner,2026-09-05,Acme,\n"
    )
    job = finished(client, upload(client, body))
    assert (job["succeeded"], job["failed"]) == (1, 2)
    assert len(calls) == 1
    failed = client.get(f"/jobs/{job['id']}/certificates", params={"status": "failed"}).json()
    assert all("connection refused" in f["error"] for f in failed)


def test_private_logo_host_is_blocked_end_to_end(client):
    body = HEADER + (
        "A,Quiz,Winner,2026-09-05,Acme,http://127.0.0.1:9/logo.png\n"
        "B,Quiz,Winner,2026-09-05,Acme,\n"
    )
    job = finished(client, upload(client, body))
    assert (job["succeeded"], job["failed"]) == (1, 1)
    failed = client.get(f"/jobs/{job['id']}/certificates", params={"status": "failed"}).json()
    assert "not a public address" in failed[0]["error"]


def test_corrupt_logo_fails_only_that_row(client):
    bad = data_uri(b"definitely not an image")
    body = HEADER + (
        f'A,Quiz,Winner,2026-09-05,Acme,"{bad}"\n'
        "B,Quiz,Winner,2026-09-05,Acme,\n"
    )
    job = finished(client, upload(client, body))
    assert (job["succeeded"], job["failed"]) == (1, 1)


@pytest.mark.parametrize(
    "ref, message",
    [
        ("http://127.0.0.1:9/logo.png", "public"),
        ("http://localhost/logo.png", "public"),
        ("http://169.254.169.254/latest/meta-data", "public"),
        ("ftp://example.org/logo.png", "http"),
        ("data:image/png;base64,@@@", "base64"),
        (data_uri(b"0" * (MAX_BYTES + 1)), "2 MB"),
    ],
)
def test_logo_loader_guards(ref, message):
    with pytest.raises(ValueError, match=message):
        load(ref)


def test_logo_loader_accepts_data_uri():
    assert load(data_uri()) == png_bytes()


def test_csv_job_archive_only_contains_successful_certificates(client):
    body = HEADER + "Asha Rao,Quiz,Winner,2026-09-05,Acme,\nBroken,Quiz,Nope,2026-09-05,Acme,\n"
    job = finished(client, upload(client, body))
    r = client.get(f"/jobs/{job['id']}/archive")
    assert r.status_code == 200
    assert zipfile.ZipFile(io.BytesIO(r.content)).namelist() == ["00001_Asha_Rao.pdf"]
