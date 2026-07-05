import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { api, ApiError, tokens } from "./client.js";

// Build a fake fetch Response. `data` is returned from .json(); status 204
// short-circuits before json() is ever called (matches rawFetch).
function response(data, { status = 200, ok = status < 400 } = {}) {
  return {
    ok,
    status,
    statusText: `HTTP ${status}`,
    json: vi.fn().mockResolvedValue(data),
  };
}

// The BASE the client builds requests against — derived from the same env var
// the client reads, so it holds whether or not .env.local overrides the port.
const BASE = `${import.meta.env.VITE_API_URL || "http://localhost:8000/api"}/v1`;

let fetchMock;

beforeEach(() => {
  fetchMock = vi.fn();
  global.fetch = fetchMock;
  localStorage.clear();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("tokens", () => {
  it("persists and reads access/refresh from localStorage", () => {
    tokens.set({ access: "a1", refresh: "r1" });
    expect(tokens.access).toBe("a1");
    expect(tokens.refresh).toBe("r1");
    expect(localStorage.getItem("dr.access")).toBe("a1");
    expect(localStorage.getItem("dr.refresh")).toBe("r1");
  });

  it("only overwrites the values it is given", () => {
    tokens.set({ access: "a1", refresh: "r1" });
    tokens.set({ access: "a2" }); // no refresh → keep the old one
    expect(tokens.access).toBe("a2");
    expect(tokens.refresh).toBe("r1");
  });

  it("clears both tokens", () => {
    tokens.set({ access: "a1", refresh: "r1" });
    tokens.clear();
    expect(tokens.access).toBeNull();
    expect(tokens.refresh).toBeNull();
  });
});

describe("api.eventsUrl", () => {
  it("puts the access token and last_id in the query string", () => {
    tokens.set({ access: "tok en/+" });
    const url = new URL(api.eventsUrl("42", "7"));
    expect(url.pathname).toBe("/api/v1/runs/42/events");
    expect(url.searchParams.get("token")).toBe("tok en/+");
    expect(url.searchParams.get("last_id")).toBe("7");
  });

  it("defaults last_id to 0 and tolerates a missing token", () => {
    const url = new URL(api.eventsUrl("9"));
    expect(url.searchParams.get("last_id")).toBe("0");
    expect(url.searchParams.get("token")).toBe("");
  });
});

describe("api.listRuns", () => {
  it("omits the query string when no date range is given", async () => {
    fetchMock.mockResolvedValue(response([]));
    await api.listRuns();
    expect(fetchMock).toHaveBeenCalledWith(`${BASE}/runs`, expect.anything());
  });

  it("maps after/before to created_after/created_before", async () => {
    fetchMock.mockResolvedValue(response([]));
    await api.listRuns({ after: "2026-01-01", before: "2026-02-01" });
    const url = new URL(fetchMock.mock.calls[0][0]);
    expect(url.searchParams.get("created_after")).toBe("2026-01-01");
    expect(url.searchParams.get("created_before")).toBe("2026-02-01");
  });
});

describe("request construction", () => {
  it("login posts credentials without an auth header and stores the tokens", async () => {
    fetchMock.mockResolvedValue(response({ access: "A", refresh: "R" }));
    const data = await api.login("me@example.com", "pw");

    expect(data).toEqual({ access: "A", refresh: "R" });
    const [url, opts] = fetchMock.mock.calls[0];
    expect(url).toBe(`${BASE}/auth/token`);
    expect(opts.method).toBe("POST");
    expect(opts.headers.Authorization).toBeUndefined();
    expect(JSON.parse(opts.body)).toEqual({ email: "me@example.com", password: "pw" });
    expect(tokens.access).toBe("A");
  });

  it("authenticated calls attach the Bearer access token", async () => {
    tokens.set({ access: "A" });
    fetchMock.mockResolvedValue(response({ id: "1" }));
    await api.createRun("why is the sky blue?", "deep");

    const [url, opts] = fetchMock.mock.calls[0];
    expect(url).toBe(`${BASE}/runs`);
    expect(opts.headers.Authorization).toBe("Bearer A");
    expect(JSON.parse(opts.body)).toEqual({ question: "why is the sky blue?", depth: "deep" });
  });

  it("returns null for a 204 response without parsing a body", async () => {
    tokens.set({ access: "A" });
    const res = response(null, { status: 204 });
    fetchMock.mockResolvedValue(res);
    const out = await api.cancelRun("1");
    expect(out).toBeNull();
    expect(res.json).not.toHaveBeenCalled();
  });
});

describe("error surfacing", () => {
  it("throws an ApiError carrying status and data", async () => {
    tokens.set({ access: "A" });
    fetchMock.mockResolvedValue(response({ detail: "nope" }, { status: 403 }));
    await expect(api.getRun("1")).rejects.toMatchObject({
      name: "Error",
      status: 403,
      message: "nope",
    });
    await expect(api.getRun("1")).rejects.toBeInstanceOf(ApiError);
  });

  it("surfaces the first DRF field error", async () => {
    fetchMock.mockResolvedValue(
      response({ email: ["already registered", "second"] }, { status: 400 })
    );
    await expect(api.register({ email: "x" })).rejects.toMatchObject({
      message: "already registered",
    });
  });

  it("falls back to the status text when the body has no message", async () => {
    fetchMock.mockResolvedValue(response({}, { status: 500 }));
    await expect(api.getRun("1").catch((e) => e.message)).resolves.toBe("HTTP 500");
  });
});

describe("401 refresh-and-retry", () => {
  it("refreshes once and replays the original request", async () => {
    tokens.set({ access: "stale", refresh: "R" });
    fetchMock
      .mockResolvedValueOnce(response({ detail: "expired" }, { status: 401 })) // first /runs/1
      .mockResolvedValueOnce(response({ access: "fresh", refresh: "R2" })) // refresh
      .mockResolvedValueOnce(response({ id: "1" })); // replayed /runs/1

    const data = await api.getRun("1");
    expect(data).toEqual({ id: "1" });
    expect(tokens.access).toBe("fresh");

    // Third call is the replay and must carry the refreshed token.
    const replay = fetchMock.mock.calls[2];
    expect(replay[0]).toBe(`${BASE}/runs/1`);
    expect(replay[1].headers.Authorization).toBe("Bearer fresh");
  });

  it("clears tokens and throws when there is no refresh token", async () => {
    tokens.set({ access: "stale" }); // no refresh
    fetchMock.mockResolvedValue(response({ detail: "expired" }, { status: 401 }));

    await expect(api.getRun("1")).rejects.toMatchObject({ status: 401 });
    expect(tokens.access).toBeNull();
    expect(fetchMock).toHaveBeenCalledTimes(1); // never attempted a refresh
  });

  it("clears tokens when the refresh call itself fails", async () => {
    tokens.set({ access: "stale", refresh: "R" });
    fetchMock
      .mockResolvedValueOnce(response({ detail: "expired" }, { status: 401 })) // /runs/1
      .mockResolvedValueOnce(response({ detail: "bad refresh" }, { status: 401 })); // refresh

    await expect(api.getRun("1")).rejects.toMatchObject({ status: 401 });
    expect(tokens.access).toBeNull();
    expect(tokens.refresh).toBeNull();
  });
});
