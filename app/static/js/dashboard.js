// ─────────────────────────────────────────────────────────────────────────────
// dashboard.js — shared helpers for all pages
// Loaded once via base.html. All functions are global.
// ─────────────────────────────────────────────────────────────────────────────

const _API_KEY_STORAGE = "usa_api_key";

// ── API key persistence ───────────────────────────────────────────────────────
// Bridges to the auth.js session first (logged-in users never need to
// re-type their key), falling back to a manually-entered key for anyone
// testing analytics endpoints without logging in.

function getApiKey() {
  if (typeof getSession === "function") {
    const session = getSession();
    if (session?.api_key) return session.api_key;
  }
  return localStorage.getItem(_API_KEY_STORAGE) || "";
}

function setApiKey(key) {
  const trimmed = key.trim();
  if (trimmed) {
    localStorage.setItem(_API_KEY_STORAGE, trimmed);
  } else {
    localStorage.removeItem(_API_KEY_STORAGE);
  }
  _updateKeyIndicator();
}

function clearApiKey() {
  localStorage.removeItem(_API_KEY_STORAGE);
  _updateKeyIndicator();
}

// ── Nav key indicator ─────────────────────────────────────────────────────────
// Populates #navKeyIndicator, which auth.js renders inside the navbar
// for logged-in users.

function _updateKeyIndicator() {
  const el = document.getElementById("navKeyIndicator");
  if (!el) return;

  const key = getApiKey();
  if (key) {
    el.innerHTML = `
      <span class="flex items-center gap-1.5 text-xs text-emerald-600 font-medium">
        <span class="w-2 h-2 rounded-full bg-emerald-500 inline-block"></span>
        Key saved
      </span>`;
  } else {
    el.innerHTML = `
      <a href="/dashboard"
         class="text-xs text-amber-600 hover:text-amber-700 font-medium transition">
        ⚠ No API key
      </a>`;
  }
}

// Run on every page load
document.addEventListener("DOMContentLoaded", _updateKeyIndicator);

// ── Mask helper ───────────────────────────────────────────────────────────────

/**
 * Masks all but the first 6 and last 4 characters of a key, for display
 * before the user explicitly chooses to reveal it.
 *
 * @param {string} key
 * @returns {string}
 */
function maskKey(key) {
  if (!key || key.length < 10) return "••••••••";
  return key.slice(0, 6) + "•".repeat(Math.max(key.length - 10, 4)) + key.slice(-4);
}

// ── Fetch helpers ─────────────────────────────────────────────────────────────

/**
 * GET /api/v1/... with X-API-Key header.
 * Unwraps the { data, meta, errors } envelope.
 * Throws an Error with a human-readable message on failure.
 *
 * @param {string} url  Full URL or path
 * @returns {Promise<{data: any, meta: any, response: Response}>}
 */
async function apiFetch(url) {
  const res = await fetch(url, {
    headers: { "X-API-Key": getApiKey() },
  });

  const json = await res.json().catch(() => ({}));

  if (!res.ok) {
    const msg = json.errors?.[0]?.message ?? `HTTP ${res.status}`;
    throw new ApiError(msg, res.status);
  }

  return { data: json.data ?? json, meta: json.meta ?? null, response: res };
}

/**
 * POST /api/v1/... with X-API-Key header and JSON body.
 * Unwraps the { data, meta, errors } envelope.
 * Throws an Error with a human-readable message on failure.
 *
 * @param {string} url
 * @param {object} body
 * @returns {Promise<{data: any, meta: any, response: Response}>}
 */
async function apiPost(url, body) {
  const res = await fetch(url, {
    method: "POST",
    headers: {
      "X-API-Key": getApiKey(),
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
  });

  const json = await res.json().catch(() => ({}));

  if (!res.ok) {
    const msg = json.errors?.[0]?.message ?? `HTTP ${res.status}`;
    throw new ApiError(msg, res.status);
  }

  return { data: json.data ?? json, meta: json.meta ?? null, response: res };
}

/**
 * POST without authentication (for unauthenticated quick shorten).
 *
 * @param {string} url
 * @param {object} body
 * @returns {Promise<{data: any, meta: any, response: Response}>}
 */
async function apiPostAnon(url, body) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  const json = await res.json().catch(() => ({}));

  if (!res.ok) {
    const msg = json.errors?.[0]?.message ?? `HTTP ${res.status}`;
    throw new ApiError(msg, res.status);
  }

  return { data: json.data ?? json, meta: json.meta ?? null, response: res };
}

