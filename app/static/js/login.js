// ── Tab switching ─────────────────────────────────────────────────────────
const tabPassword = document.getElementById("tab-password");
const tabApikey = document.getElementById("tab-apikey");
const passwordForm = document.getElementById("login-password-form");
const apikeyForm = document.getElementById("login-apikey-form");
const errorEl = document.getElementById("login-error");

function activate(tab) {
  const isPw = tab === "password";

  passwordForm.classList.toggle("hidden", !isPw);
  apikeyForm.classList.toggle("hidden", isPw);

  tabPassword.className = isPw
    ? "tab-btn flex-1 py-2 rounded-lg bg-indigo-600 text-white font-medium"
    : "tab-btn flex-1 py-2 rounded-lg bg-gray-100 text-gray-700 font-medium";
  tabApikey.className = isPw
    ? "tab-btn flex-1 py-2 rounded-lg bg-gray-100 text-gray-700 font-medium"
    : "tab-btn flex-1 py-2 rounded-lg bg-indigo-600 text-white font-medium";

  hideError();
}

tabPassword.addEventListener("click", () => activate("password"));
tabApikey.addEventListener("click", () => activate("apikey"));

// ── Error helpers ─────────────────────────────────────────────────────────
function showError(msg) {
  errorEl.textContent = msg;
  errorEl.classList.remove("hidden");
}
function hideError() {
  errorEl.textContent = "";
  errorEl.classList.add("hidden");
}

function extractError(body, fallback) {
  return body?.errors?.[0]?.message || fallback;
}

// ── Submit handler (shared) ───────────────────────────────────────────────
async function submitLogin(payload) {
  hideError();
  try {
    const res = await fetch("/session/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const body = await res.json().catch(() => null);

    if (!res.ok) {
      showError(extractError(body, "Login failed. Check your credentials."));
      return;
    }
    window.location.href = body.redirect || "/dashboard/";
  } catch {
    showError("Network error. Please try again.");
  }
}

// ── Password form ─────────────────────────────────────────────────────────
passwordForm.addEventListener("submit", (e) => {
  e.preventDefault();
  submitLogin({
    email: document.getElementById("login-email").value.trim(),
    password: document.getElementById("login-password").value,
  });
});

// ── API key form ──────────────────────────────────────────────────────────
apikeyForm.addEventListener("submit", (e) => {
  e.preventDefault();
  submitLogin({
    api_key: document.getElementById("login-apikey").value.trim(),
  });
});
