import { Project, ProjectCreate, ResearchBundle, ResearchFact } from "@/types/project";

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
};
