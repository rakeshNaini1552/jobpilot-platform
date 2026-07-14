/**
 * Typed API client — generated types from api/openapi.yaml keep the
 * frontend and backend contracts in lockstep at compile time.
 *
 * 401 handling: silently rotate the refresh token once and retry.
 * The refresh call is single-flight — concurrent 401s share one rotation,
 * because a second parallel refresh with the same token would trip the
 * backend's reuse detection and revoke every session.
 */
import createClient, { type Middleware } from "openapi-fetch";
import type { paths } from "./schema";
import { useAuthStore, type SessionUser } from "@/stores/auth";

let refreshInFlight: Promise<string | null> | null = null;

async function rotateTokens(): Promise<string | null> {
  const { refreshToken, setSession, logout } = useAuthStore.getState();
  if (!refreshToken) {
    logout();
    return null;
  }
  try {
    const resp = await fetch("/api/v1/auth/refresh", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });
    if (!resp.ok) {
      logout();
      return null;
    }
    const pair = (await resp.json()) as {
      access_token: string;
      refresh_token: string;
      user: SessionUser;
    };
    setSession(pair.access_token, pair.refresh_token, pair.user);
    return pair.access_token;
  } catch {
    logout();
    return null;
  }
}

const authMiddleware: Middleware = {
  onRequest({ request }) {
    const token = useAuthStore.getState().accessToken;
    if (token) request.headers.set("Authorization", `Bearer ${token}`);
    return request;
  },
  async onResponse({ request, response }) {
    if (response.status !== 401 || request.url.includes("/auth/")) {
      return response;
    }
    refreshInFlight ??= rotateTokens().finally(() => {
      refreshInFlight = null;
    });
    const newToken = await refreshInFlight;
    if (!newToken) return response;

    const retry = new Request(request, { headers: new Headers(request.headers) });
    retry.headers.set("Authorization", `Bearer ${newToken}`);
    return fetch(retry);
  },
};

// Paths in the generated schema are absolute (/api/v1/...), so no baseUrl prefix.
export const api = createClient<paths>({ baseUrl: "/" });
api.use(authMiddleware);
