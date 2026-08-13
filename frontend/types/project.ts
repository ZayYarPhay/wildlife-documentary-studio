export type Project = {
  id: number;
  title: string;
  animal_topic: string | null;
  auto_topic: boolean;
  language: string;
  requested_duration_seconds: number;
  output_resolution: string;
  status: "DRAFT" | "RESEARCHING" | "RESEARCH_REVIEW" | "FAILED";
  current_phase: "FOUNDATION" | "RESEARCH" | "RESEARCH_REVIEW";
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

export type ProjectCreate = Pick<
  Project,
  | "title"
  | "animal_topic"
  | "auto_topic"
  | "language"
  | "requested_duration_seconds"
  | "output_resolution"
>;
