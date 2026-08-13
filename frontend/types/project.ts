export type Project = {
  id: number;
  title: string;
  animal_topic: string | null;
  auto_topic: boolean;
  language: string;
  requested_duration_seconds: number;
  output_resolution: string;
  documentary_tone: string;
  status: "DRAFT" | "RESEARCHING" | "RESEARCH_REVIEW" | "SCRIPTING" | "SCRIPT_REVIEW" | "SCENE_PLANNING" | "SCENE_REVIEW" | "MEDIA_SEARCH" | "MEDIA_REVIEW" | "IMAGE_GENERATING" | "IMAGE_REVIEW" | "VIDEO_GENERATING" | "VIDEO_REVIEW" | "VOICE_TRANSCRIBING" | "VOICE_REVIEW" | "VOICE_APPLIED" | "TIMELINE_BUILDING" | "TIMELINE_REVIEW" | "AUDIO_REVIEW" | "WORKFLOW_RUNNING" | "PIPELINE_PAUSED" | "VOICE_WAITING" | "RENDER_READY" | "RENDERING" | "COMPLETED" | "FAILED";
  current_phase: "FOUNDATION" | "RESEARCH" | "RESEARCH_REVIEW" | "SCRIPT" | "SCRIPT_REVIEW" | "SCENES" | "SCENE_REVIEW" | "MEDIA" | "MEDIA_REVIEW" | "IMAGES" | "IMAGE_REVIEW" | "VIDEOS" | "VIDEO_REVIEW" | "VOICE" | "VOICE_REVIEW" | "TIMELINE" | "TIMELINE_REVIEW" | "AUDIO" | "AUDIO_REVIEW" | "WORKFLOW" | "RENDER_READY" | "EXPORT";
  created_at: string;
  updated_at: string;
};

export type ResearchSource = {
  id: number;
  title: string;
  url: string;
  source_name: string;
  retrieved_at: string;
  metadata_json: Record<string, unknown>;
};

export type ResearchFact = {
  id: number;
  project_id: number;
  category: string;
  claim: string;
  confidence: number;
  approved: boolean;
  notes: string | null;
  source: ResearchSource;
};

export type ResearchBundle = {
  project_id: number;
  status: "idle" | "review";
  provider: string;
  is_mock: boolean;
  facts: ResearchFact[];
  warning: string | null;
};

export type ScriptSection = {
  id: number;
  order: number;
  title: string;
  text: string;
  estimated_duration_seconds: number;
  source_fact_ids: number[];
};

export type DocumentaryScript = {
  id: number;
  project_id: number;
  version: number;
  tone: string;
  full_text: string;
  estimated_words: number;
  estimated_duration_seconds: number;
  length_status: "TOO_SHORT" | "ON_TARGET" | "TOO_LONG";
  approved: boolean;
  created_at: string;
  sections: ScriptSection[];
};

export type ScriptBundle = {
  project_id: number;
  status: "idle" | "review";
  provider: string;
  is_mock: boolean;
  target_word_min: number;
  target_word_max: number;
  current: DocumentaryScript | null;
  versions: DocumentaryScript[];
  warning: string | null;
};

export type VisualStrategy = "STOCK_VIDEO" | "AI_IMAGE_MOTION" | "AI_VIDEO";

export type ScenePrompt = {
  id: number;
  image_prompt: string;
  negative_prompt: string;
  video_prompt: string;
  version: number;
};

export type Scene = {
  id: number;
  project_id: number;
  script_id: number;
  order: number;
  narration_text: string;
  start_time: number;
  end_time: number;
  target_duration: number;
  species: string;
  environment: string;
  animal_behavior: string;
  visual_description: string;
  shot_type: string;
  camera_motion: string;
  visual_strategy: VisualStrategy;
  status: "PENDING" | "READY" | "APPROVED" | "FAILED" | "SKIPPED";
  preferred_media_asset_id: number | null;
  prompts: ScenePrompt[];
};

export type MediaAsset = {
  id: number;
  project_id: number;
  scene_id: number;
  provider: string;
  provider_asset_id: string;
  type: "STOCK_VIDEO" | "STOCK_IMAGE" | "AI_IMAGE" | "AI_VIDEO" | "AUDIO" | "MUSIC" | "SFX";
  preview_url: string;
  download_url: string | null;
  source_page_url: string | null;
  creator: string | null;
  license: string | null;
  attribution_requirements: string | null;
  width: number | null;
  height: number | null;
  duration: number | null;
  local_path: string | null;
  metadata_json: Record<string, unknown>;
  relevance_score: number;
  status: "CANDIDATE" | "SELECTED" | "REJECTED" | "FAILED";
  created_at: string;
};

