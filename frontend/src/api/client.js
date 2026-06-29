// Thin API client for the DeepResearch backend.
//
// Holds JWT access/refresh tokens in localStorage, attaches the access token to
// every request, and transparently refreshes it once on a 401 (FR-AUTH-4). The
// SSE endpoint can't carry an Authorization header, so a token-in-query URL
// builder is provided for EventSource.

const ROOT = import.meta.env.VITE_API_URL || "http://localhost:8000/api";
const BASE = `${ROOT}/v1`;

const ACCESS_KEY = "dr.access";
const REFRESH_KEY = "dr.refresh";

export const tokens = {
  get access() {
    return localStorage.getItem(ACCESS_KEY);
  },
  get refresh() {
    return localStorage.getItem(REFRESH_KEY);
  },
  set({ access, refresh }) {
    if (access) localStorage.setItem(ACCESS_KEY, access);
    if (refresh) localStorage.setItem(REFRESH_KEY, refresh);
  },
  clear() {
    localStorage.removeItem(ACCESS_KEY);
    localStorage.removeItem(REFRESH_KEY);
  },
};

export class ApiError extends Error {
  constructor(message, status, data) {
    super(message);
    this.status = status;
    this.data = data;
  }
}

function messageFrom(data, fallback) {
  if (!data) return fallback;
  if (typeof data === "string") return data;
  if (data.detail) return data.detail;
  // DRF field errors: {"field": ["msg", ...]} — surface the first one.
  const first = Object.values(data)[0];
  if (Array.isArray(first)) return first[0];
  return fallback;
}

async function rawFetch(path, { method = "GET", body, auth = true } = {}) {
  const headers = { "Content-Type": "application/json" };
  if (auth && tokens.access) headers.Authorization = `Bearer ${tokens.access}`;
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  const data = res.status === 204 ? null : await res.json().catch(() => null);
  if (!res.ok) throw new ApiError(messageFrom(data, res.statusText), res.status, data);
  return data;
}

async function tryRefresh() {
  if (!tokens.refresh) return false;
  try {
    const data = await rawFetch("/auth/token/refresh", {
      method: "POST",
      auth: false,
      body: { refresh: tokens.refresh },
    });
    tokens.set({ access: data.access, refresh: data.refresh });
    return true;
  } catch {
    return false;
  }
}

// Authenticated request with a single transparent refresh-and-retry on 401.
async function apiFetch(path, opts = {}) {
  try {
    return await rawFetch(path, opts);
  } catch (err) {
    if (err.status === 401 && opts.auth !== false && (await tryRefresh())) {
      return rawFetch(path, opts);
    }
    if (err.status === 401) tokens.clear();
    throw err;
  }
}

// --- endpoint helpers ------------------------------------------------------

export const api = {
  async login(email, password) {
    const data = await rawFetch("/auth/token", {
      method: "POST",
      auth: false,
      body: { email, password },
    });
    tokens.set(data);
    return data;
  },
  register(payload) {
    return rawFetch("/auth/register", { method: "POST", auth: false, body: payload });
  },
  me() {
    return apiFetch("/auth/me");
  },
  logout() {
    tokens.clear();
  },
  createRun(question, depth) {
    return apiFetch("/runs", { method: "POST", body: { question, depth } });
  },
  listRuns() {
    return apiFetch("/runs");
  },
  getRun(id) {
    return apiFetch(`/runs/${id}`);
  },
  cancelRun(id) {
    return apiFetch(`/runs/${id}/cancel`, { method: "POST" });
  },
  // EventSource URL for the SSE progress stream (token in query — see backend
  // QueryParamJWTAuthentication). lastId resumes from a prior event (FR-STR-3).
  eventsUrl(id, lastId = "0") {
    const params = new URLSearchParams({ token: tokens.access || "", last_id: lastId });
    return `${BASE}/runs/${id}/events?${params.toString()}`;
  },
};
