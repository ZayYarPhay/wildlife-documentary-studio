"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { TopicCategory, TopicSuggestion, VisualPreference } from "@/types/project";

const categories: {value:TopicCategory;label:string}[] = [
  {value:"MAMMALS",label:"Mammals"},{value:"BIRDS",label:"Birds"},{value:"REPTILES",label:"Reptiles"},
  {value:"OCEAN",label:"Ocean"},{value:"INSECTS",label:"Insects"},{value:"RARE_ANIMALS",label:"Rare animals"},{value:"PREDATORS",label:"Predators"},
];

export default function NewProject() {
  const router = useRouter();
  const [autoTopic,setAutoTopic] = useState(false);
  const [title,setTitle] = useState("");
  const [topic,setTopic] = useState("");
  const [duration,setDuration] = useState(5);
  const [category,setCategory] = useState<TopicCategory>("MAMMALS");
  const [preference,setPreference] = useState<VisualPreference>("BALANCED");
  const [suggestions,setSuggestions] = useState<TopicSuggestion[]>([]);
  const [pickerWarning,setPickerWarning] = useState("");
  const [error,setError] = useState("");
  const [busy,setBusy] = useState(false);
  const [suggesting,setSuggesting] = useState(false);

  async function suggest(surprise=false) {
    setSuggesting(true); setError("");
    try {
      const bundle=surprise ? await api.surpriseTopic(category,duration*60,preference) : await api.suggestTopics(category,duration*60,preference);
      setSuggestions(bundle.suggestions); setPickerWarning(bundle.warning??"");
      if(surprise&&bundle.suggestions[0]) choose(bundle.suggestions[0]);
    } catch(e) { setError(e instanceof Error?e.message:"Could not suggest topics"); }
    finally { setSuggesting(false); }
  }
  function choose(item:TopicSuggestion) {
    setTopic(item.topic);
    setTitle(`${item.topic} Documentary`);
  }
  async function submit(event:FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError("");
    const data=new FormData(event.currentTarget);
    if(!topic.trim()){setError("Choose or enter an animal topic before creating the project.");setBusy(false);return;}
    try {
      const project=await api.createProject({title,animal_topic:topic.trim(),auto_topic:autoTopic,language:String(data.get("language")),requested_duration_seconds:duration*60,output_resolution:String(data.get("resolution")),documentary_tone:String(data.get("tone"))});
      router.push(`/projects/${project.id}`);
    } catch(e) { setError(e instanceof Error?e.message:"Could not create project");setBusy(false); }
  }
  return <div className="form topic-project-form"><div className="eyebrow">New production · Phase 13</div><h1>Create a documentary</h1><p>Bring your own subject, or explore production-aware wildlife topics before creating the project.</p>
    {error&&<div className="error">{error}</div>}
    <form className="card form-grid" onSubmit={submit}>
      <label className="wide">Project title<input value={title} onChange={(e)=>setTitle(e.target.value)} required placeholder="Ghost of the Mountains"/></label>
      <label className="toggle wide"><input type="checkbox" checked={autoTopic} onChange={(e)=>{setAutoTopic(e.target.checked);setSuggestions([]);}}/> Help me choose a wildlife topic</label>
      {!autoTopic&&<label className="wide">Animal or topic<input value={topic} onChange={(e)=>setTopic(e.target.value)} required placeholder="Snow leopard"/></label>}
      <label>Duration<select value={duration} onChange={(e)=>{setDuration(Number(e.target.value));setSuggestions([]);}}>{Array.from({length:14},(_,i)=>i+2).map((m)=><option key={m} value={m}>{m} minutes</option>)}</select></label>
      <label>Language<select name="language"><option>English</option><option>Burmese</option><option>Thai</option></select></label>
      {autoTopic&&<div className="wide topic-picker">
        <div className="topic-picker-controls"><label>Wildlife category<select value={category} onChange={(e)=>{setCategory(e.target.value as TopicCategory);setSuggestions([]);}}>{categories.map((item)=><option value={item.value} key={item.value}>{item.label}</option>)}</select></label><label>Production mode<select value={preference} onChange={(e)=>{setPreference(e.target.value as VisualPreference);setSuggestions([]);}}><option value="ECONOMY">Economy · mostly stock</option><option value="BALANCED">Balanced</option><option value="MAX_AI">Max AI · more GPU work</option></select></label><div className="actions"><button type="button" className="button" disabled={suggesting} onClick={()=>suggest(false)}>{suggesting?"Exploring…":"Suggest topics"}</button><button type="button" className="button secondary" disabled={suggesting} onClick={()=>suggest(true)}>Surprise me</button></div></div>
        {pickerWarning&&<div className="warning">{pickerWarning}</div>}
        {!!suggestions.length&&<div className="topic-suggestions">{suggestions.map((item)=><article className={`topic-card ${topic===item.topic?"selected":""}`} key={item.topic}><div className="stock-heading"><div><h3>{item.topic}</h3><small><em>{item.scientific_name}</em></small></div><span className={`pill difficulty-${item.production_difficulty.toLowerCase()}`}>{item.production_difficulty}</span></div><p>{item.hook}</p><div className="topic-metrics"><span>Stock {item.stock_availability} · {item.stock_score}/100</span><span>{item.recently_used?"Recently used":"Fresh topic"}</span></div><div className="visual-mix"><span style={{width:`${item.recommended_visual_mix.stock}%`}}>Stock {item.recommended_visual_mix.stock}%</span><span style={{width:`${item.recommended_visual_mix.ai_image_motion}%`}}>Image {item.recommended_visual_mix.ai_image_motion}%</span><span style={{width:`${item.recommended_visual_mix.ai_video}%`}}>Video {item.recommended_visual_mix.ai_video}%</span></div><ul>{item.difficulty_reasons.map((reason)=><li key={reason}>{reason}</li>)}</ul><button type="button" className={topic===item.topic?"button secondary":"button"} onClick={()=>choose(item)}>{topic===item.topic?"✓ Selected":"Choose topic"}</button></article>)}</div>}
        {topic&&<div className="selected-topic"><strong>Selected topic:</strong> {topic}<button type="button" className="text-button" onClick={()=>setTopic("")}>Clear</button></div>}
      </div>}
      <label className="wide">Documentary tone<select name="tone"><option value="cinematic wildlife documentary">Cinematic wildlife documentary</option><option value="educational">Educational</option><option value="dramatic">Dramatic</option><option value="calm nature">Calm / nature</option><option value="family friendly">Family friendly</option></select></label>
      <label className="wide">Output resolution<select name="resolution"><option value="1920x1080">1080p — 1920×1080</option><option value="1280x720">720p — 1280×720</option></select></label>
      <div className="warning wide">Topic suggestions never start research, API billing, or GPU jobs. Work begins only after you create the project and explicitly start its workflow.</div>
      <div className="actions wide"><button className="button" disabled={busy||!topic.trim()}>{busy?"Creating…":"Create project"}</button><Link className="button secondary" href="/">Cancel</Link></div>
    </form>
  </div>;
}
