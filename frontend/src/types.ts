export type View = "conversations" | "tasks" | "automations" | "memory" | "settings";

export type TaskState =
  | "CREATED"
  | "PLANNING"
  | "READY"
  | "EXECUTING"
  | "VERIFYING"
  | "WAITING"
  | "AWAITING_APPROVAL"
  | "COMPLETED"
  | "FAILED"
  | "CANCELLED"
  | "TIMED_OUT";

export type Message = {
  role: "user" | "assistant";
  text: string;
  task_id?: string;
  state?: TaskState;
  error?: string;
  verified?: boolean;
};

export type Diagnostics = {
  runtime?: string;
  build_id?: string;
  task_id?: string;
  session_id?: string;
  action_id?: string;
  capability?: string;
  target?: string;
  target_identity?: string;
  execution_tier?: string | number;
  execution_strategy?: string;
  execution_method?: string;
  browser?: string;
  browser_name?: string;
  browser_pid?: number | null;
  browser_hwnd?: number | null;
  tab_index?: number | null;
  tab_title?: string | null;
  tab_url?: string | null;
  page_identity?: string | null;
  web_resolver?: string | null;
  before_state?: string | null;
  after_state?: string | null;
  identity_status?: "MATCHED" | "MISMATCHED" | "UNKNOWN" | string;
  verification_strategy?: string;
  verification_result?: boolean | null;
  verified?: boolean | null;
  state?: TaskState;
  final_state?: TaskState;
  latency_ms?: number;
  fallback_count?: number;
  vision_used?: boolean;
  mouse_used?: boolean;
  legacy_path_used?: boolean;
  error?: string;
  [key: string]: unknown;
};

export type Activity = {
  name: string;
  summary: string;
  status?: "pending" | "running" | "executing" | "verifying" | "completed" | "verified" | "failed" | string;
  capability?: string;
  target?: string;
  tier?: string | number;
  strategy?: string;
  verification_strategy?: string;
  verification_result?: boolean;
  latency_ms?: number;
  diagnostics?: Diagnostics;
};

export type Task = {
  id: string;
  title: string;
  status: TaskState | string;
  request: string;
  response: string;
  session_id?: string | null;
  created_at: string;
};

export type Memory = { id: string; content: string; category: string; created_at: string };

export type ProviderStatus = { provider: string; model: string; configured: boolean };

export type Confirmation = {
  call_id: string;
  name: string;
  arguments: Record<string, unknown>;
  permission: string;
};

export type Session = {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  task_count: number;
  preview: string;
};

export type ToolInfo = { name: string; description: string; permission: string };

export type RuntimeIdentity = {
  name: string;
  version: string;
  build_id: string;
  phase: string;
  supported_tiers: number[];
  status?: string;
  browser_detected?: boolean;
  browser_hwnd?: number | null;
  timestamp?: string;
  pid?: number;
  python_executable?: string;
  has_find_elements_by_query?: boolean;
  uia_engine_module_path?: string;
  browser_engine_class?: string;
  runtime_module_path?: string;
};
