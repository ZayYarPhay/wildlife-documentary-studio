"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Scene, VoiceBundle } from "@/types/project";

export function VoicePanel({ projectId, onProjectChanged }: { projectId: number; onProjectChanged: () => void }) {
  const [bundle, setBundle] = useState<VoiceBundle | null>(null);
  const [scenes, setScenes] = useState<Scene[]>([]);
  const [upload, setUpload] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const load = useCallback(async () => {
    const [voice, sceneData] = await Promise.all([api.getVoice(projectId), api.getScenes(projectId)]);
    setBundle(voice); setScenes(sceneData.scenes);
  }, [projectId]);
  useEffect(() => {
    let active = true;
    Promise.all([api.getVoice(projectId), api.getScenes(projectId)]).then(([voice, sceneData]) => {
      if (!active) return;
      setBundle(voice); setScenes(sceneData.scenes);
    }).catch((reason) => { if (active) setError(reason.message); });
    return () => { active = false; };
  }, [projectId]);
  useEffect(() => {
    if (bundle?.active?.status !== "TRANSCRIBING") return;
    const timer = window.setInterval(() => load().catch((reason) => setError(reason.message)), 1500);
    return () => window.clearInterval(timer);
  }, [bundle?.active?.status, load]);

  async function uploadFile() {
    if (!upload) return;
    setBusy(true); setError("");
    try { setBundle(await api.uploadVoice(projectId, upload)); await load(); onProjectChanged(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Upload failed"); }
    finally { setBusy(false); }
  }
  async function retranscribe() {
    if (!bundle?.active) return;
    setBusy(true); setError("");
    try { setBundle(await api.retranscribeVoice(bundle.active.id)); await load(); onProjectChanged(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Transcription failed"); }
    finally { setBusy(false); }
  }
  async function saveSegment(id: number, text: string) {
    try { await api.updateTranscriptSegment(id, text); await load(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Transcript update failed"); }
  }
  async function saveAlignment(id: number, start: number, end: number) {
    try { await api.updateVoiceAlignment(id, start, end); await load(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Alignment update failed"); }
  }
  async function apply() {
    if (!bundle?.active) return;
    setBusy(true); setError("");
    try { setBundle(await api.applyVoiceTiming(bundle.active.id)); await load(); onProjectChanged(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Could not apply timing"); }
    finally { setBusy(false); }
  }

  const track = bundle?.active;
  const sceneById = new Map(scenes.map((scene) => [scene.id, scene]));
  return <section className="research-section voice-studio">
    <div className="section-heading"><div><div className="eyebrow">Phase 7</div><h2>Voice-over alignment</h2><p>Your uploaded narration becomes the final timing authority. Speech is never sped up or slowed down automatically.</p></div>{track && <button className="button secondary" disabled={busy || track.status === "TRANSCRIBING"} onClick={retranscribe}>Re-transcribe</button>}</div>
    {error && <div className="error">{error}</div>}
    <div className="card voice-upload"><label>Narration audio (WAV, MP3, M4A)<input type="file" accept=".wav,.mp3,.m4a,audio/wav,audio/mpeg,audio/mp4" onChange={(event) => setUpload(event.target.files?.[0] ?? null)} /></label><button className="button" disabled={!upload || busy} onClick={uploadFile}>{busy ? "Working…" : "Upload voice-over"}</button></div>
    {bundle?.warning && <div className="warning"><strong>Mock provider:</strong> {bundle.warning}</div>}
    {!track ? <div className="empty"><h2>No voice-over uploaded</h2><p>Upload the user&apos;s final narration after scenes are available.</p></div> : <>
      <div className="card voice-summary"><div><span className="pill">{track.status}</span><h3>{track.original_filename}</h3><p>{track.duration.toFixed(2)} seconds · {track.language} · {(track.size_bytes / 1024 / 1024).toFixed(1)} MB</p></div><audio src={track.public_url} controls preload="metadata" /></div>
      {track.mismatch_warning && <div className="warning"><strong>Script mismatch:</strong> {track.mismatch_warning}</div>}
      <div className="alignment-score"><strong>Overall alignment</strong><span>{track.alignment_confidence == null ? "Pending" : `${Math.round(track.alignment_confidence * 100)}%`}</span></div>
      <div className="voice-columns"><div><h3>Transcript</h3><div className="transcript-list">{track.segments.map((segment) => <div className="card transcript-segment" key={segment.id}><small>{segment.start_time.toFixed(2)}s – {segment.end_time.toFixed(2)}s · {segment.confidence == null ? "?" : `${Math.round(segment.confidence * 100)}%`}</small><textarea defaultValue={segment.text} rows={4} onBlur={(event) => { if (event.target.value !== segment.text) saveSegment(segment.id, event.target.value); }} /></div>)}</div></div>
        <div><h3>Scene timing recommendations</h3><div className="alignment-list">{[...track.alignments].sort((a, b) => a.recommended_start - b.recommended_start).map((alignment) => { const scene = sceneById.get(alignment.scene_id); return <div className={`card alignment-card ${alignment.mismatch ? "mismatch" : ""}`} key={alignment.id}><div><strong>Scene #{scene?.order ?? alignment.scene_id}</strong><span className="pill">{Math.round(alignment.confidence * 100)}%</span></div><p>{scene?.narration_text.slice(0, 100)}</p><div className="timing-inputs"><label>Start<input type="number" step="0.01" defaultValue={alignment.recommended_start} id={`start-${alignment.id}`} /></label><label>End<input type="number" step="0.01" defaultValue={alignment.recommended_end} id={`end-${alignment.id}`} /></label><button className="text-button" onClick={() => { const start = Number((document.getElementById(`start-${alignment.id}`) as HTMLInputElement).value); const end = Number((document.getElementById(`end-${alignment.id}`) as HTMLInputElement).value); saveAlignment(alignment.id, start, end); }}>Save</button></div><small>{alignment.visual_adjustment.replaceAll("_", " ")}{alignment.manually_edited ? " · manually edited" : ""}</small>{alignment.mismatch && <div className="error">Transcript differs from this scene narration.</div>}</div>; })}</div></div></div>
      <div className="voice-apply card"><div><h3>Apply narration timing</h3><p>This updates scene start/end/duration only. Script text and selected media remain untouched.</p></div><button className="button" disabled={busy || !track.alignments.length || track.status === "TRANSCRIBING"} onClick={apply}>{track.status === "APPLIED" ? "Re-apply timing" : "Apply timing"}</button></div>
    </>}
  </section>;
}
