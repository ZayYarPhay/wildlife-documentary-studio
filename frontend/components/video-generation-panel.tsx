"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Scene, ScenePrompt, VideoGenerationBundle } from "@/types/project";

export function VideoGenerationPanel({ projectId, onProjectChanged }: { projectId: number; onProjectChanged: () => void }) {
  const [scenes, setScenes] = useState<Scene[]>([]);
  const [sceneId, setSceneId] = useState<number | null>(null);
  const [bundle, setBundle] = useState<VideoGenerationBundle | null>(null);
  const [prompt, setPrompt] = useState("");
  const [duration, setDuration] = useState("5");
  const [fps, setFps] = useState("24");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const applyBundle = useCallback((data: VideoGenerationBundle) => {
    setBundle(data);
    const latest = data.prompts.find((item) => item.video_prompt.trim());
    setPrompt(latest?.video_prompt ?? "");
  }, []);
  const load = useCallback(async (id: number) => applyBundle(await api.getVideos(id)), [applyBundle]);

  useEffect(() => {
    let active = true;
    api.getScenes(projectId).then((data) => {
      if (!active) return;
      const eligible = data.scenes.filter((scene) => scene.visual_strategy === "AI_VIDEO");
      setScenes(eligible); setSceneId((current) => current ?? eligible[0]?.id ?? null);
    }).catch((reason) => setError(reason.message));
    return () => { active = false; };
  }, [projectId]);
  useEffect(() => {
    if (!sceneId) return;
    let active = true;
    api.getVideos(sceneId).then((data) => { if (active) applyBundle(data); })
      .catch((reason) => { if (active) setError(reason.message); });
    return () => { active = false; };
  }, [sceneId, applyBundle]);
  useEffect(() => {
    if (!sceneId || !bundle?.jobs.some((job) => ["PENDING", "RUNNING"].includes(job.status))) return;
    const timer = window.setInterval(() => load(sceneId).catch((reason) => setError(reason.message)), 1500);
    return () => window.clearInterval(timer);
  }, [sceneId, bundle?.jobs, load]);

  async function structuredPrompt() {
    if (!sceneId) return;
    setBusy(true); setError("");
    try { const created = await api.generateVideoPrompt(sceneId); setPrompt(created.video_prompt); await load(sceneId); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Prompt generation failed"); }
    finally { setBusy(false); }
  }
  async function saveVersion(): Promise<ScenePrompt | null> {
    if (!sceneId) return null;
    const saved = await api.saveVideoPrompt(sceneId, prompt); await load(sceneId); return saved;
  }
  async function generate() {
    if (!sceneId || !bundle?.selected_image_asset_id) return;
    setBusy(true); setError("");
    try {
      const saved = await saveVersion(); if (!saved) return;
      await api.generateVideo(sceneId, { prompt_id: saved.id, source_asset_id: bundle.selected_image_asset_id, duration: Number(duration), fps: Number(fps) });
      await load(sceneId); onProjectChanged();
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Video generation failed"); }
    finally { setBusy(false); }
  }
  async function retry(jobId: number) { try { await api.retryVideoJob(jobId); if (sceneId) await load(sceneId); } catch (reason) { setError(reason instanceof Error ? reason.message : "Retry failed"); } }
  async function select(assetId: number) { await api.selectMediaAsset(assetId); if (sceneId) await load(sceneId); }
  async function fallback(strategy: "AI_IMAGE_MOTION" | "STOCK_VIDEO") { if (!sceneId) return; applyBundle(await api.chooseVideoFallback(sceneId, strategy)); onProjectChanged(); setScenes((current) => current.filter((scene) => scene.id !== sceneId)); setSceneId(null); }

  return <section className="research-section image-studio video-studio">
    <div className="section-heading"><div><div className="eyebrow">Phase 6</div><h2>AI video studio</h2><p>Animate an approved scene image through a replaceable provider and validate every resulting clip.</p></div><button className="button secondary" disabled={!sceneId || busy} onClick={structuredPrompt}>New motion prompt</button></div>
    {error && <div className="error">{error}</div>}
    {!scenes.length ? <div className="empty"><h2>No AI video scenes</h2><p>Set a scene to AI_VIDEO, generate an AI image, and approve that image first.</p></div> : <>
      <div className="media-scene-picker card"><label>Video scene<select value={sceneId ?? ""} onChange={(event) => setSceneId(Number(event.target.value))}>{scenes.map((scene) => <option key={scene.id} value={scene.id}>#{scene.order} · {scene.species} · {scene.target_duration}s</option>)}</select></label><div><span className="pill">Source image #{bundle?.selected_image_asset_id ?? "not selected"}</span><p>An approved local AI image is required. Generate and select it in the image studio above.</p></div></div>
      {bundle?.warning && <div className="warning"><strong>Mock provider:</strong> {bundle.warning}</div>}
      <div className="image-workspace"><div className="card prompt-editor"><h3>Motion prompt</h3><label>Video prompt<textarea rows={10} value={prompt} onChange={(event) => setPrompt(event.target.value)} /></label><div className="video-settings"><label>Duration (seconds)<input type="number" min="1" max="10" step="0.5" value={duration} onChange={(event) => setDuration(event.target.value)} /></label><label>FPS<input type="number" min="12" max="60" value={fps} onChange={(event) => setFps(event.target.value)} /></label></div><div className="actions"><button className="button secondary" disabled={busy || prompt.length < 10} onClick={() => saveVersion().catch((reason) => setError(reason.message))}>Save version</button><button className="button" disabled={busy || prompt.length < 10 || !bundle?.selected_image_asset_id} onClick={generate}>{busy ? "Working…" : "Generate video"}</button></div></div>
        <div><h3>Video job history</h3><div className="job-list">{bundle?.jobs.map((job) => <div className={`card job-card ${job.status.toLowerCase()}`} key={job.id}><div><strong>Job #{job.id}</strong><span className="pill">{job.status}</span></div><div className="job-progress"><span style={{ width: `${Math.round(job.progress * 100)}%` }} /></div><small>Provider: {job.provider} · Retry: {job.retry_count}</small>{job.error_message && <div className="error">{job.error_message}</div>}{job.status === "FAILED" && !bundle.fallback_recommendations.length && <button className="button secondary" onClick={() => retry(job.id)}>Retry</button>}</div>)}</div></div></div>
      {!!bundle?.fallback_recommendations.length && <div className="warning"><strong>Video retries exhausted.</strong><p>Keep the approved image with motion editing later, or switch this scene back to stock footage.</p><div className="actions">{bundle.fallback_recommendations.map((strategy) => <button className="button secondary" key={strategy} onClick={() => fallback(strategy)}>Use {strategy.replaceAll("_", " ")}</button>)}</div></div>}
      <h3 className="generation-title">Generated clips</h3><div className="stock-grid">{bundle?.assets.map((asset) => { const selected = bundle.selected_asset_id === asset.id; return <article className={`card stock-card ${selected ? "selected" : ""}`} key={asset.id}><video className="video-preview" src={asset.preview_url} controls preload="metadata" /><div className="stock-body"><h3>Video generation #{asset.id}</h3><p>{asset.width}×{asset.height} · {asset.duration}s · {String(asset.metadata_json.fps)} fps</p><div className="actions"><button className="button" disabled={selected} onClick={() => select(asset.id)}>{selected ? "Approved" : "Approve / select"}</button><a className="button secondary" href={asset.download_url ?? asset.preview_url} download>Download MP4</a></div></div></article>; })}</div>
    </>}
  </section>;
}
