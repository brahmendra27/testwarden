import { useQuery } from "@tanstack/react-query";
import type {
  CompareResult,
  FlakyCase,
  ProjectCard,
  ResultDetail,
  ResultRow,
  RunSummary,
  StripEntry,
  TestDetail,
} from "./types";

async function get<T>(url: string): Promise<T> {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}: ${url}`);
  }
  return response.json();
}

export const useProjects = () =>
  useQuery({ queryKey: ["projects"], queryFn: () => get<ProjectCard[]>("/api/v1/projects") });

export const useRuns = (slug: string, branch?: string) =>
  useQuery({
    queryKey: ["runs", slug, branch],
    queryFn: () =>
      get<RunSummary[]>(
        `/api/v1/projects/${slug}/runs?limit=50${branch ? `&branch=${encodeURIComponent(branch)}` : ""}`
      ),
  });

export const useBranches = (slug: string) =>
  useQuery({
    queryKey: ["branches", slug],
    queryFn: () => get<string[]>(`/api/v1/projects/${slug}/branches`),
  });

export const useRun = (runId: number | undefined) =>
  useQuery({
    queryKey: ["run", runId],
    queryFn: () => get<RunSummary>(`/api/v1/runs/${runId}`),
    enabled: runId != null,
  });

export const useRunStrip = (runId: number | undefined) =>
  useQuery({
    queryKey: ["strip", runId],
    queryFn: () => get<StripEntry[]>(`/api/v1/runs/${runId}/strip`),
    enabled: runId != null,
  });

export const useRunResults = (runId: number | undefined, status?: string, search?: string) =>
  useQuery({
    queryKey: ["results", runId, status, search],
    queryFn: () => {
      const params = new URLSearchParams();
      if (status) params.set("status", status);
      if (search) params.set("search", search);
      return get<ResultRow[]>(`/api/v1/runs/${runId}/results?${params}`);
    },
    enabled: runId != null,
  });

export const useResultDetail = (resultId: number | null) =>
  useQuery({
    queryKey: ["result", resultId],
    queryFn: () => get<ResultDetail>(`/api/v1/results/${resultId}`),
    enabled: resultId != null,
  });

export const useTestDetail = (caseId: number | undefined) =>
  useQuery({
    queryKey: ["test", caseId],
    queryFn: () => get<TestDetail>(`/api/v1/tests/${caseId}`),
    enabled: caseId != null,
  });

export const useFlaky = (slug: string) =>
  useQuery({
    queryKey: ["flaky", slug],
    queryFn: () => get<FlakyCase[]>(`/api/v1/projects/${slug}/flaky`),
  });

export const useCompare = (base: number | null, head: number | null) =>
  useQuery({
    queryKey: ["compare", base, head],
    queryFn: () => get<CompareResult>(`/api/v1/compare?base_run=${base}&head_run=${head}`),
    enabled: base != null && head != null,
  });
