export type MarketCode = "DE" | "FR";
export type RoleName = "company_owner" | "product_scout" | "amazon_operator";
export type ToolName = "get_product_spec" | "search_inventory";

export interface CurrentUser {
  user_id: string;
  tenant_id: string;
  email: string;
  display_name: string;
  roles: RoleName[];
  market_scopes: MarketCode[];
  synthetic_data: true;
}

export interface LoginResponse {
  access_token: string;
  token_type: "bearer";
  expires_in_seconds: number;
  user: CurrentUser;
}

export interface ThreadResponse {
  thread_id: string;
  title: string | null;
  status: "active" | "archived";
  created_at: string;
}

export interface EvidenceSummary {
  id: string;
  source_type: "database";
  source_name: "synthetic_inventory" | "synthetic_product_catalog";
  title: string;
  excerpt: string;
  observed_at: string;
  synthetic_data: true;
}

export interface InventoryResult {
  sku: string;
  product_name: string;
  market_code: MarketCode;
  warehouse_code: string;
  warehouse_name: string;
  on_hand: number;
  reserved: number;
  unsellable: number;
  inbound: number;
  safety_stock: number;
  available: number;
  snapshot_at: string;
  synthetic_data: true;
}

export interface ProductSpecResult {
  product_id: string;
  variant_id: string;
  sku: string;
  name_zh: string;
  name_en: string;
  status: "candidate" | "active" | "inactive" | "discontinued";
  specs: Array<{
    name: string;
    value: string;
    unit: string | null;
    verification_status: "demo_declared" | "unverified" | "verified";
  }>;
  synthetic_data: true;
}

export interface EvidenceDetail extends EvidenceSummary {
  source_locator: string;
  query_summary: Record<string, string | null>;
  structured_data: InventoryResult | ProductSpecResult;
  confidence: string | number | null;
  trust_level: "internal_demo";
  access_scope: {
    tenant_id: string;
    market_codes: MarketCode[];
  };
  created_at: string;
}

export interface ChatSuccessResponse {
  status: "completed";
  thread_id: string;
  message_id: string;
  answer: string;
  evidence: EvidenceSummary[];
  execution: {
    trace_id: string;
    route: "inventory_query" | "product_spec" | "unsupported";
    tool_names: ToolName[];
    duration_ms: number;
    status: "completed" | "failed" | "denied" | "timed_out";
  };
}

interface ApiErrorResponse {
  status: "error";
  error: {
    code: string;
    message: string;
    retryable: boolean;
    field: string | null;
  };
  trace_id: string | null;
}

const DEFAULT_API_BASE_URL = "http://127.0.0.1:8000/api/v1";
const configuredBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL?.trim();
export const API_BASE_URL = (configuredBaseUrl || DEFAULT_API_BASE_URL).replace(
  /\/$/,
  "",
);

export class ApiClientError extends Error {
  readonly status: number;
  readonly code: string;
  readonly retryable: boolean;
  readonly field: string | null;
  readonly traceId: string | null;

  constructor(status: number, payload?: ApiErrorResponse) {
    super(payload?.error.message ?? "后端暂时无法完成请求");
    this.name = "ApiClientError";
    this.status = status;
    this.code = payload?.error.code ?? "NETWORK_ERROR";
    this.retryable = payload?.error.retryable ?? true;
    this.field = payload?.error.field ?? null;
    this.traceId = payload?.trace_id ?? null;
  }
}

async function requestJson<T>(
  path: string,
  init: RequestInit = {},
  token?: string,
): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  if (init.body !== undefined) {
    headers.set("Content-Type", "application/json");
  }
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers,
      cache: "no-store",
    });
  } catch {
    throw new ApiClientError(0);
  }

  const payload: unknown = await response.json().catch(() => undefined);
  if (!response.ok) {
    throw new ApiClientError(
      response.status,
      isApiErrorResponse(payload) ? payload : undefined,
    );
  }
  return payload as T;
}

function isApiErrorResponse(value: unknown): value is ApiErrorResponse {
  if (typeof value !== "object" || value === null) return false;
  const candidate = value as Partial<ApiErrorResponse>;
  return (
    candidate.status === "error" &&
    typeof candidate.error === "object" &&
    candidate.error !== null &&
    typeof candidate.error.message === "string" &&
    typeof candidate.error.code === "string"
  );
}

export const m1Api = {
  login(email: string, password: string): Promise<LoginResponse> {
    return requestJson("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
  },

  me(token: string): Promise<CurrentUser> {
    return requestJson("/me", {}, token);
  },

  createThread(token: string, title: string): Promise<ThreadResponse> {
    return requestJson(
      "/threads",
      { method: "POST", body: JSON.stringify({ title }) },
      token,
    );
  },

  sendMessage(
    token: string,
    threadId: string,
    message: string,
  ): Promise<ChatSuccessResponse> {
    return requestJson(
      `/threads/${encodeURIComponent(threadId)}/messages`,
      { method: "POST", body: JSON.stringify({ message }) },
      token,
    );
  },

  evidence(token: string, evidenceId: string): Promise<EvidenceDetail> {
    return requestJson(
      `/evidence/${encodeURIComponent(evidenceId)}`,
      {},
      token,
    );
  },
};
