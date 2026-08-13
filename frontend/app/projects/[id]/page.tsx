"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { ResearchPanel } from "@/components/research-panel";
import { ScriptPanel } from "@/components/script-panel";
import { api } from "@/lib/api";
import { Project } from "@/types/project";

const tabs = ["Research", "Script", "Scenes", "Media", "Voice-over", "Timeline", "Export"];

export default function ProjectDetails() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [project, setProject] = useState<Project | null>(null);
  const [error, setError] = useState("");
  const [activeTab, setActiveTab] = useState("Research");
  const reloadProject = () => {
    api.getProject(Number(id)).then(setProject).catch((e) => setError(e.message));
  };
  useEffect(() => { reloadProject(); }, [id]); // eslint-disable-line react-hooks/exhaustive-deps

  async function remove() {
    if (!confirm("Delete this project?")) return;
    await api.deleteProject(Number(id));
    router.push("/");
  }
  async function edit() {
    if (!project) return;
    const title = prompt("Project title", project.title);
    if (!title) return;
    const topic = project.auto_topic
      ? project.animal_topic
      : prompt("Animal or topic", project.animal_topic ?? "");
    if (!project.auto_topic && !topic) return;
    try {
      setProject(await api.updateProject(project.id, { title, animal_topic: topic }));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not update project");
    }
  }
  if (error) return <div className="error">{error}</div>;
  if (!project) return <p>Loading project…</p>;

  return <>
    <div className="hero"><div><div className="eyebrow">{project.current_phase}</div><h1>{project.title}</h1><p>{project.animal_topic ?? "Topic will be selected later"}</p></div><Link className="button secondary" href="/">← Dashboard</Link></div>
    <div className="tabs">{tabs.map((tab) => <button className={`tab ${activeTab === tab ? "active" : ""}`} onClick={() => setActiveTab(tab)} key={tab}>{tab}</button>)}</div>
    <div className="details"><section className="card"><h2>Project brief</h2><dl className="detail-list"><div><dt>Status</dt><dd>{project.status}</dd></div><div><dt>Phase</dt><dd>{project.current_phase}</dd></div><div><dt>Duration</dt><dd>{project.requested_duration_seconds / 60} minutes</dd></div><div><dt>Language</dt><dd>{project.language}</dd></div><div><dt>Tone</dt><dd>{project.documentary_tone}</dd></div><div><dt>Resolution</dt><dd>{project.output_resolution}</dd></div></dl></section>
      <aside className="card"><span className="pill">Phase 2</span><h2 style={{ marginTop: 16 }}>Narration studio</h2><p>Review source-backed research, then generate and refine a versioned documentary script.</p><div className="actions"><button className="button secondary" onClick={edit}>Edit project</button><button className="button danger" onClick={remove}>Delete</button></div></aside></div>
    {activeTab === "Research" && <ResearchPanel projectId={project.id} onProjectChanged={reloadProject} />}
    {activeTab === "Script" && <ScriptPanel projectId={project.id} onProjectChanged={reloadProject} />}
    {!['Research', 'Script'].includes(activeTab) && <div className="empty future-tab"><h2>{activeTab}</h2><p>This workflow becomes available in a later roadmap phase.</p></div>}
  </>;
}
