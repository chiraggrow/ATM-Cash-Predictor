const API_BASE_URL = import.meta.env.VITE_API_URL || "/api/v1";
const accessTokenKey = "atm-cash-access-token";

export function getAccessToken() {
  return sessionStorage.getItem(accessTokenKey);
}

export function saveAccessToken(token) {
  sessionStorage.setItem(accessTokenKey, token);
}

export function clearAccessToken() {
  sessionStorage.removeItem(accessTokenKey);
}

export async function apiRequest(path, { token, ...options } = {}) {
  const headers = new Headers(options.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);

  let response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...options,
      headers,
      signal: AbortSignal.timeout(20_000),
    });
  } catch (error) {
    if (error instanceof TypeError) {
      throw new Error("Unable to reach the API. Start the backend and try again.");
    }
    if (error instanceof DOMException && error.name === "TimeoutError") {
      throw new Error("The API request timed out. Check the backend and retry.");
    }
    throw error;
  }
  const isJson = response.headers.get("content-type")?.includes("application/json");
  const body = response.status === 204 || !isJson ? null : await response.json();

  if (!response.ok) {
    const message = typeof body?.detail === "string"
      ? body.detail
      : `Request failed (${response.status}).`;
    const error = new Error(message);
    error.status = response.status;
    throw error;
  }

  return body;
}

export async function createSession(username, password) {
  const body = new URLSearchParams({ username, password });
  const response = await apiRequest("/auth/token", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body,
  });
  saveAccessToken(response.access_token);
  return response.access_token;
}
