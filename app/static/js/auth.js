let _cachedUser = null; // { email, api_key } once verified, else null

async function checkAuth() {
  try {
    const res = await fetch("/api/v1/auth/me");
    if (!res.ok) {
      _cachedUser = null;
      return null;
    }
    const body = await res.json();
    _cachedUser = body.data;
    return _cachedUser;
  } catch {
    return _cachedUser; // network error — fail soft, keep last known state
  }
}

function isLoggedIn() {
  return !!_cachedUser;
}

function renderNavbar() {
  const container = document.getElementById("navbar-actions");
  if (!container) return;

  const path = window.location.pathname;

  if (isLoggedIn()) {
    container.innerHTML = `
      <a href="/" class="nav-btn">Home</a>
      <a href="/create" class="nav-btn">Create</a>
      <a href="/links" class="nav-btn">My Links</a>
      <a href="/dashboard/" class="nav-btn">Dashboard</a>
      <a href="/dashboard/compare" class="nav-btn">Compare</a>
      <div id="navKeyIndicator" class="ml-1">
        ${_cachedUser.api_key ? "" : '<span class="text-amber-600 text-sm">⚠ No API key</span>'}
      </div>
      <button id="signout-btn" class="nav-btn text-red-600">Sign out</button>
    `;
    document.getElementById("signout-btn").addEventListener("click", async () => {
      await fetch("/session/logout", { method: "POST" });
      window.location.href = "/";
    });
  } else {
    const showLogin = path !== "/login";
    const showRegister = path !== "/register";

    container.innerHTML = `
      <a href="/" class="nav-btn">Home</a>
      ${showLogin ? `<a href="/login" class="nav-btn">Login</a>` : ""}
      ${showRegister ? `
        <a href="/register"
           class="bg-indigo-600 text-white px-4 py-2 rounded-lg font-medium hover:bg-indigo-700 transition">
          Sign Up
        </a>` : ""}
    `;
  }
}

const style = document.createElement("style");
style.textContent = `.nav-btn { padding: 0.4rem 0.8rem; border-radius: 0.5rem; font-weight: 500; color: #374151; }
.nav-btn:hover { background: #f3f4f6; }`;
document.head.appendChild(style);

/**
 * For any client-only page that still needs a soft guard
 * (server-gated pages like /dashboard don't need this — they redirect
 * before the template even renders).
 */
async function requireAuth() {
  await checkAuth();
  if (!isLoggedIn()) {
    window.location.replace("/?auth=required");
    return false;
  }
  return true;
}

document.addEventListener("DOMContentLoaded", async () => {
  await checkAuth();
  renderNavbar();
  document.dispatchEvent(new CustomEvent("authReady"));
});