export type StockSearchBundle = {
  scene_id: number;
  provider: string;
  is_mock: boolean;
  queries: string[];
  selected_asset_id: number | null;
  assets: MediaAsset[];
  warning: string | null;
};

export type GenerationJob = {
  id: number;
  project_id: number;
  scene_id: number | null;
  job_type: string;
  provider: string;
  status: "PENDING" | "RUNNING" | "COMPLETED" | "FAILED" | "CANCELED";
  progress: number;
  retry_count: number;
  prompt_id: number | null;
  output_asset_id: number | null;
  seed: number | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
};

export type ImageGenerationBundle = {
  scene_id: number;
  provider: string;
  is_mock: boolean;
  selected_asset_id: number | null;
  prompts: ScenePrompt[];
  jobs: GenerationJob[];
  assets: MediaAsset[];
  warning: string | null;
};

export type VideoGenerationBundle = {
  scene_id: number;
  provider: string;
  is_mock: boolean;
  selected_asset_id: number | null;
  selected_image_asset_id: number | null;
  prompts: ScenePrompt[];
  jobs: GenerationJob[];
  assets: MediaAsset[];
  fallback_recommendations: ("AI_IMAGE_MOTION" | "STOCK_VIDEO")[];
  warning: string | null;
};

export type TranscriptSegment = {
  id: number;
  start_time: number;
  end_time: number;
  text: string;
  confidence: number | null;
};

export type SceneVoiceAlignment = {
  id: number;
  scene_id: number;
  recommended_start: number;
  recommended_end: number;
  confidence: number;
  mismatch: boolean;
  visual_adjustment: string;
  manually_edited: boolean;
};

export type VoiceTrack = {
  id: number;
  project_id: number;
  public_url: string;
  original_filename: string;
  mime_type: string;
  size_bytes: number;
  duration: number;
  language: string;
  status: "UPLOADED" | "TRANSCRIBING" | "READY" | "FAILED" | "APPLIED";
  alignment_confidence: number | null;
  mismatch_warning: string | null;
  metadata_json: Record<string, unknown>;
  created_at: string;
  segments: TranscriptSegment[];
  alignments: SceneVoiceAlignment[];
};

export type VoiceBundle = {
  project_id: number;
  provider: string;
  is_mock: boolean;
  active: VoiceTrack | null;
  tracks: VoiceTrack[];
  warning: string | null;
};

export type TimelineItem = {
  id: number;
  track: "VISUAL" | "VOICE" | "MUSIC" | "AMBIENT" | "SUBTITLE";
  order: number;
  scene_id: number | null;
  asset_id: number | null;
  voice_track_id: number | null;
  start_time: number;
  end_time: number;
  source_in: number;
  source_out: number | null;
  transition: string;
  effect: string | null;
  metadata_json: Record<string, unknown>;
};

export type Timeline = {
  id: number;
  project_id: number;
  voice_track_id: number;
  version: number;
  duration: number;
  output_resolution: string;
  fps: number;
  valid: boolean;
  warnings_json: {code:string;message:string;scene_id:number|null;severity:"WARNING"|"ERROR"}[];
  render_plan_json: Record<string, unknown>;
  created_at: string;
  items: TimelineItem[];
};

export type TimelineBundle = {
  project_id: number;
  current: Timeline | null;
  versions: Timeline[];
};

export type AudioAsset = {
  id: number;
  project_id: number;
  scene_id: number | null;
  kind: "MUSIC" | "AMBIENT";
  public_url: string;
  original_filename: string;
  mime_type: string;
  size_bytes: number;
  duration: number;
  source_name: string;
  source_url: string | null;
  license: string;
  attribution: string | null;
  created_at: string;
};

export type AudioSettings = {
  id: number;
  project_id: number;
  subtitles_enabled: boolean;
  subtitle_font_size: number;
  subtitle_position: "TOP" | "MIDDLE" | "BOTTOM";
  subtitle_outline: boolean;
  subtitle_background: boolean;
  subtitle_safe_margin: number;
  music_enabled: boolean;
  music_asset_id: number | null;
  music_volume: number;
  music_fade_in: number;
  music_fade_out: number;
  ducking_ratio: number;
  ambient_enabled: boolean;
  ambient_volume: number;
};

