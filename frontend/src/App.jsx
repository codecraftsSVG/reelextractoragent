import { useState, useEffect, useCallback } from "react";

const API = "";

async function fetchJson(url, options) {
  const response = await fetch(url, options);
  if (!response.ok) throw new Error(`Request failed (${response.status})`);
  return response.json();
}

function SubmitForm({ onSubmit }) {
  const [user, setUser] = useState("");
  const [mode, setMode] = useState("username");
  const [reelUrl, setReelUrl] = useState("");
  return (
    <div style={{ padding: 20 }}>
      <div style={{ display: "flex", gap: 12, marginBottom: 10 }}>
        <label>
          <input type="radio" checked={mode === "username"} onChange={() => setMode("username")} /> Profile
        </label>
        <label>
          <input type="radio" checked={mode === "link"} onChange={() => setMode("link")} /> Reel link
        </label>
      </div>
      <div style={{ display: "flex", gap: 8 }}>
        {mode === "username" ? (
          <input
            placeholder="@target_username"
            value={user}
            onChange={(e) => setUser(e.target.value)}
            style={{ padding: 8, width: 260 }}
          />
        ) : (
          <input
            placeholder="https://www.instagram.com/reel/SHORTCODE/"
            value={reelUrl}
            onChange={(e) => setReelUrl(e.target.value)}
            style={{ padding: 8, width: 420 }}
          />
        )}
        <button
          onClick={() => onSubmit(mode === "username"
            ? { target_user: user }
            : { reel_url: reelUrl })}
          style={{ padding: "8px 16px" }}
        >
          {mode === "username" ? "Extract all reels" : "Extract reel"}
        </button>
      </div>
    </div>
  );
}

function scoreColor(score) {
  if (score >= 85) return "#1a7f37";
  if (score >= 60) return "#9a6700";
  return "#cf222e";
}

function JobList({ jobs, selected, onSelect }) {
  return (
    <div style={{ padding: 20 }}>
      <h3>Jobs</h3>
      {jobs.map((j) => (
        <div
          key={j.id}
          onClick={() => onSelect(j.id)}
          style={{
            padding: 10, marginBottom: 6, cursor: "pointer",
            border: selected === j.id ? "2px solid #0969da" : "1px solid #ddd",
            borderRadius: 6,
          }}
        >
          <b>{j.target_user}</b> — {j.status} — {j.done_reels}/{j.total_reels} reels
        </div>
      ))}
    </div>
  );
}

