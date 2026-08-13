"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { DocumentaryScript, ScriptBundle, ScriptSection } from "@/types/project";

export function ScriptPanel({projectId, onProjectChanged}:{projectId:number; onProjectChanged:()=>void}) {
  const [bundle,setBundle]=useState<ScriptBundle|null>(null);
  const [selected,setSelected]=useState<DocumentaryScript|null>(null);
  const [fullText,setFullText]=useState("");
  const [state,setState]=useState<"loading"|"idle"|"generating"|"review"|"failed">("loading");
  const [error,setError]=useState("");
  async function load() { const data=await api.getScript(projectId); setBundle(data); setSelected(data.current); setFullText(data.current?.full_text??""); setState(data.current?"review":"idle"); }
  useEffect(()=>{ let active=true; api.getScript(projectId).then(data=>{if(!active)return;setBundle(data);setSelected(data.current);setFullText(data.current?.full_text??"");setState(data.current?"review":"idle");}).catch(e=>{if(!active)return;setError(e.message);setState("failed");});return()=>{active=false};},[projectId]);
  async function generate(){setState("generating");setError("");try{const data=await api.generateScript(projectId);setBundle(data);setSelected(data.current);setFullText(data.current?.full_text??"");setState("review");onProjectChanged();}catch(e){setError(e instanceof Error?e.message:"Script generation failed");setState("failed");onProjectChanged();}}
  async function saveFull(){if(!selected)return;await api.updateScript(selected.id,{full_text:fullText});await load();}
  async function saveSection(section:ScriptSection){const title=(document.getElementById(`section-title-${section.id}`) as HTMLInputElement).value;const text=(document.getElementById(`section-text-${section.id}`) as HTMLTextAreaElement).value;await api.updateScriptSection(section.id,{title,text});await load();}
  async function revise(section:ScriptSection,mode:"regenerate"|"shorten"|"expand"){await api.regenerateScriptSection(section.id,mode);await load();}
  async function approve(){if(!selected)return;await api.approveScript(selected.id);await load();}
  function chooseVersion(id:string){const script=bundle?.versions.find(v=>v.id===Number(id))??null;setSelected(script);setFullText(script?.full_text??"");}
  return <section className="research-section"><div className="section-heading"><div><div className="eyebrow">Phase 2</div><h2>Documentary script</h2><p>Narration generated only from approved research, with fact traceability per section.</p></div><button className="button" disabled={state==="generating"} onClick={generate}>{state==="generating"?"Generating…":bundle?.current?"Generate new version":"Generate script"}</button></div>
    {bundle?.warning&&<div className="warning"><strong>Mock LLM:</strong> {bundle.warning}</div>}{error&&<div className="error">{error} <button className="text-button" onClick={generate}>Retry</button></div>}
    {state==="idle"&&<div className="empty"><h2>No script yet</h2><p>Approve research facts first, then generate the first narration version.</p></div>}
    {selected&&<><div className="script-toolbar card"><label>Version<select value={selected.id} onChange={e=>chooseVersion(e.target.value)}>{bundle?.versions.map(v=><option key={v.id} value={v.id}>Version {v.version}{v.approved?" — approved":""}</option>)}</select></label><div className="script-metrics"><span><strong>{selected.estimated_words}</strong> words</span><span><strong>{Math.round(selected.estimated_duration_seconds/60*10)/10}</strong> min</span><span className={`pill ${selected.length_status.toLowerCase()}`}>{selected.length_status.replaceAll("_"," ")}</span></div><button className="button" disabled={selected.approved} onClick={approve}>{selected.approved?"Approved":"Approve script"}</button></div>
      <section className="card script-editor"><h3>Full narration</h3><p>Target: {bundle?.target_word_min}–{bundle?.target_word_max} words · Tone: {selected.tone}</p><textarea value={fullText} onChange={e=>setFullText(e.target.value)} rows={16}/><button className="button secondary" onClick={saveFull}>Save full script</button></section>
      <div className="script-sections"><h2>Sections</h2>{selected.sections.map(section=><article className="card section-editor" key={section.id}><div className="section-number">{section.order}</div><div><input id={`section-title-${section.id}`} defaultValue={section.title}/><textarea id={`section-text-${section.id}`} defaultValue={section.text} rows={7}/><small>{Math.round(section.estimated_duration_seconds)} sec · Source facts: {section.source_fact_ids.join(", ")}</small><div className="actions"><button className="text-button" onClick={()=>saveSection(section)}>Save</button><button className="text-button" onClick={()=>revise(section,"regenerate")}>Regenerate</button><button className="text-button" onClick={()=>revise(section,"shorten")}>Shorten</button><button className="text-button" onClick={()=>revise(section,"expand")}>Expand</button></div></div></article>)}</div></>}
  </section>;
}