export type AudioBundle = {
  project_id: number;
  settings: AudioSettings;
  assets: AudioAsset[];
  srt_url: string | null;
  mix_plan: Record<string, unknown>;
};

export type WorkflowMode = "MANUAL" | "AUTO";
export type WorkflowRunStatus = "PENDING" | "RUNNING" | "PAUSED" | "VOICE_WAITING" | "FAILED" | "RENDER_READY" | "CANCELED";
export type WorkflowStepStatus = "PENDING" | "RUNNING" | "WAITING" | "COMPLETED" | "SKIPPED" | "FAILED";

export type WorkflowPolicy = {
  auto_approve_research: boolean;
  auto_approve_script: boolean;
  auto_select_media: boolean;
  generate_ai_video: boolean;
  fallback_missing_stock_to_image: boolean;
};

export type WorkflowStep = {
  id: number;
  name: string;
  order: number;
  status: WorkflowStepStatus;
  progress: number;
  attempts: number;
  operation: string | null;
  error_message: string | null;
  metadata_json: Record<string, unknown>;
  started_at: string | null;
  finished_at: string | null;
};

export type WorkflowRun = {
  id: number;
  project_id: number;
  mode: WorkflowMode;
  status: WorkflowRunStatus;
  current_step: string | null;
  current_operation: string | null;
  current_job_id: number | null;
  progress: number;
  pause_requested: boolean;
  policy_json: WorkflowPolicy;
  error_message: string | null;
  created_at: string;
  updated_at: string;
  finished_at: string | null;
  steps: WorkflowStep[];
};

export type WorkflowBundle = {
  project_id: number;
  current: WorkflowRun | null;
  runs: WorkflowRun[];
};

export type ExportSettings = {
  fps: number;
  crf: number;
  preset: "ultrafast" | "veryfast" | "faster" | "fast" | "medium" | "slow";
  subtitles_enabled: boolean;
  audio_mix_enabled: boolean;
};

export type PreflightCheck = {
  code: string;
  label: string;
  status: "PASS" | "WARNING" | "ERROR";
  detail: string;
};

export type PreflightReport = {
  project_id: number;
  timeline_id: number | null;
  ready: boolean;
  checks: PreflightCheck[];
  estimated_required_bytes: number;
  free_bytes: number;
};

export type RenderJob = {
  id: number;
  project_id: number;
  timeline_id: number | null;
  status: "PENDING" | "RUNNING" | "COMPLETED" | "FAILED" | "CANCELED";
  progress: number;
  retry_count: number;
  cancel_requested: boolean;
  settings_json: ExportSettings;
  validation_json: Record<string, unknown>;
  logs: string | null;
  output_path: string | null;
  duration: number | null;
  width: number | null;
  height: number | null;
  fps: number | null;
  file_size_bytes: number | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
  started_at: string | null;
  finished_at: string | null;
};

export type ExportBundle = {
  project_id: number;
  preflight: PreflightReport;
  current: RenderJob | null;
  jobs: RenderJob[];
  download_url: string | null;
};

export type ProjectStorageReport = {
  project_id: number;
  usage_bytes: number;
  file_count: number;
  missing_asset_ids: number[];
  generation_job_count: number;
  render_job_count: number;
};

export type SceneBundle = {
  project_id: number;
  status: "idle" | "review";
  total_duration: number;
  target_duration: number;
  duration_difference: number;
  scenes: Scene[];
};

export type ProjectCreate = Pick<
  Project,
  | "title"
  | "animal_topic"
  | "auto_topic"
  | "language"
  | "requested_duration_seconds"
  | "output_resolution"
  | "documentary_tone"
>;

export type TopicCategory = "MAMMALS" | "BIRDS" | "REPTILES" | "OCEAN" | "INSECTS" | "RARE_ANIMALS" | "PREDATORS";
export type VisualPreference = "ECONOMY" | "BALANCED" | "MAX_AI";
export type TopicSuggestion = {
  topic: string;
  scientific_name: string | null;
  category: TopicCategory;
  hook: string;
  stock_availability: "HIGH" | "MEDIUM" | "LOW";
  stock_score: number;
  production_difficulty: "EASY" | "MEDIUM" | "HARD";
  difficulty_reasons: string[];
  recommended_visual_mix: {stock:number;ai_image_motion:number;ai_video:number};
  recently_used: boolean;
};
export type TopicSuggestionBundle = {
  provider: string;
  is_mock: boolean;
  suggestions: TopicSuggestion[];
  excluded_recent_topics: string[];
  warning: string | null;
};
