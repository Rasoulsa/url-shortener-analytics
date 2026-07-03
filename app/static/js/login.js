document.addEventListener("DOMContentLoaded", () => {
  const tabPassword = document.getElementById("tab-password");
  const tabApikey = document.getElementById("tab-apikey");
  const formPassword = document.getElementById("login-password-form");
  const formApikey = document.getElementById("login-apikey-form");
  const errorEl = document.getElementById("login-error");

  function activateTab(tab) {
    const isPassword = tab === "password";
    formPassword.classList.toggle("hidden", !isPassword);
    formApikey.classList.toggle("hidden", isPassword);
    tabPassword.classList.toggle("bg-indigo-600", isPassword);
    tabPassword.classList.toggle("text-white", isPassword);
    tabPassword.classList.toggle("bg-gray-100", !isPassword);
    tabPassword.classList.toggle("text-gray-700", !isPassword);
    tabApikey.classList.toggle("bg-indigo-600", !isPassword);
    tabApikey.classList.toggle("text-white", !isPassword);
    tabApikey.classList.toggle("bg-gray-100", isPassword);
    tabApikey.classList.toggle("text-gray-700", isPassword);
  }

  tabPassword.addEventListener("click", () => activateTab("password"));
  tabApikey.addEventListener("click", () => activateTab("apikey"));

  function showError(msg) {
    errorEl.textContent = msg;
    errorEl.classList.remove("hidden");
  }

  async function submitLogin(body) {
    errorEl.classList.add("hidden");
    try {
      const res = await fetch("/api/v1/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const json = await res.json();
      if (!res.ok) {
        showError(json.errors?.[0]?.message || "Login failed.");
        return;
      }
      setSession({ email: json.data.email, api_key: json.data.api_key });
      sessionStorage.setItem("usa_show_api_key", "1");
      window.location.href = "/dashboard";
    } catch {
      showError("Network error — is the API running?");
    }
  }

  formPassword.addEventListener("submit", (e) => {
    e.preventDefault();
    submitLogin({
      email: document.getElementById("login-email").value,
      password: document.getElementById("login-password").value,
    });
  });

  formApikey.addEventListener("submit", (e) => {
    e.preventDefault();
    submitLogin({ api_key: document.getElementById("login-apikey").value });
  });
});
