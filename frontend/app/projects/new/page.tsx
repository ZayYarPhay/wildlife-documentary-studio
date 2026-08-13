"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";

export default function NewProject() {
  const router = useRouter();
  const [autoTopic, setAutoTopic] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError("");
    const data = new FormData(event.currentTarget);
    try {
      const project = await api.createProject({
        title: String(data.get("title")), animal_topic: autoTopic ? null : String(data.get("topic")), auto_topic: autoTopic,
        language: String(data.get("language")), requested_duration_seconds: Number(data.get("duration")) * 60,
        output_resolution: String(data.get("resolution")),
      });
      router.push(`/projects/${project.id}`);
    } catch (e) { setError(e instanceof Error ? e.message : "Could not create project"); setBusy(false); }
  }
  return <div className="form"><div className="eyebrow">New production</div><h1>Create a documentary</h1><p>Set the creative brief. AI generation begins in later phases only.</p>
    {error && <div className="error">{error}</div>}
    <form className="card form-grid" onSubmit={submit}>
      <label className="wide">Project title<input name="title" required placeholder="Ghost of the Mountains" /></label>
      <label className="wide">Animal or topic<input name="topic" required={!autoTopic} disabled={autoTopic} placeholder="Snow leopard" /></label>
      <label className="toggle wide"><input type="checkbox" checked={autoTopic} onChange={(e) => setAutoTopic(e.target.checked)} /> Let AI choose a topic later</label>
      <label>Duration<select name="duration" defaultValue="5">{Array.from({length:14},(_,i)=>i+2).map((m)=><option key={m} value={m}>{m} minutes</option>)}</select></label>
      <label>Language<select name="language"><option>English</option><option>Burmese</option><option>Thai</option></select></label>
      <label className="wide">Output resolution<select name="resolution"><option value="1920x1080">1080p — 1920×1080</option><option value="1280x720">720p — 1280×720</option></select></label>
      <div className="actions wide"><button className="button" disabled={busy}>{busy ? "Creating…" : "Create project"}</button><Link className="button secondary" href="/">Cancel</Link></div>
    </form>
  </div>;
}