function ReelGrid({ jobId, selectedReel, onSelectReel }) {
  const [detail, setDetail] = useState(null);
  const [error, setError] = useState("");
  useEffect(() => {
    if (!jobId) {
      setDetail(null);
      setError("");
      return;
    }
    let active = true;
    const load = () => fetchJson(`${API}/jobs/${jobId}`)
      .then((data) => {
        if (!Array.isArray(data.reels)) throw new Error("Invalid job response");
        if (active) {
          setDetail(data);
          setError("");
        }
      })
      .catch(() => {
        if (active) {
          setDetail(null);
          setError("Job details are temporarily unavailable. The job may have been interrupted.");
        }
      });
    load();
    const iv = setInterval(load, 4000);
    return () => {
      active = false;
      clearInterval(iv);
    };
  }, [jobId]);

  if (error) return <div role="alert" style={{ padding: 20 }}>{error}</div>;
  if (!detail) return null;
  return (
    <div style={{ padding: 20 }}>
      <h3>Reels</h3>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(180px, 1fr))", gap: 10 }}>
        {detail.reels.map((r) => (
          <div
            key={r.id}
            onClick={() => onSelectReel(r)}
            style={{
              border: selectedReel?.id === r.id ? "2px solid #0969da" : "1px solid #ddd",
              borderRadius: 6, padding: 10, cursor: "pointer", background: selectedReel?.id === r.id ? "#f0f6fc" : "#fff"
            }}
          >
            <div style={{ fontFamily: "monospace", fontSize: 12 }}>{r.shortcode}</div>
            <div>verify: {r.verify_status}</div>
            <div style={{ color: scoreColor(r.score), fontWeight: 700 }}>
              {r.score != null ? `score: ${r.score}` : "—"}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function ReelSidebar({ reel }) {
  const [content, setContent] = useState("");
  useEffect(() => {
    if (!reel || !reel.md_path) {
      setContent("Select a reel to view extracted report and transcript.");
      return;
    }
    fetch(`${API}/${reel.md_path}`)
      .then((r) => r.text())
      .then(setContent)
      .catch(() => setContent("Failed to load report."));
  }, [reel]);

  return (
    <div style={{ padding: 20, borderLeft: "1px solid #ddd", width: 420, background: "#f6f8fa", minHeight: 400, overflowY: "auto" }}>
      <h3>Extracted Text Report</h3>
      {reel && (
        <div style={{ fontSize: 13, marginBottom: 10 }}>
          <div><b>Shortcode:</b> {reel.shortcode}</div>
          <div><b>Status:</b> {reel.verify_status} | <b>Score:</b> {reel.score != null ? reel.score : "—"}</div>
          {reel.reel_url && <div><a href={reel.reel_url} target="_blank" rel="noreferrer">Open on Instagram</a></div>}
        </div>
      )}
      <pre style={{ whiteSpace: "pre-wrap", fontFamily: "monospace", fontSize: 11, background: "#fff", padding: 12, borderRadius: 6, border: "1px solid #d0d7de", maxHeight: 500, overflowY: "auto" }}>
        {content}
      </pre>
    </div>
  );
}

function Trajectory({ jobId }) {
  const [events, setEvents] = useState([]);
  const [error, setError] = useState("");
  useEffect(() => {
    if (!jobId) return;
    let active = true;
    const load = () => fetchJson(`${API}/trajectory/${jobId}`)
      .then((data) => {
        if (!Array.isArray(data)) throw new Error("Invalid trajectory response");
        if (active) {
          setEvents(data);
          setError("");
        }
      })
      .catch(() => {
        if (active) setError("Trajectory is temporarily unavailable.");
      });
    load();
    const iv = setInterval(load, 4000);
    return () => {
      active = false;
      clearInterval(iv);
    };
  }, [jobId]);
  return (
    <div style={{ padding: 20, fontFamily: "monospace", fontSize: 12 }}>
      <h3>Trajectory</h3>
      {error && <div role="alert">{error}</div>}
      {events.map((e, i) => (
        <div key={i} style={{ color: e.status === "ok" ? "#333" : "#cf222e", marginBottom: 2 }}>
          [{e.at}] {e.agent}/{e.step} — {e.status} — {e.latency_ms}ms — {e.output}
        </div>
      ))}
    </div>
  );
}

export default function App() {
  const [jobs, setJobs] = useState([]);
  const [jobsError, setJobsError] = useState("");
  const [submitError, setSubmitError] = useState("");
  const [selected, setSelected] = useState(null);
  const [selectedReel, setSelectedReel] = useState(null);

  const refresh = useCallback(() => {
    return fetchJson(`${API}/jobs`)
      .then((data) => {
        if (!Array.isArray(data)) throw new Error("Invalid jobs response");
        setJobs(data);
        setJobsError("");
      })
      .catch(() => setJobsError("Jobs are temporarily unavailable."));
  }, []);

  useEffect(() => {
    refresh();
    const iv = setInterval(refresh, 4000);
    return () => clearInterval(iv);
  }, [refresh]);

  const submit = (user) => {
    setSubmitError("");
    fetchJson(`${API}/jobs`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(user),
    }).then((d) => {
      if (!d.job_id) throw new Error("Invalid job response");
      setSelected(d.job_id);
      setSelectedReel(null);
      refresh();
    }).catch(() => setSubmitError("Could not start the job. Please retry when the service is available."));
  };

  return (
    <div style={{ maxWidth: 1250, margin: "0 auto", fontFamily: "system-ui" }}>
      <h1 style={{ padding: "20px 20px 0" }}>Reel Extractor</h1>
      <SubmitForm onSubmit={submit} />
      {submitError && <div role="alert" style={{ padding: "0 20px" }}>{submitError}</div>}
      <div style={{ display: "flex" }}>
        <div style={{ width: 300 }}>
          {jobsError && <div role="alert" style={{ padding: 20 }}>{jobsError}</div>}
          <JobList jobs={jobs} selected={selected} onSelect={(id) => { setSelected(id); setSelectedReel(null); }} />
        </div>
        <div style={{ flex: 1 }}>
          {selected && (
            <div style={{ display: "flex" }}>
              <div style={{ flex: 1 }}>
                <ReelGrid jobId={selected} selectedReel={selectedReel} onSelectReel={setSelectedReel} />
                <Trajectory jobId={selected} />
              </div>
              <ReelSidebar reel={selectedReel} />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
