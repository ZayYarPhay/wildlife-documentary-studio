"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { ResearchBundle, ResearchFact } from "@/types/project";

export function ResearchPanel({ projectId, onProjectChanged }: { projectId: number; onProjectChanged: () => void }) {
  const [research, setResearch] = useState<ResearchBundle | null>(null);
  const [state, setState] = useState<"loading" | "idle" | "researching" | "review" | "failed">("loading");
  const [error, setError] = useState("");
  const load = useCallback(async () => {
    try {
      const data = await api.getResearch(projectId); setResearch(data); setState(data.facts.length ? "review" : "idle");
    } catch (e) { setError(e instanceof Error ? e.message : "Could not load research"); setState("failed"); }
  }, [projectId]);
  useEffect(() => {
    let active = true;
    api.getResearch(projectId).then((data) => {
      if (!active) return;
      setResearch(data);
      setState(data.facts.length ? "review" : "idle");
    }).catch((e) => {
      if (!active) return;
      setError(e instanceof Error ? e.message : "Could not load research");
      setState("failed");
    });
    return () => { active = false; };
  }, [projectId]);
  const groups = useMemo(() => {
    const result: Record<string, ResearchFact[]> = {};
    for (const fact of research?.facts ?? []) (result[fact.category] ??= []).push(fact);
    return result;
  }, [research]);
  async function generate() {
    setState("researching"); setError("");
    try { const data = await api.generateResearch(projectId); setResearch(data); setState("review"); onProjectChanged(); }
    catch (e) { setError(e instanceof Error ? e.message : "Research failed"); setState("failed"); onProjectChanged(); }
  }
  async function updateFact(fact: ResearchFact) {
    const claim = prompt("Edit fact", fact.claim); if (!claim) return;
    await api.updateFact(fact.id, { claim }); await load();
  }
  async function approve(fact: ResearchFact) { await api.approveFact(fact.id); await load(); }
  async function remove(fact: ResearchFact) { if (!confirm("Delete this research fact?")) return; await api.deleteFact(fact.id); await load(); }

  return <section className="research-section">
    <div className="section-heading"><div><div className="eyebrow">Phase 1</div><h2>Research review</h2><p>Every claim remains attached to its source and requires human approval.</p></div><button className="button" disabled={state === "researching"} onClick={generate}>{state === "researching" ? "Researching…" : research?.facts.length ? "Regenerate research" : "Generate research"}</button></div>
    {research?.warning && <div className="warning"><strong>Mock provider:</strong> {research.warning}</div>}
    {error && <div className="error">{error} <button className="text-button" onClick={generate}>Retry</button></div>}
    {state === "loading" && <p>Loading research…</p>}
    {state === "idle" && <div className="empty"><h2>No research yet</h2><p>Generate a reviewable development dataset for this topic.</p></div>}
    {research && research.facts.length > 0 && !research.facts.some((fact) => fact.approved) && <div className="warning">No facts have been approved. Future script generation will have no factual input until review is complete.</div>}
    {Object.entries(groups).map(([category, facts]) => <div className="fact-group" key={category}><h3>{category.replaceAll("_", " ")}</h3>{facts.map((fact) => <article className={`fact-card ${fact.approved ? "approved" : ""}`} key={fact.id}><div className="fact-main"><p>{fact.claim}</p><a href={fact.source.url} target="_blank" rel="noreferrer">{fact.source.source_name} ↗</a>{fact.notes && <small>{fact.notes}</small>}</div><div className="fact-side"><span className="confidence">{Math.round(fact.confidence * 100)}% confidence</span><label className="toggle"><input type="checkbox" checked={fact.approved} onChange={() => fact.approved ? api.updateFact(fact.id, {approved:false}).then(load) : approve(fact)} /> Approved</label><div><button className="text-button" onClick={() => updateFact(fact)}>Edit</button><button className="text-button danger-text" onClick={() => remove(fact)}>Delete</button></div></div></article>)}</div>)}
  </section>;
}
