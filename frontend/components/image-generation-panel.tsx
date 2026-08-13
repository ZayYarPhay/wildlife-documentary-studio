"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { ImageGenerationBundle, Scene, ScenePrompt } from "@/types/project";

export function ImageGenerationPanel({
  projectId,
  onProjectChanged,
}: {
  projectId: number;
  onProjectChanged: () => void;
}) {
  const [scenes, setScenes] = useState<Scene[]>([]);
  const [sceneId, setSceneId] = useState<number | null>(null);
  const [bundle, setBundle] = useState<ImageGenerationBundle | null>(null);
  const [prompt, setPrompt] = useState("");
  const [negative, setNegative] = useState("");
  const [seed, setSeed] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const applyBundle = useCallback((data: ImageGenerationBundle) => {
    setBundle(data);
    const latest = data.prompts[0];
    if (latest) {
      setPrompt(latest.image_prompt);
      setNegative(latest.negative_prompt);
    }
  }, []);

  const load = useCallback(async (selectedId: number) => {
    const data = await api.getImages(selectedId);
    applyBundle(data);
  }, [applyBundle]);

  useEffect(() => {
    let active = true;
    api.getScenes(projectId).then((data) => {
      if (!active) return;
      const eligible = data.scenes.filter((scene) => scene.visual_strategy !== "STOCK_VIDEO");
      setScenes(eligible);
      setSceneId((current) => current ?? eligible[0]?.id ?? null);
    }).catch((reason) => setError(reason.message));
    return () => { active = false; };
  }, [projectId]);

  useEffect(() => {
    if (!sceneId) return;
    let active = true;
    api.getImages(sceneId).then((data) => { if (active) applyBundle(data); })
      .catch((reason) => { if (active) setError(reason.message); });
    return () => { active = false; };
  }, [sceneId, applyBundle]);

  useEffect(() => {
    if (!sceneId || !bundle?.jobs.some((job) => ["PENDING", "RUNNING"].includes(job.status))) return;
    const timer = window.setInterval(() => load(sceneId).catch((reason) => setError(reason.message)), 1500);
    return () => window.clearInterval(timer);
  }, [sceneId, bundle?.jobs, load]);

  async function createStructuredPrompt() {
    if (!sceneId) return;
    setBusy(true); setError("");
    try {
      const created = await api.generateImagePrompt(sceneId);
      setPrompt(created.image_prompt); setNegative(created.negative_prompt);
      await load(sceneId);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Prompt generation failed"); }
    finally { setBusy(false); }
  }

  async function saveVersion(): Promise<ScenePrompt | null> {
    if (!sceneId) return null;
    const saved = await api.saveImagePrompt(sceneId, { image_prompt: prompt, negative_prompt: negative });
    await load(sceneId);
    return saved;
  }

  async function generate() {
    if (!sceneId) return;
    setBusy(true); setError("");
    try {
      const saved = await saveVersion();
      if (!saved) return;
      const numericSeed = seed.trim() ? Number(seed) : undefined;
      await api.generateImage(sceneId, { prompt_id: saved.id, seed: numericSeed });
      await load(sceneId); onProjectChanged();
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Image generation failed"); }
    finally { setBusy(false); }
  }

  async function retry(jobId: number) {
    setError("");
    try { await api.retryImageJob(jobId); if (sceneId) await load(sceneId); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Retry failed"); }
  }

  async function select(assetId: number) {
    await api.selectMediaAsset(assetId);
    if (sceneId) await load(sceneId);
  }

  const selectedScene = scenes.find((scene) => scene.id === sceneId);
  return <section className="research-section image-studio">
    <div className="section-heading"><div><div className="eyebrow">Phase 5</div><h2>AI image studio</h2><p>Create species-conscious 16:9 stills for AI image motion scenes while preserving every prompt and generation.</p></div><button className="button secondary" disabled={!sceneId || busy} onClick={createStructuredPrompt}>New structured prompt</button></div>
    {error && <div className="error">{error}</div>}
    {!scenes.length ? <div className="empty"><h2>No AI image scenes</h2><p>Set a scene strategy to AI_IMAGE_MOTION or AI_VIDEO in the Scenes tab.</p></div> : <>
      <div className="media-scene-picker card"><label>AI scene<select value={sceneId ?? ""} onChange={(event) => setSceneId(Number(event.target.value))}>{scenes.map((scene) => <option key={scene.id} value={scene.id}>#{scene.order} · {scene.species} · {scene.visual_strategy.replaceAll("_", " ")}</option>)}</select></label>{selectedScene && <div><span className="pill">{selectedScene.shot_type}</span><p>{selectedScene.visual_description}</p></div>}</div>
      {bundle?.warning && <div className="warning"><strong>Mock provider:</strong> {bundle.warning}</div>}
      <div className="image-workspace">
        <div className="card prompt-editor"><div className="stock-heading"><h3>Image prompt</h3><span className="pill">v{bundle?.prompts[0]?.version ?? "–"}</span></div><label>Positive prompt<textarea rows={12} value={prompt} onChange={(event) => setPrompt(event.target.value)} /></label><label>Negative / constraints<textarea rows={5} value={negative} onChange={(event) => setNegative(event.target.value)} /></label><label>Seed (optional)<input inputMode="numeric" value={seed} onChange={(event) => setSeed(event.target.value.replace(/\D/g, ""))} placeholder="Provider chooses when blank" /></label><div className="actions"><button className="button secondary" disabled={busy || prompt.length < 10 || negative.length < 3} onClick={() => saveVersion().catch((reason) => setError(reason.message))}>Save version</button><button className="button" disabled={busy || prompt.length < 10 || negative.length < 3} onClick={generate}>{busy ? "Working…" : "Generate image"}</button></div></div>
        <div><h3>Generation history</h3>{!bundle?.jobs.length && <div className="empty"><p>No image generations yet.</p></div>}<div className="job-list">{bundle?.jobs.map((job) => <div className={`card job-card ${job.status.toLowerCase()}`} key={job.id}><div><strong>Job #{job.id}</strong><span className="pill">{job.status}</span></div><div className="job-progress"><span style={{width:`${Math.round(job.progress * 100)}%`}} /></div><small>Provider: {job.provider} · Prompt #{job.prompt_id} · Seed: {job.seed ?? "automatic"} · Retry: {job.retry_count}</small>{job.error_message && <div className="error">{job.error_message}</div>}{job.status === "FAILED" && <button className="button secondary" onClick={() => retry(job.id)}>Retry</button>}</div>)}</div></div>
      </div>
      <h3 className="generation-title">Generated images</h3><div className="stock-grid">{bundle?.assets.map((asset) => { const selected = bundle.selected_asset_id === asset.id; return <article className={`card stock-card ${selected ? "selected" : ""}`} key={asset.id}><div className="stock-preview image-preview" role="img" aria-label={`Generated image ${asset.id}`} style={{backgroundImage:`url("${asset.preview_url}")`}}><span>AI IMAGE · {asset.width}×{asset.height}</span></div><div className="stock-body"><h3>Generation #{asset.id}</h3><p>Prompt v{String(asset.metadata_json.prompt_version ?? "?")} · Seed {String(asset.metadata_json.seed ?? "automatic")}</p><div className="actions"><button className="button" disabled={selected} onClick={() => select(asset.id)}>{selected ? "Approved" : "Approve / select"}</button><a className="button secondary" href={asset.download_url ?? asset.preview_url} download>Download preview</a></div></div></article>; })}</div>
    </>}
  </section>;
}
