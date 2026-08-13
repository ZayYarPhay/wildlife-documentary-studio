"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Scene, Timeline, TimelineItem } from "@/types/project";

export function TimelinePanel({ projectId, onProjectChanged }: { projectId: number; onProjectChanged: () => void }) {
  const [timeline, setTimeline] = useState<Timeline | null>(null);
  const [versions, setVersions] = useState<Timeline[]>([]);
  const [scenes, setScenes] = useState<Scene[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const load = useCallback(async () => {
    const [bundle, sceneBundle] = await Promise.all([api.getTimeline(projectId), api.getScenes(projectId)]);
    setTimeline(bundle.current); setVersions(bundle.versions); setScenes(sceneBundle.scenes);
  }, [projectId]);
  useEffect(() => {
    let active = true;
    Promise.all([api.getTimeline(projectId), api.getScenes(projectId)]).then(([bundle, sceneBundle]) => {
      if (!active) return;
      setTimeline(bundle.current); setVersions(bundle.versions); setScenes(sceneBundle.scenes);
    }).catch((reason) => { if (active) setError(reason.message); });
    return () => { active = false; };
  }, [projectId]);

  async function rebuild() {
    setBusy(true); setError("");
    try { const bundle = await api.buildTimeline(projectId); setTimeline(bundle.current); setVersions(bundle.versions); onProjectChanged(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Timeline build failed"); }
    finally { setBusy(false); }
  }
  async function saveItem(item: TimelineItem) {
    const start = Number((document.getElementById(`timeline-start-${item.id}`) as HTMLInputElement).value);
    const end = Number((document.getElementById(`timeline-end-${item.id}`) as HTMLInputElement).value);
    const transition = (document.getElementById(`timeline-transition-${item.id}`) as HTMLSelectElement).value;
    try { await api.updateTimelineItem(item.id, {start_time:start,end_time:end,transition}); await load(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Timeline edit failed"); }
  }
  async function validate() {
    if (!timeline) return;
    try { setTimeline(await api.validateTimeline(timeline.id)); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Timeline validation failed"); }
  }

  const sceneById = new Map(scenes.map((scene) => [scene.id, scene]));
  const visuals = timeline?.items.filter((item) => item.track === "VISUAL") ?? [];
  const voice = timeline?.items.find((item) => item.track === "VOICE");
  return <section className="research-section timeline-studio">
    <div className="section-heading"><div><div className="eyebrow">Phase 8</div><h2>Automatic timeline</h2><p>Build a deterministic visual and voice edit plan before any final export.</p></div><div className="actions"><button className="button secondary" disabled={!timeline || busy} onClick={validate}>Validate</button><button className="button" disabled={busy} onClick={rebuild}>{busy ? "Building…" : timeline ? "Rebuild timeline" : "Build timeline"}</button></div></div>
    {error && <div className="error">{error}</div>}
    {!timeline ? <div className="empty"><h2>No timeline yet</h2><p>Apply voice timing and select a visual for each scene, then build the timeline.</p></div> : <>
      <div className={`duration-bar ${timeline.valid ? "" : "mismatch"}`}><strong>Version {timeline.version}</strong><span>{timeline.duration.toFixed(2)} seconds</span><span>{timeline.output_resolution} · {timeline.fps} fps</span><span>{timeline.valid ? "✓ Valid timeline" : "⚠ Needs attention"}</span><span>{versions.length} saved version{versions.length === 1 ? "" : "s"}</span></div>
      {!!timeline.warnings_json.length && <div className="timeline-warnings">{timeline.warnings_json.map((warning, index) => <div className={warning.severity === "ERROR" ? "error" : "warning"} key={`${warning.code}-${warning.scene_id}-${index}`}><strong>{warning.code.replaceAll("_", " ")}:</strong> {warning.message}</div>)}</div>}
      <div className="timeline-ruler"><span>0s</span><span>{(timeline.duration / 2).toFixed(1)}s</span><span>{timeline.duration.toFixed(1)}s</span></div>
      <div className="timeline-track card"><strong>VISUAL</strong><div className="timeline-strip">{visuals.map((item) => <div className={`timeline-block ${item.metadata_json.auto_fill_reason ? "filler" : ""}`} style={{width:`${Math.max(2,(item.end_time-item.start_time)/timeline.duration*100)}%`}} title={`${item.start_time}s – ${item.end_time}s`} key={item.id}>#{sceneById.get(item.scene_id ?? -1)?.order ?? "fill"}</div>)}</div></div>
      <div className="timeline-track card"><strong>VOICE</strong><div className="timeline-strip"><div className="timeline-block voice-block" style={{width:"100%"}}>Voice #{voice?.voice_track_id} · {timeline.duration.toFixed(1)}s</div></div></div>
      <h3 className="generation-title">Ordered visual edit</h3><div className="timeline-items">{visuals.map((item) => { const scene = sceneById.get(item.scene_id ?? -1); const preview = String(item.metadata_json.preview_url ?? ""); const assetType = String(item.metadata_json.asset_type ?? ""); return <article className="card timeline-item" key={item.id}><div className="timeline-thumb">{assetType.includes("VIDEO") ? <video src={preview} controls preload="metadata" /> : preview ? <div style={{backgroundImage:`url("${preview}")`}} /> : <span>No preview</span>}</div><div><div className="stock-heading"><h3>{scene ? `Scene #${scene.order}` : "Automatic filler"}</h3><span className="pill">{item.effect?.replaceAll("_", " ")}</span></div><p>{scene?.narration_text ?? String(item.metadata_json.auto_fill_reason ?? "Gap fill")}</p><div className="timeline-edit"><label>Start<input id={`timeline-start-${item.id}`} type="number" step="0.01" defaultValue={item.start_time} /></label><label>End<input id={`timeline-end-${item.id}`} type="number" step="0.01" defaultValue={item.end_time} /></label><label>Transition<select id={`timeline-transition-${item.id}`} defaultValue={item.transition}><option>NONE</option><option>CUT</option><option>DISSOLVE</option></select></label><button className="text-button" onClick={() => saveItem(item)}>Save</button></div><small>Asset #{item.asset_id} · Source {item.source_in.toFixed(2)}–{item.source_out?.toFixed(2) ?? "still"} · {item.end_time-item.start_time}s</small></div></article>; })}</div>
      <details className="card render-plan"><summary>Intermediate render plan JSON</summary><pre>{JSON.stringify(timeline.render_plan_json, null, 2)}</pre></details>
    </>}
  </section>;
}
