const STORAGE_KEY = "pkm.lastVault";
const COOKIE_KEY = "pkm_last_vault";
const COOKIE_MAX_AGE_SECONDS = 60 * 60 * 24 * 365;

export function readRememberedVault() {
  const stored = readStoredVault();
  if (stored) return stored;
  return readCookieVault();
}

export function rememberVault(vault: string) {
  const name = vault.trim();
  if (!name) return;

  try {
    localStorage.setItem(STORAGE_KEY, name);
  } catch {
    // ignore — private-browsing restriction
  }

  try {
    document.cookie = `${COOKIE_KEY}=${encodeURIComponent(name)}; Max-Age=${COOKIE_MAX_AGE_SECONDS}; Path=/; SameSite=Lax`;
  } catch {
    // ignore — non-browser environments
  }
}

function readStoredVault() {
  try {
    return localStorage.getItem(STORAGE_KEY) || null;
  } catch {
    return null;
  }
}

function readCookieVault() {
  try {
    const prefix = `${COOKIE_KEY}=`;
    const entry = document.cookie
      .split(";")
      .map((part) => part.trim())
      .find((part) => part.startsWith(prefix));
    if (!entry) return null;
    return decodeURIComponent(entry.slice(prefix.length)) || null;
  } catch {
    return null;
  }
}
