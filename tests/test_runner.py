import os
import pytest


@pytest.fixture(autouse=True)
def ensure_tables():
    from backend.database import Base, engine
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


def _seed_job(reel_url=None, target="@user"):
    from backend.database import SessionLocal
    from backend.models import Job
    db = SessionLocal()
    job = Job(target_user=target, reel_url=reel_url, status="queued",
              total_reels=1 if reel_url else 0)
    db.add(job)
    db.commit()
    jid = job.id
    db.close()
    return jid


def _fake_asyncio_run(coro):
    coro.close()
    return "/tmp/fake.mp4"


def _patch_pipeline(monkeypatch, runner):
    monkeypatch.setattr(runner.asyncio, "run", _fake_asyncio_run)
    monkeypatch.setattr(runner.transcript, "transcribe",
                        lambda p, s: {"text": "hello", "avg_confidence": 0.8})
    monkeypatch.setattr(runner.ocr, "extract_text",
                        lambda p, s, fps=0.5: {"duration_s": 5.0, "frames_extracted": 3,
                                              "raw": ["f"], "lines": ["hi"]})
    monkeypatch.setattr(runner.writer, "write_md",
                        lambda *a, **k: _write_dummy_md(a[1]["shortcode"]))
    monkeypatch.setattr(runner.verifier, "verify_reel",
                        lambda *a, **k: {"status": "pass", "failed_checks": [],
                                         "detail": {"ok": True}})
    monkeypatch.setattr(runner.evaluator, "score",
                        lambda *a, **k: {"total": 95.0, "criteria": {"formatting": 10},
                                         "justification": "j", "verdict": "publish"})


def _write_dummy_md(shortcode):
    d = os.path.join("storage", "output", f"@reel-{shortcode}")
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, f"{shortcode}.md")
    with open(p, "w") as f:
        f.write("## Caption\nx\n## Transcript (spoken)\n## On-screen text\n## Hashtags\n")
    return p


def test_run_job_reel_url_happy(monkeypatch):
    import workers.runner as runner
    from backend.database import SessionLocal
    from backend.models import Job, Reel, Evaluation, TrajectoryEvent

    jid = _seed_job(reel_url="https://www.instagram.com/reel/abc123XYZ/")
    _patch_pipeline(monkeypatch, runner)

    runner.run_job(jid)

    db = SessionLocal()
    job = db.get(Job, jid)
    assert job.status == "done"
    assert job.done_reels == 1
    reels = db.query(Reel).filter_by(job_id=jid).all()
    assert len(reels) == 1
    assert reels[0].shortcode == "abc123XYZ"
    assert reels[0].verify_status == "pass"
    assert reels[0].score == 95.0
    evs = db.query(Evaluation).filter_by(reel_id=reels[0].id).all()
    assert len(evs) == 1
    steps = [e.step for e in db.query(TrajectoryEvent)
             .filter_by(job_id=jid).order_by(TrajectoryEvent.id).all()]
    assert steps == ["igexport_download", "transcribe", "ocr", "verify", "evaluate"]
    db.close()


def test_run_job_reel_url_retry_verifier(monkeypatch):
    import workers.runner as runner
    from backend.database import SessionLocal
    from backend.models import Job

    jid = _seed_job(reel_url="https://www.instagram.com/reel/abc123XYZ/")
    _patch_pipeline(monkeypatch, runner)
    calls = {"n": 0}

    def flaky(*a, **k):
        calls["n"] += 1
        if calls["n"] == 1:
            return {"status": "retry", "failed_checks": ["V2"], "detail": {}}
        return {"status": "pass", "failed_checks": [], "detail": {}}

    monkeypatch.setattr(runner.verifier, "verify_reel", flaky)
    runner.run_job(jid)
    assert calls["n"] == 2
    db = SessionLocal()
    assert db.get(Job, jid).status == "done"
    db.close()


