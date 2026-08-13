export type Project = {
  id: number;
  title: string;
  animal_topic: string | null;
  auto_topic: boolean;
  language: string;
  requested_duration_seconds: number;
  output_resolution: string;
  documentary_tone: string;
  status: "DRAFT" | "RESEARCHING" | "RESEARCH_REVIEW" | "SCRIPTING" | "SCRIPT_REVIEW" | "SCENE_PLANNING" | "SCENE_REVIEW" | "MEDIA_SEARCH" | "MEDIA_REVIEW" | "FAILED";
  current_phase: "FOUNDATION" | "RESEARCH" | "RESEARCH_REVIEW" | "SCRIPT" | "SCRIPT_REVIEW" | "SCENES" | "SCENE_REVIEW" | "MEDIA" | "MEDIA_REVIEW";
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
  source_page_url: string;
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
