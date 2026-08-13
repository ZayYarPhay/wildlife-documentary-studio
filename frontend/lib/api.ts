import { DocumentaryScript, GenerationJob, ImageGenerationBundle, MediaAsset, Project, ProjectCreate, ResearchBundle, ResearchFact, Scene, SceneBundle, ScenePrompt, SceneVoiceAlignment, ScriptBundle, ScriptSection, StockSearchBundle, TranscriptSegment, VideoGenerationBundle, VoiceBundle } from "@/types/project";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    ...options,
    headers: { "Content-Type": "application/json", ...options?.headers },
    cache: "no-store",
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(body?.error?.message ?? body?.detail ?? "Request failed");
  }
  return response.status === 204 ? (undefined as T) : response.json();
}

export const api = {
  listProjects: () => request<Project[]>("/api/projects"),
  getProject: (id: number) => request<Project>(`/api/projects/${id}`),
  createProject: (payload: ProjectCreate) =>
    request<Project>("/api/projects", { method: "POST", body: JSON.stringify(payload) }),
  updateProject: (id: number, payload: Partial<ProjectCreate>) =>
    request<Project>(`/api/projects/${id}`, { method: "PATCH", body: JSON.stringify(payload) }),
  deleteProject: (id: number) => request<void>(`/api/projects/${id}`, { method: "DELETE" }),
  getResearch: (projectId: number) =>
    request<ResearchBundle>(`/api/projects/${projectId}/research`),
  generateResearch: (projectId: number) =>
    request<ResearchBundle>(`/api/projects/${projectId}/research/generate`, { method: "POST" }),
  updateFact: (factId: number, payload: Partial<Pick<ResearchFact, "category" | "claim" | "confidence" | "approved" | "notes">>) =>
    request<ResearchFact>(`/api/research/facts/${factId}`, { method: "PATCH", body: JSON.stringify(payload) }),
  approveFact: (factId: number) =>
    request<ResearchFact>(`/api/research/facts/${factId}/approve`, { method: "POST" }),
  deleteFact: (factId: number) => request<void>(`/api/research/facts/${factId}`, { method: "DELETE" }),
  getScript: (projectId: number) => request<ScriptBundle>(`/api/projects/${projectId}/script`),
  generateScript: (projectId: number) =>
    request<ScriptBundle>(`/api/projects/${projectId}/script/generate`, { method: "POST" }),
  updateScript: (scriptId: number, payload: {full_text?: string; tone?: string}) =>
    request<DocumentaryScript>(`/api/scripts/${scriptId}`, { method: "PATCH", body: JSON.stringify(payload) }),
  updateScriptSection: (sectionId: number, payload: {title?: string; text?: string}) =>
    request<ScriptSection>(`/api/script-sections/${sectionId}`, { method: "PATCH", body: JSON.stringify(payload) }),
  regenerateScriptSection: (sectionId: number, mode: "regenerate" | "shorten" | "expand") =>
    request<ScriptSection>(`/api/script-sections/${sectionId}/regenerate`, { method: "POST", body: JSON.stringify({mode}) }),
  approveScript: (scriptId: number) => request<DocumentaryScript>(`/api/scripts/${scriptId}/approve`, { method: "POST" }),
  getScenes: (projectId: number) => request<SceneBundle>(`/api/projects/${projectId}/scenes`),
  generateScenes: (projectId: number) => request<SceneBundle>(`/api/projects/${projectId}/scenes/generate`, {method:"POST"}),
  createScene: (projectId: number, payload: Omit<Scene,"id"|"project_id"|"script_id"|"start_time"|"end_time"|"status"|"prompts"|"preferred_media_asset_id">) => request<Scene>(`/api/projects/${projectId}/scenes`, {method:"POST",body:JSON.stringify(payload)}),
  updateScene: (sceneId: number, payload: Partial<Scene>) => request<Scene>(`/api/scenes/${sceneId}`, {method:"PATCH",body:JSON.stringify(payload)}),
  deleteScene: (sceneId: number) => request<void>(`/api/scenes/${sceneId}`, {method:"DELETE"}),
  regenerateScene: (sceneId: number) => request<Scene>(`/api/scenes/${sceneId}/regenerate`, {method:"POST"}),
  reorderScenes: (projectId: number, sceneIds: number[]) => request<SceneBundle>(`/api/projects/${projectId}/scenes/reorder`, {method:"POST",body:JSON.stringify({scene_ids:sceneIds})}),
  getStock: (sceneId: number) => request<StockSearchBundle>(`/api/scenes/${sceneId}/stock`),
  searchStock: (sceneId: number) => request<StockSearchBundle>(`/api/scenes/${sceneId}/stock/search`, {method:"POST"}),
  selectMediaAsset: (assetId: number) => request<MediaAsset>(`/api/media-assets/${assetId}/select`, {method:"POST"}),
  rejectMediaAsset: (assetId: number) => request<MediaAsset>(`/api/media-assets/${assetId}/reject`, {method:"POST"}),
  getImages: (sceneId: number) => request<ImageGenerationBundle>(`/api/scenes/${sceneId}/images`),
  generateImagePrompt: (sceneId: number) => request<ScenePrompt>(`/api/scenes/${sceneId}/image-prompts/generate`, {method:"POST"}),
  saveImagePrompt: (sceneId: number, payload: {image_prompt:string;negative_prompt:string}) => request<ScenePrompt>(`/api/scenes/${sceneId}/image-prompts`, {method:"POST",body:JSON.stringify(payload)}),
  generateImage: (sceneId: number, payload: {prompt_id:number;seed?:number}) => request<GenerationJob>(`/api/scenes/${sceneId}/images/generate`, {method:"POST",body:JSON.stringify(payload)}),
  retryImageJob: (jobId: number) => request<GenerationJob>(`/api/image-jobs/${jobId}/retry`, {method:"POST"}),
  cancelImageJob: (jobId: number) => request<GenerationJob>(`/api/image-jobs/${jobId}/cancel`, {method:"POST"}),
  getVideos: (sceneId: number) => request<VideoGenerationBundle>(`/api/scenes/${sceneId}/videos`),
  generateVideoPrompt: (sceneId: number) => request<ScenePrompt>(`/api/scenes/${sceneId}/video-prompts/generate`, {method:"POST"}),
  saveVideoPrompt: (sceneId: number, videoPrompt: string) => request<ScenePrompt>(`/api/scenes/${sceneId}/video-prompts`, {method:"POST",body:JSON.stringify({video_prompt:videoPrompt})}),
  generateVideo: (sceneId: number, payload: {prompt_id:number;source_asset_id:number;duration?:number;fps?:number}) => request<GenerationJob>(`/api/scenes/${sceneId}/videos/generate`, {method:"POST",body:JSON.stringify(payload)}),
  retryVideoJob: (jobId: number) => request<GenerationJob>(`/api/video-jobs/${jobId}/retry`, {method:"POST"}),
  chooseVideoFallback: (sceneId: number, strategy: "AI_IMAGE_MOTION"|"STOCK_VIDEO") => request<VideoGenerationBundle>(`/api/scenes/${sceneId}/video-fallback`, {method:"POST",body:JSON.stringify({strategy})}),
  getVoice: (projectId: number) => request<VoiceBundle>(`/api/projects/${projectId}/voice`),
  uploadVoice: async (projectId: number, file: File) => {
    const form = new FormData(); form.append("file", file);
    const response = await fetch(`${API_URL}/api/projects/${projectId}/voice/upload`, {method:"POST",body:form});
    const body = await response.json().catch(() => null);
    if (!response.ok) throw new Error(body?.error?.message ?? body?.detail ?? "Upload failed");
    return body as VoiceBundle;
  },
  retranscribeVoice: (trackId: number) => request<VoiceBundle>(`/api/voice-tracks/${trackId}/transcribe`, {method:"POST"}),
  updateTranscriptSegment: (segmentId: number, text: string) => request<TranscriptSegment>(`/api/transcript-segments/${segmentId}`, {method:"PATCH",body:JSON.stringify({text})}),
  updateVoiceAlignment: (alignmentId: number, recommendedStart: number, recommendedEnd: number) => request<SceneVoiceAlignment>(`/api/voice-alignments/${alignmentId}`, {method:"PATCH",body:JSON.stringify({recommended_start:recommendedStart,recommended_end:recommendedEnd})}),
  applyVoiceTiming: (trackId: number) => request<VoiceBundle>(`/api/voice-tracks/${trackId}/apply`, {method:"POST"}),
};
