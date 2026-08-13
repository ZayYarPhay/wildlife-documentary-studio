"use client";

import { useCallback, useEffect, useState } from "react";
import { api, apiUrl } from "@/lib/api";
import { ThumbnailAsset, ThumbnailBundle } from "@/types/project";

export function ThumbnailPanel({projectId}:{projectId:number}) {
  const [bundle,setBundle]=useState<ThumbnailBundle|null>(null);
  const [overlay,setOverlay]=useState(false);
  const [overlayText,setOverlayText]=useState("");
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  const load=useCallback(async()=>setBundle(await api.getThumbnails(projectId)),[projectId]);
  useEffect(()=>{let active=true;api.getThumbnails(projectId).then((value)=>{if(active)setBundle(value);}).catch((reason)=>{if(active)setError(reason.message);});return()=>{active=false;};},[projectId]);
  const hasPending=bundle?.assets.some((item)=>item.status==="PENDING")??false;
  useEffect(()=>{if(!hasPending)return;const timer=setInterval(()=>void load(),1200);return()=>clearInterval(timer);},[hasPending,load]);
  async function concepts(){setBusy(true);setError("");try{setBundle(await api.generateThumbnailConcepts(projectId));}catch(reason){setError(reason instanceof Error?reason.message:"Concept generation failed");}finally{setBusy(false);}}
  async function generate(){setBusy(true);setError("");try{await api.generateThumbnails(projectId,{title_overlay:overlay,overlay_text:overlay?overlayText:undefined});await load();}catch(reason){setError(reason instanceof Error?reason.message:"Thumbnail generation failed");}finally{setBusy(false);}}
  async function action(asset:ThumbnailAsset,kind:"approve"|"reject"|"retry"){setError("");try{if(kind==="approve")await api.approveThumbnail(asset.id);else if(kind==="reject")await api.rejectThumbnail(asset.id);else await api.retryThumbnail(asset.id);await load();}catch(reason){setError(reason instanceof Error?reason.message:"Thumbnail action failed");}}
  if(!bundle)return <section className="research-section"><div className="empty">Loading thumbnail studio…</div>{error&&<div className="error">{error}</div>}</section>;
  const conceptById=new Map(bundle.concepts.map((item)=>[item.id,item]));
  return <section className="research-section thumbnail-studio">
    <div className="section-heading"><div><div className="eyebrow">Optional Phase 14</div><h2>Documentary thumbnails</h2><p>Develop three distinct 16:9 concepts after the final film is complete. Thumbnail generations never alter the video render.</p></div><div className="actions"><button className="button secondary" disabled={busy||!bundle.final_render_ready} onClick={concepts}>{bundle.concepts.length?"Regenerate concepts":"Create 3 concepts"}</button><button className="button" disabled={busy||!bundle.concepts.length||!bundle.final_render_ready||(overlay&&!overlayText.trim())} onClick={generate}>{busy?"Working…":"Generate all 3"}</button></div></div>
    {error&&<div className="error">{error}</div>}{!bundle.final_render_ready&&<div className="warning">Complete and validate the final MP4 in Export before creating thumbnails.</div>}{bundle.warning&&<div className="warning">{bundle.warning}</div>}
    <div className="card thumbnail-options"><label className="check"><input type="checkbox" checked={overlay} onChange={(e)=>setOverlay(e.target.checked)}/> Add an optional title overlay</label>{overlay&&<label>Overlay text<input maxLength={120} value={overlayText} onChange={(e)=>setOverlayText(e.target.value)} placeholder="Ghost of the Mountains"/></label>}<small>Default generation contains no text, logo or watermark.</small></div>
    {!!bundle.concepts.length&&<div className="thumbnail-concepts">{bundle.concepts.map((concept)=><article className="card" key={concept.id}><span className="pill">Concept {concept.concept_order} · v{concept.version}</span><h3>{concept.name}</h3><p>{concept.description}</p><details><summary>Identity-safe prompt</summary><p>{concept.prompt}</p><small>Negative: {concept.negative_prompt}</small></details></article>)}</div>}
    {!!bundle.assets.length&&<><h3 className="generation-title">Generation history</h3><div className="thumbnail-gallery">{bundle.assets.map((asset)=>{const concept=conceptById.get(asset.concept_id);const conceptName=concept?.name??String(asset.metadata_json.concept_name??`Concept #${asset.concept_id}`);return <article className={`card thumbnail-result ${asset.status==="APPROVED"?"approved":""}`} key={asset.id}>{asset.public_url?<div className="thumbnail-image" role="img" aria-label={`${conceptName} thumbnail`} style={{backgroundImage:`url("${asset.public_url}")`}}/>:<div className="thumbnail-placeholder">{asset.status}</div>}<div className="stock-heading"><div><h3>{conceptName}</h3><small>#{asset.id} · {asset.width}×{asset.height} · retry {asset.retry_count}</small></div><span className="pill">{asset.status}</span></div>{asset.overlay_text&&<p>Overlay: {asset.overlay_text}</p>}{asset.error_message&&<div className="error">{asset.error_message}</div>}<div className="actions">{asset.status==="COMPLETED"&&<><button className="button" onClick={()=>action(asset,"approve")}>Approve</button><button className="button secondary" onClick={()=>action(asset,"reject")}>Reject</button></>}{asset.status==="APPROVED"&&<button className="button secondary" onClick={()=>action(asset,"reject")}>Unapprove</button>}{["FAILED","REJECTED"].includes(asset.status)&&<button className="button" onClick={()=>action(asset,"retry")}>Regenerate</button>}{asset.public_url&&<a className="button secondary" href={apiUrl(`/api/thumbnail-assets/${asset.id}/download`)} download>Download PNG</a>}</div></article>;})}</div></>}
  </section>;
}
