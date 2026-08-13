"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Project } from "@/types/project";

export default function Dashboard() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const load = useCallback(() => api.listProjects().then(setProjects).catch((e) => setError(e.message)).finally(() => setLoading(false)), []);
  useEffect(() => { void load(); }, [load]);

  return <>
    <section className="hero">
      <div><div className="eyebrow">Production workspace</div><h1>Stories from the wild, built with care.</h1><p>Research, plan and produce source-backed wildlife documentaries.</p></div>
      <Link className="button" href="/projects/new">+ New project</Link>
    </section>
    {error && <div className="error">Backend unavailable: {error}</div>}
    {loading ? <p>Loading projects…</p> : projects.length === 0 ?
      <div className="empty"><h2>Your expedition starts here</h2><p>Create a documentary project to begin.</p><Link className="button" href="/projects/new">Create first project</Link></div> :
      <div className="grid">{projects.map((p) => <Link className="card project-card" href={`/projects/${p.id}`} key={p.id}><span className="pill">{p.status}</span><h3>{p.title}</h3><p>{p.animal_topic ?? "AI-selected topic"}</p><div className="meta"><span>{p.requested_duration_seconds / 60} min</span><span>•</span><span>{p.language}</span><span>•</span><span>{p.output_resolution}</span></div></Link>)}</div>}
  </>;
}

