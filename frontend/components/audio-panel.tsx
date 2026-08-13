"use client";

import { FormEvent, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { AudioBundle, AudioSettings, Scene } from "@/types/project";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export function AudioPanel({ projectId }: { projectId: number }) {
  const [bundle, setBundle] = useState<AudioBundle | null>(null);
  const [settings, setSettings] = useState<AudioSettings | null>(null);
  const [scenes, setScenes] = useState<Scene[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    Promise.all([api.getAudio(projectId), api.getScenes(projectId)]).then(([audio, sceneBundle]) => {
      if (!active) return;
      setBundle(audio); setSettings(audio.settings); setScenes(sceneBundle.scenes);
    }).catch((reason) => { if (active) setError(reason.message); });
    return () => { active = false; };
  }, [projectId]);

  async function save() {
    if (!settings) return;
    setBusy(true); setError("");
    try {
      const { id: _id, project_id: _projectId, ...payload } = settings;
      void _id; void _projectId;
      const updated = await api.updateAudioSettings(projectId, payload);
      setBundle(updated); setSettings(updated.settings);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Audio settings failed"); }
    finally { setBusy(false); }
  }

  async function upload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError("");
    try { const updated = await api.uploadAudioAsset(projectId, new FormData(event.currentTarget)); setBundle(updated); setSettings(updated.settings); event.currentTarget.reset(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Audio upload failed"); }
    finally { setBusy(false); }
  }
  if (!bundle || !settings) return <section className="research-section"><p>{error || "Loading subtitle and audio settings…"}</p></section>;
  const music = bundle.assets.filter((asset) => asset.kind === "MUSIC");
  const ambient = bundle.assets.filter((asset) => asset.kind === "AMBIENT");
  return <section className="research-section audio-studio">
    <div className="section-heading"><div><div className="eyebrow">Phase 9</div><h2>Subtitles & voice-first audio</h2><p>Prepare export-only captions, licensed background music, and low-volume scene ambience.</p></div><button className="button" disabled={busy} onClick={save}>{busy ? "Saving…" : "Apply audio plan"}</button></div>
    {error && <div className="error">{error}</div>}
    <div className="audio-grid">
      <div className="card audio-settings"><h3>Subtitle preview</h3><div className={`subtitle-preview ${settings.subtitle_position.toLowerCase()}`}><span style={{fontSize:Math.max(12,settings.subtitle_font_size/2)}}>Wildlife narration appears here.</span></div><label className="toggle"><input type="checkbox" checked={settings.subtitles_enabled} onChange={(e)=>setSettings({...settings,subtitles_enabled:e.target.checked})}/> Enable subtitles during export</label><div className="compact-grid"><label>Font size<input type="number" min="18" max="96" value={settings.subtitle_font_size} onChange={(e)=>setSettings({...settings,subtitle_font_size:Number(e.target.value)})}/></label><label>Position<select value={settings.subtitle_position} onChange={(e)=>setSettings({...settings,subtitle_position:e.target.value as AudioSettings["subtitle_position"]})}><option>TOP</option><option>MIDDLE</option><option>BOTTOM</option></select></label><label>Safe margin<input type="number" min="0" max="300" value={settings.subtitle_safe_margin} onChange={(e)=>setSettings({...settings,subtitle_safe_margin:Number(e.target.value)})}/></label></div><div className="toggle-row"><label className="toggle"><input type="checkbox" checked={settings.subtitle_outline} onChange={(e)=>setSettings({...settings,subtitle_outline:e.target.checked})}/> Outline</label><label className="toggle"><input type="checkbox" checked={settings.subtitle_background} onChange={(e)=>setSettings({...settings,subtitle_background:e.target.checked})}/> Background</label></div>{bundle.srt_url && <a className="source-link" href={`${API_URL}${bundle.srt_url}`}>Download current SRT</a>}</div>
      <div className="card audio-settings"><h3>Music & ambience</h3><label className="toggle"><input type="checkbox" checked={settings.music_enabled} onChange={(e)=>setSettings({...settings,music_enabled:e.target.checked})}/> Enable background music</label><label>Licensed music<select value={settings.music_asset_id ?? ""} onChange={(e)=>setSettings({...settings,music_asset_id:e.target.value?Number(e.target.value):null})}><option value="">Select music</option>{music.map((asset)=><option value={asset.id} key={asset.id}>{asset.original_filename} · {asset.license}</option>)}</select></label><div className="compact-grid"><label>Music volume<input type="number" min="0" max="1" step="0.01" value={settings.music_volume} onChange={(e)=>setSettings({...settings,music_volume:Number(e.target.value)})}/></label><label>Fade in<input type="number" min="0" max="30" value={settings.music_fade_in} onChange={(e)=>setSettings({...settings,music_fade_in:Number(e.target.value)})}/></label><label>Fade out<input type="number" min="0" max="30" value={settings.music_fade_out} onChange={(e)=>setSettings({...settings,music_fade_out:Number(e.target.value)})}/></label><label>Ducking ratio<input type="number" min="2" max="20" value={settings.ducking_ratio} onChange={(e)=>setSettings({...settings,ducking_ratio:Number(e.target.value)})}/></label></div><label className="toggle"><input type="checkbox" checked={settings.ambient_enabled} onChange={(e)=>setSettings({...settings,ambient_enabled:e.target.checked})}/> Enable per-scene ambience</label><label>Ambient volume<input type="number" min="0" max="1" step="0.01" value={settings.ambient_volume} onChange={(e)=>setSettings({...settings,ambient_volume:Number(e.target.value)})}/></label><small>Voice is normalized first; music ducks under narration and the final mix uses a peak limiter.</small></div>
    </div>
    <form className="card audio-upload" onSubmit={upload}><h3>Upload licensed audio</h3><div className="compact-grid"><label>Audio file<input name="file" type="file" accept="audio/wav,audio/mpeg,audio/mp4" required/></label><label>Kind<select name="kind"><option value="MUSIC">Music</option><option value="AMBIENT">Ambient</option></select></label><label>Ambient scene<select name="scene_id"><option value="">Project music</option>{scenes.map((scene)=><option value={scene.id} key={scene.id}>Scene #{scene.order}</option>)}</select></label><label>Source / creator<input name="source_name" required/></label><label>License<input name="license" placeholder="CC0, CC BY 4.0…" required/></label><label>Source URL<input name="source_url" type="url"/></label><label>Attribution<input name="attribution"/></label></div><button className="button secondary" disabled={busy}>Upload audio</button></form>
    {!!ambient.length && <div className="card audio-library"><h3>Ambient library</h3>{ambient.map((asset)=><div key={asset.id}><audio controls preload="metadata" src={asset.public_url}/><span>{asset.original_filename} · Scene #{scenes.find((scene)=>scene.id===asset.scene_id)?.order} · {asset.license}</span></div>)}</div>}
    {Object.keys(bundle.mix_plan).length > 0 && <details className="card render-plan"><summary>Deterministic FFmpeg audio mix plan</summary><pre>{JSON.stringify(bundle.mix_plan,null,2)}</pre></details>}
  </section>;
}
