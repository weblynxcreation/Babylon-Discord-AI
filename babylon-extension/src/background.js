import { BABYLON_API_BASE } from "./config.js";

const ME_RE = /\/api\/me(\?|$)/;
const COMPANIES_RE = /\/api\/company\/mine(\?|$)/;
const GAME_RE = /\/api\/game\/([0-9a-f-]+)/;

async function getLocal(keys) {
  return chrome.storage.local.get(keys);
}
async function setLocal(obj) {
  return chrome.storage.local.set(obj);
}

async function getToken() {
  const { babylonToken } = await getLocal("babylonToken");
  return babylonToken ?? null;
}

async function apiFetch(path, options = {}) {
  const token = await getToken();
  const headers = { "Content-Type": "application/json", ...(options.headers ?? {}) };
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(`${BABYLON_API_BASE}${path}`, { ...options, headers });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    const message = body?.error?.message ?? `Request to ${path} failed (${res.status})`;
    throw new Error(message);
  }
  return body;
}

async function login(email, password) {
  const body = await apiFetch("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) });
  await setLocal({ babylonToken: body.token, babylonUser: body.user });
  await ensureLinked();
  return body.user;
}

async function logout() {
  await chrome.storage.local.clear();
}

// The ONLY thing this extension ever tells Babylon about a company's actual state: which
// companies this player belongs to, and whether they're the founder. Used only to bootstrap the
// founder relationship the first time a company is seen - Babylon independently confirms and
// maintains everything else (net worth, profit rate, member roster) itself from here on, by
// polling Capital Rift's own API with the relayed session cookie below. Nothing about a company's
// actual numbers is ever self-reported.
async function ensureLinked() {
  const { gameMe, gameCompanies, babylonToken } = await getLocal(["gameMe", "gameCompanies", "babylonToken"]);
  if (!babylonToken || !gameMe || !gameCompanies) return;

  try {
    const result = await apiFetch("/auth/extension-link", {
      method: "POST",
      body: JSON.stringify({ gameMe, gameCompanies }),
    });
    await setLocal({ linkedCompanies: result.linkedCompanies, linkError: null });
  } catch (err) {
    await setLocal({ linkError: String(err.message ?? err) });
  }
}

const SESSION_COOKIE_NAME = "_capitalrift_oauth2";
// Cookies barely change - no need to check anywhere near as often as a poll cycle.
const SESSION_COOKIE_SYNC_INTERVAL_MS = 5 * 60 * 1000;

// Relays the live Capital Rift session cookie so the server can independently poll the game's own
// API for everything about a company (see services/gameVerification.ts on the API side) - this is
// the one relay that actually unlocks verification, so it rides every trigger below rather than
// just one. Only ever sent to Babylon's own API over HTTPS, encrypted at rest there - see the
// Privacy Policy for the full disclosure.
async function syncSessionCookie(force = false) {
  const token = await getToken();
  if (!token) return;
  const key = "lastSessionCookieSyncAt";
  if (!force) {
    const stored = await getLocal(key);
    const lastSyncAt = stored[key] ?? 0;
    if (Date.now() - lastSyncAt < SESSION_COOKIE_SYNC_INTERVAL_MS) return;
  }
  try {
    const cookie = await chrome.cookies.get({ url: "https://play.capitalrift.com", name: SESSION_COOKIE_NAME });
    if (!cookie?.value) return;
    await apiFetch("/telemetry/session-cookie", { method: "POST", body: JSON.stringify({ cookie: cookie.value }) });
    await setLocal({ [key]: Date.now(), sessionCookieSyncError: null });
  } catch (err) {
    await setLocal({ sessionCookieSyncError: String(err.message ?? err) });
  }
}

async function handleGameApiObserved(url, data) {
  if (ME_RE.test(url)) {
    await setLocal({ gameMe: data });
    ensureLinked();
    syncSessionCookie();
    return;
  }
  if (COMPANIES_RE.test(url)) {
    await setLocal({ gameCompanies: data });
    ensureLinked();
    return;
  }
  if (GAME_RE.test(url)) {
    // The response itself is never relayed - the server polls this exact endpoint for real using
    // the session cookie (services/gameVerification.ts). This observation only re-triggers the
    // cookie relay, since it fires far more often than /api/me while someone's actually on their
    // dashboard - without this, a lapsed cookie could go unrenewed indefinitely even while the
    // player keeps actively playing.
    syncSessionCookie();
  }
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  (async () => {
    try {
      switch (message.type) {
        case "GAME_API_OBSERVED":
          await handleGameApiObserved(message.url, message.data);
          sendResponse({ ok: true });
          break;
        case "LOGIN": {
          const user = await login(message.email, message.password);
          sendResponse({ ok: true, user });
          break;
        }
        case "LOGOUT":
          await logout();
          sendResponse({ ok: true });
          break;
        case "GET_STATUS": {
          const all = await chrome.storage.local.get(null);
          sendResponse({ ok: true, status: all });
          break;
        }
        case "SYNC_NOW":
          // Forces an immediate cookie relay, bypassing the 5-minute throttle - there's nothing
          // else left to sync client-side. The server's own poll (running every minute) picks up
          // from there.
          await syncSessionCookie(true);
          sendResponse({ ok: true });
          break;
        default:
          sendResponse({ ok: false, error: "Unknown message type" });
      }
    } catch (err) {
      sendResponse({ ok: false, error: String(err.message ?? err) });
    }
  })();
  return true; // keep the message channel open for the async response
});
