/**
 * API client for pkm daemon.
 * Reads token from localStorage.pkm.token (or sessionStorage fallback).
 * Redirects to / on 401 (token expired or missing).
 */

function getToken() {
  try {
    return (
      localStorage.getItem('pkm.token') ||
      sessionStorage.getItem('pkm.token') ||
      null
    );
  } catch {
    return null;
  }
}

/**
 * Thin fetch wrapper that injects the Bearer token and handles 401.
 *
 * @param {string} path - API path (e.g. '/api/v1/vault/my-vault/notes')
 * @param {{ token?: string } & RequestInit} [opts] - fetch options; pass `token` to override stored token
 * @returns {Promise<Response>}
 */
export async function apiClient(path, opts = {}) {
  const { token: overrideToken, ...fetchOpts } = opts;
  const token = overrideToken ?? getToken();

  const headers = {
    'Content-Type': 'application/json',
    ...(fetchOpts.headers ?? {}),
    ...(token ? { Authorization: `Bearer ${token}` } : {})
  };

  const response = await fetch(path, { ...fetchOpts, headers });

  if (response.status === 401) {
    // Clear stale token and redirect to onboarding
    try {
      localStorage.removeItem('pkm.token');
      sessionStorage.removeItem('pkm.token');
    } catch {
      // ignore
    }
    if (typeof window !== 'undefined') {
      window.location.href = '/';
    }
  }

  return response;
}

/**
 * Convenience: GET + JSON parse.
 *
 * @template T
 * @param {string} path
 * @param {RequestInit} [opts]
 * @returns {Promise<T>}
 */
export async function apiGet(path, opts = {}) {
  const res = await apiClient(path, { method: 'GET', ...opts });
  if (!res.ok) throw new Error(`GET ${path} → ${res.status}`);
  return res.json();
}
