const GO_API = process.env.NEXT_PUBLIC_GO_API_URL ?? "http://127.0.0.1:8787";
const PYTHON_API = process.env.NEXT_PUBLIC_PYTHON_API_URL ?? "http://127.0.0.1:8001";

async function request<T>(base: string, path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${base}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    cache: "no-store",
  });
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
  return response.json() as Promise<T>;
}

export const goApi = {
  get: <T>(path: string) => request<T>(GO_API, path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(GO_API, path, { method: "POST", body: JSON.stringify(body ?? {}) }),
  put: <T>(path: string, body: unknown) =>
    request<T>(GO_API, path, { method: "PUT", body: JSON.stringify(body) }),
  delete: <T>(path: string, body: unknown) =>
    request<T>(GO_API, path, { method: "DELETE", body: JSON.stringify(body) }),
};

export const pythonApi = {
  get: <T>(path: string) => request<T>(PYTHON_API, path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(PYTHON_API, path, { method: "POST", body: JSON.stringify(body ?? {}) }),
};
