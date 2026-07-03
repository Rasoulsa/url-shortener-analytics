const params = new URLSearchParams(window.location.search);
if (params.get("auth") === "required") {
    const banner = document.createElement("div");
    banner.className =
      "max-w-xl mx-auto mb-6 rounded-lg bg-amber-50 border border-amber-200 " +
      "text-amber-800 px-4 py-3 text-sm text-center";
    banner.textContent = "Please log in first to access your dashboard.";
    document.querySelector("main").prepend(banner);
    // clean the URL so refresh doesn't re-show it
    history.replaceState({}, "", "/");
}

document.addEventListener("DOMContentLoaded", () => {
  const cta = document.getElementById("home-cta");
  if (!cta) return;

  if (isLoggedIn()) {
    cta.innerHTML = `
      <a href="/create"
         class="inline-block bg-indigo-600 text-white px-6 py-3 rounded-lg font-medium hover:bg-indigo-700 transition">
        Create a short link →
      </a>`;
  } else {
    cta.innerHTML = `
      <a href="/login"
         class="inline-block bg-indigo-600 text-white px-6 py-3 rounded-lg font-medium hover:bg-indigo-700 transition">
        Log in to get started →
      </a>`;
  }
});
