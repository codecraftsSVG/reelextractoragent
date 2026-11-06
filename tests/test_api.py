import os
import pytest
from fastapi.testclient import TestClient
from backend.main import app
from backend.database import SessionLocal, Base, engine, ensure_job_reel_url_column
from backend.models import Job, Reel, TrajectoryEvent, Evaluation


@pytest.fixture(autouse=True)
def clean_db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def mock_popen(monkeypatch):
    import subprocess
    calls = []

    class FakePopen:
        def __init__(self, *args, **kwargs):
            calls.append((args, kwargs))

    monkeypatch.setattr(subprocess, "Popen", FakePopen)
    return calls


# ---------- Health ----------

def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_health_method_not_allowed(client):
    r = client.post("/health")
    assert r.status_code in (405, 422)


# ---------- List jobs ----------

def test_list_jobs_empty(client):
    r = client.get("/jobs")
    assert r.status_code == 200
    assert r.json() == []


def test_list_jobs_ordering_newest_first(client):
    db = SessionLocal()
    db.add(Job(target_user="@old", status="done"))
    db.commit()
    db.add(Job(target_user="@new", status="queued"))
    db.commit()
    db.close()
    r = client.get("/jobs")
    assert r.status_code == 200
    data = r.json()
    assert [j["target_user"] for j in data] == ["@new", "@old"]


# ---------- Create job validation ----------

@pytest.mark.parametrize("url", [
    "https://www.instagram.com/reel/abc123XYZ/",
    "https://instagram.com/reel/abc123XYZ/",
    "https://www.instagram.com/reels/abc123XYZ",
    "https://www.instagram.com/reel/abc-123_XYZ/",
    "https://www.instagram.com/reel/abc123XYZ/?utm_source=ig_web",
    "https://www.instagram.com/reel/abc123XYZ/?igsh=xxx&y=1",
])
def test_create_job_valid_reel_urls(client, mock_popen, url):
    r = client.post("/jobs", json={"reel_url": url})
    assert r.status_code == 200, r.text
    data = r.json()
    assert "job_id" in data
    db = SessionLocal()
    job = db.get(Job, data["job_id"])
    assert job is not None
    assert job.reel_url == url
    assert job.total_reels == 1
    assert job.status == "queued"
    db.close()
    assert len(mock_popen) == 1


@pytest.mark.parametrize("url", [
    "https://example.com/not-a-reel",
    "http://www.instagram.com/reel/abc123/",
    "https://www.instagram.com/p/abc123/",
    "https://www.instagram.com/reel/",
    "https://www.instagram.com/reel/abc 123/",
    "https://www.instagram.com/reel/abc!123/",
    "abc123XYZ",
    "https://www.instagram.com/reel/abc123/#frag",
    "",
])
def test_create_job_invalid_reel_urls(client, url):
    r = client.post("/jobs", json={"reel_url": url})
    assert r.status_code == 422, (url, r.status_code, r.text)


@pytest.mark.parametrize("payload,detail_part", [
    ({}, "Enter an Instagram username or reel URL"),
    ({"target_user": ""}, "Enter an Instagram username or reel URL"),
    ({"target_user": "   "}, "Enter an Instagram username or reel URL"),
    ({"reel_url": "https://example.com/x"}, "Enter a valid Instagram reel URL"),
])
def test_create_job_validation_errors(client, payload, detail_part):
    r = client.post("/jobs", json=payload)
    assert r.status_code == 422
    assert detail_part in r.json().get("detail", "")


@pytest.mark.parametrize("user,expected", [
    ("corespear", "@corespear"),
    ("@corespear", "@corespear"),
    ("  corespear  ", "@corespear"),
    ("a_b-c123", "@a_b-c123"),
])
def test_create_job_valid_usernames(client, mock_popen, user, expected):
    r = client.post("/jobs", json={"target_user": user})
    assert r.status_code == 200, r.text
    data = r.json()
    db = SessionLocal()
    job = db.get(Job, data["job_id"])
    assert job.target_user == expected
    assert job.reel_url is None
    db.close()


def test_create_job_reel_url_wins_over_target_user(client, mock_popen):
    r = client.post("/jobs", json={
        "reel_url": "https://www.instagram.com/reel/abc123XYZ/",
        "target_user": "someone",
    })
    assert r.status_code == 200
    db = SessionLocal()
    job = db.get(Job, r.json()["job_id"])
    assert job.reel_url is not None
    assert job.target_user.startswith("Reel: ")
    db.close()


def test_create_job_shortcode_extraction(client, mock_popen):
    r = client.post("/jobs", json={"reel_url": "https://www.instagram.com/reel/DfIyw6ThfwO/?utm_source=x"})
    assert r.status_code == 200
    db = SessionLocal()
    job = db.get(Job, r.json()["job_id"])
    assert job.target_user == "Reel: DfIyw6ThfwO"
    db.close()


