const SESSION_KEY = "urlshortener_session";

function getSession() {
  const raw = localStorage.getItem(SESSION_KEY);
  return raw ? JSON.parse(raw) : null;
}

function setSession(data) {
  localStorage.setItem(SESSION_KEY, JSON.stringify(data));
}

function clearSession() {
  localStorage.removeItem(SESSION_KEY);
  localStorage.removeItem("usa_api_key"); // clear legacy dashboard key store too
}

function isLoggedIn() {
  return !!getSession()?.api_key;
}

async function verifySession() {
  const session = getSession();
  if (!session?.api_key) return false;

  try {
    const res = await fetch("/api/v1/auth/me", {
      headers: { "X-API-Key": session.api_key },
    });
    if (!res.ok) {
      clearSession();
      return false;
    }
    return true;
  } catch {
    return false; // network error — don't nuke session, just fail soft
  }
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
      <a href="/dashboard" class="nav-btn">Dashboard</a>
      <a href="/compare" class="nav-btn">Compare</a>
      <div id="navKeyIndicator" class="ml-1"></div>
      <button id="signout-btn" class="nav-btn text-red-600">Sign out</button>
    `;
    document.getElementById("signout-btn").addEventListener("click", () => {
      clearSession();
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

// nav-btn shared style, injected once
const style = document.createElement("style");
style.textContent = `.nav-btn { padding: 0.4rem 0.8rem; border-radius: 0.5rem; font-weight: 500; color: #374151; }
.nav-btn:hover { background: #f3f4f6; }`;
document.head.appendChild(style);

/**
 * Redirect to home if the user is NOT logged in.
 * Call this at the top of any page that requires authentication.
 */
function requireAuth() {
  if (!isLoggedIn()) {
    // Optional: pass a hint so home can show a message
    window.location.replace("/?auth=required");
    return false;
  }
  return true;
}

document.addEventListener("DOMContentLoaded", async () => {
  renderNavbar();
  // soft background check — clears stale/invalid keys, re-renders if state changed
  const wasLoggedIn = isLoggedIn();
  const stillValid = await verifySession();
  if (wasLoggedIn && !stillValid) renderNavbar();
});