def test_run_job_reel_url_error_sets_job_error(monkeypatch):
    import workers.runner as runner
    from backend.database import SessionLocal
    from backend.models import Job, TrajectoryEvent

    jid = _seed_job(reel_url="https://www.instagram.com/reel/abc123XYZ/")

    def boom(coro):
        coro.close()
        raise RuntimeError("download exploded")

    monkeypatch.setattr(runner.asyncio, "run", boom)
    monkeypatch.setattr(runner.transcript, "transcribe",
                        lambda p, s: {"text": "x", "avg_confidence": 0.8})
    monkeypatch.setattr(runner.ocr, "extract_text",
                        lambda p, s, fps=0.5: {"duration_s": 1, "frames_extracted": 1,
                                              "raw": [], "lines": []})
    monkeypatch.setattr(runner.writer, "write_md", lambda *a, **k: "/tmp/x.md")
    monkeypatch.setattr(runner.verifier, "verify_reel",
                        lambda *a, **k: {"status": "pass", "failed_checks": [], "detail": {}})
    monkeypatch.setattr(runner.evaluator, "score",
                        lambda *a, **k: {"total": 1, "criteria": {}, "justification": "", "verdict": "x"})

    with pytest.raises(RuntimeError, match="download exploded"):
        runner.run_job(jid)

    db = SessionLocal()
    assert db.get(Job, jid).status == "error"
    errs = (db.query(TrajectoryEvent)
            .filter_by(job_id=jid, status="error").all())
    assert len(errs) >= 1
    db.close()


def test_run_job_profile_happy(monkeypatch):
    import workers.runner as runner
    from backend.database import SessionLocal
    from backend.models import Job, Reel

    jid = _seed_job(target="@natgeo")
    monkeypatch.setattr(runner.scout, "discover_reels",
                        lambda u: {"count": 1, "reels": [
                            {"shortcode": "abc", "url": "https://www.instagram.com/reel/abc/"}]})
    monkeypatch.setattr(runner.fetch, "fetch_reel", lambda url, sc: {
        "shortcode": sc, "url": url, "caption": "cap", "uploader": "u",
        "upload_date": "", "like_count": 0, "video_path": "/tmp/abc.mp4"})
    _patch_pipeline(monkeypatch, runner)

    runner.run_job(jid)
    db = SessionLocal()
    job = db.get(Job, jid)
    assert job.status == "done"
    assert job.total_reels == 1
    assert job.done_reels == 1
    assert db.query(Reel).filter_by(job_id=jid).count() == 1
    db.close()


def test_run_job_profile_cookie_dead_after_4_failures(monkeypatch):
    import workers.runner as runner
    from backend.database import SessionLocal
    from backend.models import Job

    jid = _seed_job(target="@natgeo")
    reels = [{"shortcode": f"s{i}", "url": f"https://www.instagram.com/reel/s{i}/"}
             for i in range(5)]
    monkeypatch.setattr(runner.scout, "discover_reels",
                        lambda u: {"count": len(reels), "reels": reels})

    def fail(url, sc):
        raise RuntimeError("cookie dead")

    monkeypatch.setattr(runner.fetch, "fetch_reel", fail)
    _patch_pipeline(monkeypatch, runner)

    with pytest.raises(RuntimeError, match="cookie/session dead"):
        runner.run_job(jid)
    db = SessionLocal()
    assert db.get(Job, jid).status == "error"
    db.close()


def test_run_job_profile_few_failures_continue(monkeypatch):
    import workers.runner as runner
    from backend.database import SessionLocal
    from backend.models import Job

    jid = _seed_job(target="@natgeo")
    reels = [{"shortcode": "bad", "url": "https://www.instagram.com/reel/bad/"},
             {"shortcode": "good", "url": "https://www.instagram.com/reel/good/"}]
    monkeypatch.setattr(runner.scout, "discover_reels",
                        lambda u: {"count": 2, "reels": reels})

    def fetch_flaky(url, sc):
        if sc == "bad":
            raise RuntimeError("nope")
        return {"shortcode": sc, "url": url, "caption": "c", "uploader": "u",
                "upload_date": "", "like_count": 0, "video_path": "/tmp/g.mp4"}

    monkeypatch.setattr(runner.fetch, "fetch_reel", fetch_flaky)
    _patch_pipeline(monkeypatch, runner)

    runner.run_job(jid)
    db = SessionLocal()
    assert db.get(Job, jid).status == "done"
    db.close()
