// Unified API config.
// Local development keeps the same-origin proxy behavior.
// Production/Vercel can set NEXT_PUBLIC_API_BASE_URL to a public backend URL.
const rawApiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL?.trim() || "";

export const API_BASE_URL = rawApiBaseUrl.replace(/\/+$/, "");
export const API_PREFIX = "/api";

export function apiUrl(path: string): string {
  const p = path.startsWith("/") ? path : `/${path}`;
  return `${API_BASE_URL}${API_PREFIX}${p}`;
}

// Knowledge-base/document/import APIs need current agent user id.
export function getAgentHeaders(): Record<string, string> {
  if (typeof window === "undefined") return {};
  const id = window.localStorage.getItem("agent_user_id");
  if (!id) return {};
  return { "X-User-Id": id };
}

