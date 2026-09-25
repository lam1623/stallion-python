// Apply the saved theme before first paint (external file to satisfy the CSP); light is the default
(function () {
  try {
    var saved = localStorage.getItem("stallion-theme") || "light";
    var dark = saved === "dark" || (saved === "system" && window.matchMedia("(prefers-color-scheme: dark)").matches);
    document.documentElement.classList.toggle("dark", dark);
  } catch (e) {
    // storage may be unavailable: keep the light default
  }
})();
