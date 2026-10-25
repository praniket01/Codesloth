export const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";
export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, { ...init, headers: { "Content-Type": "application/json", ...(init?.headers || {}) }, cache: "no-store" });
  if (!response.ok) { let message = `Request failed (${response.status})`; try { const data = await response.json(); message = typeof data.detail === "string" ? data.detail : message; } catch {} throw new Error(message); }
  return response.json() as Promise<T>;
}
