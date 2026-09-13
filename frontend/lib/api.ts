export function browserServiceUrl(configured: string | undefined, port: number, protocol: "http" | "ws" = "http") {
  const browserHost = typeof window === "undefined" ? "127.0.0.1" : window.location.hostname;
  const fallback = `${protocol}://${browserHost}:${port}`;
  if (!configured || typeof window === "undefined") return configured ?? fallback;
  try {
    const url = new URL(configured);
    if (["127.0.0.1", "localhost"].includes(url.hostname) && !["127.0.0.1", "localhost"].includes(browserHost)) url.hostname = browserHost;
    return url.origin;
  } catch { return fallback; }
}

const GO_API = () => browserServiceUrl(process.env.NEXT_PUBLIC_GO_API_URL, 8787);
const PYTHON_API = () => browserServiceUrl(process.env.NEXT_PUBLIC_PYTHON_API_URL, 8001);
const TWITTER_API = "/api/phobos-twitter";

async function request<T>(base: string, path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  if (init?.body != null && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  const response = await fetch(`${base}${path}`, {
    ...init,
    headers,
    cache: "no-store",
  });
  const text = await response.text();
  let data: unknown = {};
  try { data = text ? JSON.parse(text) : {}; } catch { data = { error: text }; }
  if (!response.ok) {
    const message = typeof data === "object" && data && "error" in data ? String((data as { error: unknown }).error) : `${response.status} ${response.statusText}`;
    throw new Error(message);
  }
  return data as T;
}

export const goApi = {
  get: <T>(path: string) => request<T>(GO_API(), path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(GO_API(), path, { method: "POST", body: JSON.stringify(body ?? {}) }),
  put: <T>(path: string, body: unknown) =>
    request<T>(GO_API(), path, { method: "PUT", body: JSON.stringify(body) }),
  delete: <T>(path: string, body: unknown) =>
    request<T>(GO_API(), path, { method: "DELETE", body: JSON.stringify(body) }),
};

export const pythonApi = {
  get: <T>(path: string) => request<T>(PYTHON_API(), path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(PYTHON_API(), path, { method: "POST", body: JSON.stringify(body ?? {}) }),
  delete: <T>(path: string) => request<T>(PYTHON_API(), path, { method: "DELETE" }),
};

export const twitterApi = {
  get: <T>(path: string) => request<T>(TWITTER_API, path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(TWITTER_API, path, { method: "POST", body: JSON.stringify(body ?? {}) }),
  delete: <T>(path: string) => request<T>(TWITTER_API, path, { method: "DELETE" }),
};
