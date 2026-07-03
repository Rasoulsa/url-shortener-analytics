document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("register-form");
  const errorEl = document.getElementById("register-error");

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    errorEl.classList.add("hidden");

    const email = document.getElementById("register-email").value;
    const password = document.getElementById("register-password").value;

    try {
      const res = await fetch("/api/v1/auth/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      const json = await res.json();

      if (!res.ok) {
        errorEl.textContent = json.errors?.[0]?.message || "Registration failed.";
        errorEl.classList.remove("hidden");
        return;
      }

      setSession({ email: json.data.email, api_key: json.data.api_key });
      sessionStorage.setItem("usa_show_api_key", "1");
      window.location.href = "/dashboard";
    } catch {
      errorEl.textContent = "Network error — is the API running?";
      errorEl.classList.remove("hidden");
    }
  });
});
