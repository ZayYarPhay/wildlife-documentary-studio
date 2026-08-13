"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Scene, StockSearchBundle } from "@/types/project";

export function MediaPanel({projectId,onProjectChanged}:{projectId:number;onProjectChanged:()=>void}) {
  const [scenes,setScenes]=useState<Scene[]>([]);
  const [sceneId,setSceneId]=useState<number|null>(null);
  const [stock,setStock]=useState<StockSearchBundle|null>(null);
  const [searching,setSearching]=useState(false);
  const [error,setError]=useState("");
  useEffect(()=>{let active=true;api.getScenes(projectId).then(data=>{if(!active)return;setScenes(data.scenes);setSceneId(current=>current??data.scenes[0]?.id??null);if(!data.scenes.length)setStock(null);}).catch(e=>setError(e.message));return()=>{active=false};},[projectId]);
  useEffect(()=>{if(!sceneId)return;let active=true;api.getStock(sceneId).then(data=>{if(active)setStock(data)}).catch(e=>{if(active)setError(e.message)});return()=>{active=false};},[sceneId]);
  async function search(){if(!sceneId)return;setSearching(true);setError("");try{setStock(await api.searchStock(sceneId));onProjectChanged();}catch(e){setError(e instanceof Error?e.message:"Stock search failed");}finally{setSearching(false)}}
  async function select(assetId:number){await api.selectMediaAsset(assetId);if(sceneId)setStock(await api.getStock(sceneId));}
  async function reject(assetId:number){await api.rejectMediaAsset(assetId);if(sceneId)setStock(await api.getStock(sceneId));}
  const selectedScene=scenes.find(scene=>scene.id===sceneId);
  return <section className="research-section"><div className="section-heading"><div><div className="eyebrow">Phase 4</div><h2>Stock footage</h2><p>Search real footage first, compare transparent relevance scores and preserve source/license metadata.</p></div><button className="button" disabled={!sceneId||searching} onClick={search}>{searching?"Searching…":stock?.assets.length?"Search again":"Search stock"}</button></div>
    {error&&<div className="error">{error}</div>}{scenes.length===0?<div className="empty"><h2>No scenes available</h2><p>Generate a scene plan before searching for stock footage.</p></div>:<>
      <div className="media-scene-picker card"><label>Scene<select value={sceneId??""} onChange={e=>setSceneId(Number(e.target.value))}>{scenes.map(scene=><option key={scene.id} value={scene.id}>#{scene.order} · {scene.narration_text.slice(0,70)}</option>)}</select></label>{selectedScene&&<div><span className="pill">{selectedScene.visual_strategy.replaceAll("_"," ")}</span><p>{selectedScene.visual_description}</p></div>}</div>
      {stock?.warning&&<div className="warning"><strong>Mock provider:</strong> {stock.warning}</div>}
      {stock&&<div className="query-list"><strong>Search queries:</strong>{stock.queries.map(query=><span className="query-chip" key={query}>{query}</span>)}</div>}
      {stock&&!stock.assets.length&&<div className="empty"><h2>No candidates yet</h2><p>Search this scene to retrieve and rank stock-video candidates.</p></div>}
      <div className="stock-grid">{stock?.assets.map(asset=>{const title=String(asset.metadata_json.title??"Stock candidate");const selected=stock.selected_asset_id===asset.id;return <article className={`card stock-card ${selected?"selected":""} ${asset.status==="REJECTED"?"rejected":""}`} key={asset.id}><div className="stock-preview" role="img" aria-label={title} style={{backgroundImage:`url("${asset.preview_url}")`}}><span>{asset.type.replaceAll("_"," ")}</span></div><div className="stock-body"><div className="stock-heading"><h3>{title}</h3><span className="score">{Math.round(asset.relevance_score*100)}%</span></div><div className="meta"><span>{asset.width??"?"}×{asset.height??"?"}</span><span>•</span><span>{asset.duration??"?"} sec</span><span>•</span><span>{asset.provider}</span></div><p><strong>License:</strong> {asset.license??"Unconfirmed"}</p>{asset.attribution_requirements&&<small>{asset.attribution_requirements}</small>}<a className="source-link" href={asset.source_page_url} target="_blank" rel="noreferrer">Open source page ↗</a><div className="actions"><button className="button" disabled={selected} onClick={()=>select(asset.id)}>{selected?"Selected":"Select asset"}</button><button className="button secondary" disabled={asset.status==="REJECTED"} onClick={()=>reject(asset.id)}>Reject</button></div></div></article>})}</div>
    </>}
  </section>;
}
