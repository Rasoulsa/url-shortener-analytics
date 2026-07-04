const form = document.getElementById("register-form");
const errorEl = document.getElementById("register-error");

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

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  hideError();

  const payload = {
    email: document.getElementById("register-email").value.trim(),
    password: document.getElementById("register-password").value,
  };

  try {
    const res = await fetch("/session/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const body = await res.json().catch(() => null);

    if (!res.ok) {
      showError(extractError(body, "Registration failed. Try again."));
      return;
    }
    window.location.href = body.redirect || "/dashboard/";
  } catch {
    showError("Network error. Please try again.");
  }
});
