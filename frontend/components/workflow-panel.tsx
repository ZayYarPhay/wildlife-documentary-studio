"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { WorkflowMode, WorkflowPolicy, WorkflowRun } from "@/types/project";

const DEFAULT_POLICY: WorkflowPolicy = {
  auto_approve_research: true,
  auto_approve_script: true,
  auto_select_media: true,
  generate_ai_video: true,
  fallback_missing_stock_to_image: true,
};

const STEP_TABS: Record<string,string> = {
  RESEARCH:"Research", SCRIPT:"Script", SCENES:"Scenes", MEDIA:"Media", IMAGES:"Media",
  VIDEOS:"Media", VOICE:"Voice-over", TIMELINE:"Timeline", AUDIO:"Timeline", RENDER_READY:"Export",
};

export function WorkflowPanel({ projectId, onOpenManual, onProjectChanged }: { projectId:number; onOpenManual:(tab:string)=>void; onProjectChanged:()=>void }) {
  const [run, setRun] = useState<WorkflowRun | null>(null);
  const [mode, setMode] = useState<WorkflowMode>("AUTO");
  const [policy, setPolicy] = useState(DEFAULT_POLICY);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    const refresh = () => api.getWorkflow(projectId).then((bundle) => { if (active) setRun(bundle.current); }).catch((reason) => { if (active) setError(reason.message); });
    refresh();
    const timer = window.setInterval(refresh, 2000);
    return () => { active = false; window.clearInterval(timer); };
  }, [projectId]);

  async function act(action: "start"|"pause"|"resume"|"retry"|"cancel") {
    setBusy(true); setError("");
    try {
      const updated = action === "start" ? await api.startWorkflow(projectId, mode, policy)
        : action === "pause" ? await api.pauseWorkflow(run!.id)
        : action === "resume" ? await api.resumeWorkflow(run!.id)
        : action === "retry" ? await api.retryWorkflow(run!.id)
        : await api.cancelWorkflow(run!.id);
      setRun(updated); onProjectChanged();
      window.setTimeout(() => api.getWorkflow(projectId).then((bundle)=>{setRun(bundle.current);onProjectChanged();}), 400);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Workflow action failed"); }
    finally { setBusy(false); }
  }

  const active = run && ["PENDING","RUNNING","PAUSED","VOICE_WAITING","FAILED"].includes(run.status);
  return <section className="card workflow-panel">
    <div className="workflow-heading"><div><div className="eyebrow">Phase 10</div><h2>One-click documentary pipeline</h2><p>A resumable coordinator over every implemented editor. Approved/manual work is reused, never silently regenerated.</p></div>{run && <span className={`workflow-status ${run.status.toLowerCase()}`}>{run.status.replaceAll("_"," ")}</span>}</div>
    {error && <div className="error">{error}</div>}
    {!active && <div className="workflow-launch"><label>Mode<select value={mode} onChange={(event)=>setMode(event.target.value as WorkflowMode)}><option value="AUTO">AUTO — continue by policy</option><option value="MANUAL">MANUAL — pause for review</option></select></label>{mode === "AUTO" && <><label className="toggle"><input type="checkbox" checked={policy.auto_approve_research} onChange={(event)=>setPolicy({...policy,auto_approve_research:event.target.checked})}/> Auto-approve sourced research</label><label className="toggle"><input type="checkbox" checked={policy.auto_approve_script} onChange={(event)=>setPolicy({...policy,auto_approve_script:event.target.checked})}/> Auto-approve generated script</label><label className="toggle"><input type="checkbox" checked={policy.auto_select_media} onChange={(event)=>setPolicy({...policy,auto_select_media:event.target.checked})}/> Auto-select available media</label><label className="toggle"><input type="checkbox" checked={policy.generate_ai_video} onChange={(event)=>setPolicy({...policy,generate_ai_video:event.target.checked})}/> Generate selected AI video scenes</label><label className="toggle"><input type="checkbox" checked={policy.fallback_missing_stock_to_image} onChange={(event)=>setPolicy({...policy,fallback_missing_stock_to_image:event.target.checked})}/> Fall back to local AI image when stock is unavailable</label></>}<button className="button" disabled={busy} onClick={()=>act("start")}>ONE CLICK GENERATE</button></div>}
    {run && <><div className="workflow-progress"><div><strong>{run.progress.toFixed(0)}%</strong><span>{run.current_operation ?? "Ready"}{run.current_job_id ? ` · Generation job #${run.current_job_id}` : ""}</span></div><progress max="100" value={run.progress}/></div><div className="workflow-steps">{run.steps.map((step)=><div className={`workflow-step ${step.status.toLowerCase()}`} key={step.id}><span>{step.order}</span><div><strong>{step.name.replaceAll("_"," ")}</strong><small>{step.operation}{step.attempts > 1 ? ` · ${step.attempts} attempts` : ""}</small>{step.error_message && <em>{step.error_message}</em>}</div></div>)}</div><div className="actions workflow-actions">{["PENDING","RUNNING"].includes(run.status) && <button className="button secondary" disabled={busy} onClick={()=>act("pause")}>Pause safely</button>}{["PAUSED","VOICE_WAITING"].includes(run.status) && <button className="button" disabled={busy} onClick={()=>act("resume")}>Resume</button>}{run.status === "FAILED" && <button className="button" disabled={busy} onClick={()=>act("retry")}>Retry failed step</button>}{active && <button className="text-button danger-text" disabled={busy} onClick={()=>act("cancel")}>Cancel run</button>}<button className="button secondary" onClick={()=>onOpenManual(STEP_TABS[run.current_step ?? ""] ?? "Research")}>Open manual editor</button></div>{run.status === "VOICE_WAITING" && <div className="warning">Upload narration in the Voice-over editor. AUTO mode resumes after transcription; MANUAL mode waits for your timing approval.</div>}</>}
  </section>;
}
