export type Project = {
  id: number;
  title: string;
  animal_topic: string | null;
  auto_topic: boolean;
  language: string;
  requested_duration_seconds: number;
  output_resolution: string;
  documentary_tone: string;
  status: "DRAFT" | "RESEARCHING" | "RESEARCH_REVIEW" | "SCRIPTING" | "SCRIPT_REVIEW" | "FAILED";
  current_phase: "FOUNDATION" | "RESEARCH" | "RESEARCH_REVIEW" | "SCRIPT" | "SCRIPT_REVIEW";
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
