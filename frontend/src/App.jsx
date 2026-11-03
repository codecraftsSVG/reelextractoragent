import { useState, useEffect, useCallback } from "react";

const API = window.location.hostname === "localhost" && window.location.port === "5173"
  ? ""
  : `http://${window.location.hostname}:8000`;

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

function ReelGrid({ jobId }) {
  const [detail, setDetail] = useState(null);
  useEffect(() => {
    if (!jobId) return;
    fetch(`${API}/jobs/${jobId}`).then((r) => r.json()).then(setDetail);
    const iv = setInterval(() => {
      fetch(`${API}/jobs/${jobId}`).then((r) => r.json()).then(setDetail);
    }, 4000);
    return () => clearInterval(iv);
  }, [jobId]);

  if (!detail) return null;
  return (
    <div style={{ padding: 20 }}>
      <h3>Reels</h3>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(180px, 1fr))", gap: 10 }}>
        {detail.reels.map((r) => (
          <div key={r.id} style={{ border: "1px solid #ddd", borderRadius: 6, padding: 10 }}>
            <div style={{ fontFamily: "monospace", fontSize: 12 }}>{r.shortcode}</div>
            <div>verify: {r.verify_status}</div>
            <div style={{ color: scoreColor(r.score), fontWeight: 700 }}>
              {r.score != null ? `score: ${r.score}` : "—"}
            </div>
            {r.md_path && <a href={`/${r.md_path}`} target="_blank" rel="noreferrer">open .md</a>}
          </div>
        ))}
      </div>
    </div>
  );
}

function Trajectory({ jobId }) {
  const [events, setEvents] = useState([]);
  useEffect(() => {
    if (!jobId) return;
    const load = () =>
      fetch(`${API}/trajectory/${jobId}`).then((r) => r.json()).then(setEvents);
    load();
    const iv = setInterval(load, 4000);
    return () => clearInterval(iv);
  }, [jobId]);
  return (
    <div style={{ padding: 20, fontFamily: "monospace", fontSize: 12 }}>
      <h3>Trajectory</h3>
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
  const [selected, setSelected] = useState(null);

  const refresh = useCallback(() => {
    fetch(`${API}/jobs`).then((r) => r.json()).then(setJobs);
  }, []);

  useEffect(() => {
    refresh();
    const iv = setInterval(refresh, 4000);
    return () => clearInterval(iv);
  }, [refresh]);

  const submit = (user) => {
    fetch(`${API}/jobs`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(user),
    }).then((r) => r.json()).then((d) => { setSelected(d.job_id); refresh(); });
  };

  return (
    <div style={{ maxWidth: 1100, margin: "0 auto", fontFamily: "system-ui" }}>
      <h1 style={{ padding: "20px 20px 0" }}>Reel Extractor</h1>
      <SubmitForm onSubmit={submit} />
      <div style={{ display: "flex" }}>
        <div style={{ width: 320 }}><JobList jobs={jobs} selected={selected} onSelect={setSelected} /></div>
        <div style={{ flex: 1 }}>
          {selected && <><ReelGrid jobId={selected} /><Trajectory jobId={selected} /></>}
        </div>
      </div>
    </div>
  );
}