// ── Custom error class ────────────────────────────────────────────────────────

class ApiError extends Error {
  constructor(message, status = 0) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

// ── Rate limit reader ─────────────────────────────────────────────────────────

/**
 * Reads X-RateLimit-Remaining from a fetch Response object.
 * Returns null if the header is not present.
 *
 * @param {Response} response
 * @returns {number|null}
 */
function getRateLimitRemaining(response) {
  const val = response.headers.get("X-RateLimit-Remaining");
  return val !== null ? parseInt(val, 10) : null;
}

// ── UI helpers ────────────────────────────────────────────────────────────────

/**
 * Show an error or success banner inside a container element.
 *
 * @param {HTMLElement} el   The banner element
 * @param {string}      msg  Message text (HTML allowed)
 * @param {'error'|'success'|'info'} type
 */
function showBanner(el, msg, type = "error") {
  const styles = {
    error:   "bg-red-50 border-red-200 text-red-700",
    success: "bg-emerald-50 border-emerald-200 text-emerald-700",
    info:    "bg-blue-50 border-blue-200 text-blue-700",
  };
  el.className = `rounded-lg border px-4 py-3 text-sm mb-4 ${styles[type] ?? styles.error}`;
  el.innerHTML = msg;
  el.classList.remove("hidden");
}

/**
 * Hide a banner element.
 *
 * @param {HTMLElement} el
 */
function hideBanner(el) {
  el.classList.add("hidden");
  el.innerHTML = "";
}

/**
 * Set a status message element (inline, not a banner).
 *
 * @param {HTMLElement} el
 * @param {string}      msg
 * @param {boolean}     isError
 */
function setStatus(el, msg, isError = false) {
  el.textContent = msg;
  el.className = isError ? "text-sm text-red-500" : "text-sm text-gray-500";
}

// ── Copy to clipboard ─────────────────────────────────────────────────────────

/**
 * Copy text to clipboard. Temporarily changes the button label to "Copied!".
 *
 * @param {string}      text
 * @param {HTMLElement} btn   The button that was clicked
 */
async function copyToClipboard(text, btn) {
  try {
    await navigator.clipboard.writeText(text);
    const original = btn.textContent;
    btn.textContent = "Copied!";
    btn.disabled = true;
    setTimeout(() => {
      btn.textContent = original;
      btn.disabled = false;
    }, 2000);
  } catch {
    // Fallback for older browsers
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.style.position = "fixed";
    ta.style.opacity = "0";
    document.body.appendChild(ta);
    ta.select();
    document.execCommand("copy");
    document.body.removeChild(ta);
  }
}

// ── Short URL builder ─────────────────────────────────────────────────────────

/**
 * Build the full short URL from a short code.
 *
 * @param {string} code
 * @returns {string}
 */
function buildShortUrl(code) {
  return `${window.location.origin}/${code}`;
}

// ── Format helpers ────────────────────────────────────────────────────────────

/**
 * Format a number with locale-aware thousands separators.
 *
 * @param {number} n
 * @returns {string}
 */
function formatNumber(n) {
  return (n ?? 0).toLocaleString();
}

/**
 * Format an ISO date string to a readable local date.
 * Returns "Never" for null/undefined.
 *
 * @param {string|null} iso
 * @returns {string}
 */
function formatDate(iso) {
  if (!iso) return "Never";
  return new Date(iso).toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

/**
 * Truncate a string to maxLen characters, adding "…" if cut.
 *
 * @param {string} str
 * @param {number} maxLen
 * @returns {string}
 */
function truncate(str, maxLen = 60) {
  if (!str) return "";
  return str.length > maxLen ? str.slice(0, maxLen) + "…" : str;
}

// ── Input binding helper ──────────────────────────────────────────────────────

/**
 * Bind an API key input field so that:
 * - it is pre-filled from localStorage on load
 * - changes are saved to localStorage immediately
 *
 * @param {string} inputId  The id of the <input> element
 */
function bindApiKeyInput(inputId) {
  const input = document.getElementById(inputId);
  if (!input) return;

  input.value = getApiKey();

  input.addEventListener("input", () => setApiKey(input.value));
}
