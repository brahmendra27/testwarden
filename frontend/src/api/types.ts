export interface RunSummary {
  id: number;
  run_uuid: string;
  status: string;
  framework: string;
  started_at: string | null;
  finished_at: string | null;
  branch: string | null;
  commit_sha: string | null;
  ci_url: string | null;
  environment: string | null;
  total: number;
  passed: number;
  failed: number;
  skipped: number;
  error_count: number;
  flaky_count: number;
  duration_ms: number;
  previous_run_id?: number | null;
  project_id?: number;
}

export interface ProjectCard {
  id: number;
  slug: string;
  name: string;
  repo_url: string | null;
  flaky_count: number;
  last_run: RunSummary | null;
  sparkline: { run_id: number; pass_rate: number | null; started_at: string | null }[];
}

/** [test_case_id, token, node_id] — token: P/A/F/E/K */
export type StripEntry = [number, string, string];

export interface ResultRow {
  result_id: number;
  test_case_id: number;
  node_id: string;
  file_path: string;
  title: string;
  status: string;
  is_flaky_in_run: boolean;
  attempt_count: number;
  duration_ms: number;
  error_type: string | null;
  error_message: string | null;
  extras: Record<string, unknown>;
}

export interface ArtifactInfo {
  id: number;
  kind: string;
  file_name: string;
  content_type: string;
  size_bytes: number;
  url: string;
}

export interface AttemptDetail {
  id: number;
  attempt_index: number;
  status: string;
  duration_ms: number;
  error_type: string | null;
  error_message: string | null;
  stack_trace: string | null;
  stdout: string | null;
  stderr: string | null;
  artifacts: ArtifactInfo[];
}

export interface ResultDetail {
  result_id: number;
  run_id: number;
  test_case_id: number;
  node_id: string;
  file_path: string;
  title: string;
  status: string;
  is_flaky_in_run: boolean;
  duration_ms: number;
  error_type: string | null;
  error_message: string | null;
  failure_fingerprint: string | null;
  extras: Record<string, unknown>;
  attempts: AttemptDetail[];
}

export interface WindowEntry {
  t: string;
  d: number;
  r: number;
}

export interface FlakyCase {
  id: number;
  node_id: string;
  file_path: string;
  title: string;
  flake_score: number;
  flip_count: number;
  last_status: string | null;
  recent_statuses: WindowEntry[];
  avg_duration_ms: number;
  stats_updated_at: string | null;
}

export interface HistoryEntry {
  result_id: number;
  run_id: number;
  run_started_at: string | null;
  branch: string | null;
  status: string;
  is_flaky_in_run: boolean;
  attempt_count: number;
  duration_ms: number;
  error_type: string | null;
  error_message: string | null;
  failure_fingerprint: string | null;
}

export interface TestDetail {
  id: number;
  project_id: number;
  node_id: string;
  file_path: string;
  suite: string | null;
  title: string;
  framework: string;
  last_status: string | null;
  flake_score: number;
  is_flaky: boolean;
  flip_count: number;
  avg_duration_ms: number;
  p95_duration_ms: number;
  recent_statuses: WindowEntry[];
  history: HistoryEntry[];
}

export interface CompareItem {
  test_case_id: number;
  node_id: string;
  file_path: string;
  title: string;
  base_status: string | null;
  head_status: string | null;
  head_flaky_in_run: boolean;
  error_message: string | null;
}

export interface CompareResult {
  base_run_id: number;
  head_run_id: number;
  counts: Record<string, number>;
  buckets: Record<string, CompareItem[]>;
}
