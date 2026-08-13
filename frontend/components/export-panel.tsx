"use client";

import { useCallback, useEffect, useState } from "react";
import { api, apiUrl } from "@/lib/api";
import { ExportBundle, ExportSettings } from "@/types/project";

const defaults: ExportSettings = {fps:24, crf:20, preset:"medium", subtitles_enabled:true, audio_mix_enabled:true};
const bytes = (value: number | null) => value === null ? "—" : value < 1_000_000 ? `${(value / 1000).toFixed(1)} KB` : `${(value / 1_000_000).toFixed(1)} MB`;

export function ExportPanel({projectId, onProjectChanged}:{projectId:number;onProjectChanged:()=>void}) {
  const [bundle,setBundle] = useState<ExportBundle|null>(null);
  const [settings,setSettings] = useState<ExportSettings>(defaults);
  const [busy,setBusy] = useState(false);
  const [error,setError] = useState("");
  const load = useCallback(async()=>setBundle(await api.getExport(projectId)),[projectId]);
  useEffect(()=>{let active=true;api.getExport(projectId).then((value)=>{if(active)setBundle(value);}).catch((reason)=>{if(active)setError(reason.message);});return()=>{active=false;};},[projectId]);
  const activeStatus = bundle?.current?.status;
  useEffect(()=>{
    if (!activeStatus || !["PENDING","RUNNING"].includes(activeStatus)) return;
    const timer=setInterval(()=>void load(),1500); return()=>clearInterval(timer);
  },[activeStatus,load]);
  const outputUrl=bundle?.download_url ? apiUrl(bundle.download_url):null;

  async function preflight(){setBusy(true);setError("");try{const report=await api.preflightExport(projectId,settings);setBundle((value)=>value?{...value,preflight:report}:value);}catch(reason){setError(reason instanceof Error?reason.message:"Preflight failed");}finally{setBusy(false);}}
  async function render(){setBusy(true);setError("");try{await api.startRender(projectId,settings);await load();onProjectChanged();}catch(reason){setError(reason instanceof Error?reason.message:"Render failed");}finally{setBusy(false);}}
  async function cancel(){if(!bundle?.current)return;await api.cancelRender(bundle.current.id);await load();onProjectChanged();}
  async function retry(){if(!bundle?.current)return;setBusy(true);try{await api.retryRender(bundle.current.id);await load();onProjectChanged();}catch(reason){setError(reason instanceof Error?reason.message:"Retry failed");}finally{setBusy(false);}}
  if(!bundle)return <section className="research-section"><div className="empty">Loading export studio…</div>{error&&<div className="error">{error}</div>}</section>;
  const job=bundle.current;
  return <section className="research-section export-studio">
    <div className="section-heading"><div><div className="eyebrow">Phase 12</div><h2>Final export</h2><p>Validate every production input, render in the background, and download a verified MP4.</p></div><div className="actions"><button className="button secondary" disabled={busy} onClick={preflight}>Run preflight</button><button className="button" disabled={busy||!bundle.preflight.ready||Boolean(job&&["PENDING","RUNNING"].includes(job.status))} onClick={render}>{busy?"Working…":"Start render"}</button></div></div>
    {error&&<div className="error">{error}</div>}
    <div className="details"><div className="card"><h3>Export settings</h3><div className="timeline-edit"><label>FPS<select value={settings.fps} onChange={(e)=>setSettings({...settings,fps:Number(e.target.value)})}><option value={24}>24</option><option value={25}>25</option><option value={30}>30</option></select></label><label>Quality (CRF)<input type="number" min={15} max={35} value={settings.crf} onChange={(e)=>setSettings({...settings,crf:Number(e.target.value)})}/></label><label>Preset<select value={settings.preset} onChange={(e)=>setSettings({...settings,preset:e.target.value as ExportSettings["preset"]})}><option>veryfast</option><option>fast</option><option>medium</option><option>slow</option></select></label></div><label className="check"><input type="checkbox" checked={settings.subtitles_enabled} onChange={(e)=>setSettings({...settings,subtitles_enabled:e.target.checked})}/> Burn subtitles into video</label><label className="check"><input type="checkbox" checked={settings.audio_mix_enabled} onChange={(e)=>setSettings({...settings,audio_mix_enabled:e.target.checked})}/> Include music and ambient mix</label></div>
      <div className="card"><h3>Storage sanity</h3><p>{bytes(bundle.preflight.free_bytes)} free</p><small>Estimated temporary space: {bytes(bundle.preflight.estimated_required_bytes)}</small></div></div>
    <div className="preflight-grid">{bundle.preflight.checks.map((check)=><article className={`card preflight-${check.status.toLowerCase()}`} key={check.code}><span className="pill">{check.status}</span><h3>{check.label}</h3><p>{check.detail}</p></article>)}</div>
    {job&&<div className="card render-status"><div className="stock-heading"><div><span className="pill">{job.status}</span><h3>Render #{job.id}</h3></div><strong>{Math.round(job.progress*100)}%</strong></div><div className="render-progress"><span style={{width:`${job.progress*100}%`}}/></div>{job.error_message&&<div className="error">{job.error_message}</div>}<div className="meta"><span>{job.duration?.toFixed(2)??"—"} sec</span><span>•</span><span>{job.width??"—"}×{job.height??"—"}</span><span>•</span><span>{bytes(job.file_size_bytes)}</span></div><div className="actions">{["PENDING","RUNNING"].includes(job.status)&&<button className="button danger" onClick={cancel}>Cancel render</button>}{["FAILED","CANCELED"].includes(job.status)&&<button className="button" disabled={busy} onClick={retry}>Retry render</button>}{outputUrl&&<a className="button" href={outputUrl} download>Download MP4</a>}</div>{job.logs&&<details className="render-plan"><summary>FFmpeg diagnostics</summary><pre>{job.logs.slice(-8000)}</pre></details>}</div>}
    {outputUrl&&job?.status==="COMPLETED"&&<div className="card"><h3>Final preview</h3><video className="final-preview" src={outputUrl} controls preload="metadata"/></div>}
    {!!bundle.jobs.length&&<details className="card render-plan"><summary>Render history ({bundle.jobs.length})</summary><ul>{bundle.jobs.map((item)=><li key={item.id}>#{item.id} · {item.status} · {new Date(item.created_at).toLocaleString()} · retry {item.retry_count}</li>)}</ul></details>}
  </section>;
}