def test_create_job_spawns_runner_with_sys_executable(client, mock_popen):
    import sys
    r = client.post("/jobs", json={"reel_url": "https://www.instagram.com/reel/abc123XYZ/"})
    assert r.status_code == 200
    (args, kwargs), = mock_popen
    assert args[0][0] == sys.executable
    assert args[0][1].endswith("workers/runner.py")
    assert str(r.json()["job_id"]) in args[0][2]


def test_create_job_invalid_json(client):
    r = client.post("/jobs", content="{not json", headers={"Content-Type": "application/json"})
    assert r.status_code in (422, 400)


def test_create_job_duplicate_urls_create_two_rows(client, mock_popen):
    url = "https://www.instagram.com/reel/abc123XYZ/"
    r1 = client.post("/jobs", json={"reel_url": url})
    r2 = client.post("/jobs", json={"reel_url": url})
    assert r1.json()["job_id"] != r2.json()["job_id"]
    db = SessionLocal()
    count = db.query(Job).filter(Job.reel_url == url).count()
    assert count == 2
    db.close()


# ---------- Detail / evaluation / trajectory ----------

def test_job_detail_not_found(client):
    r = client.get("/jobs/99999")
    assert r.status_code == 404
    assert "Job not found" in r.json().get("detail", "")


def test_job_detail_negative_id(client):
    r = client.get("/jobs/-1")
    assert r.status_code == 404


def test_job_detail_with_reels(client, mock_popen):
    r = client.post("/jobs", json={"reel_url": "https://www.instagram.com/reel/abc123XYZ/"})
    jid = r.json()["job_id"]
    db = SessionLocal()
    db.add(Reel(job_id=jid, shortcode="abc123XYZ",
                reel_url="https://www.instagram.com/reel/abc123XYZ/",
                verify_status="pass", score=90.0, md_path="storage/x.md"))
    db.commit()
    db.close()
    r = client.get(f"/jobs/{jid}")
    assert r.status_code == 200
    data = r.json()
    assert data["job"]["id"] == jid
    assert len(data["reels"]) == 1
    assert data["reels"][0]["shortcode"] == "abc123XYZ"
    assert data["reels"][0]["score"] == 90.0


def test_job_evaluation_empty(client, mock_popen):
    r = client.post("/jobs", json={"reel_url": "https://www.instagram.com/reel/abc123XYZ/"})
    r = client.get(f"/jobs/{r.json()['job_id']}/evaluation")
    assert r.status_code == 200
    assert r.json() == []


def test_job_evaluation_seeded(client, mock_popen):
    r = client.post("/jobs", json={"reel_url": "https://www.instagram.com/reel/abc123XYZ/"})
    jid = r.json()["job_id"]
    db = SessionLocal()
    reel = Reel(job_id=jid, shortcode="abc123XYZ",
                reel_url="https://www.instagram.com/reel/abc123XYZ/")
    db.add(reel)
    db.commit()
    db.refresh(reel)
    db.add(Evaluation(reel_id=reel.id, criterion="Clarity", score=90.0,
                      justification="ok"))
    db.commit()
    db.close()
    r = client.get(f"/jobs/{jid}/evaluation")
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 1
    assert rows[0]["criterion"] == "Clarity"
    assert rows[0]["shortcode"] == "abc123XYZ"


def test_trajectory_empty_for_unknown_job(client):
    r = client.get("/trajectory/424242")
    assert r.status_code == 200
    assert r.json() == []


def test_trajectory_shape(client, mock_popen):
    r = client.post("/jobs", json={"reel_url": "https://www.instagram.com/reel/abc123XYZ/"})
    jid = r.json()["job_id"]
    db = SessionLocal()
    db.add(TrajectoryEvent(job_id=jid, agent="DownloadAgent",
                           step="igexport_download", status="ok",
                           latency_ms=100, output="x" * 600,
                           error_message=None, opik_trace_id=None,
                           input_hash="abc"))
    db.commit()
    db.close()
    r = client.get(f"/trajectory/{jid}")
    assert r.status_code == 200
    events = r.json()
    assert len(events) == 1
    e = events[0]
    assert e["agent"] == "DownloadAgent"
    assert len(e["output"]) <= 500
    assert "error_message" in e
    assert "opik_trace_id" in e
    assert "at" in e


# ---------- Static storage ----------

def test_storage_serves_markdown(client):
    md_dir = os.path.join("storage", "output", "@test")
    os.makedirs(md_dir, exist_ok=True)
    md_file = os.path.join(md_dir, "abc.md")
    with open(md_file, "w") as f:
        f.write("# Hello\n")
    try:
        r = client.get("/storage/output/@test/abc.md")
        assert r.status_code == 200
        assert "# Hello" in r.text
    finally:
        os.remove(md_file)


def test_storage_404(client):
    r = client.get("/storage/nonexistent/xyz.md")
    assert r.status_code == 404


def test_health_no_auth_required(client):
    r = client.get("/health", headers={"Authorization": "Bearer x"})
    assert r.status_code == 200


def test_unknown_route(client):
    r = client.get("/nonexistent-xyz")
    assert r.status_code in (200, 404)


def test_ensure_columns_idempotent():
    # Should not raise even when called repeatedly
    ensure_job_reel_url_column()
    ensure_job_reel_url_column()
