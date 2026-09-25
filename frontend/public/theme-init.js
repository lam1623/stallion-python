// Apply the saved theme before first paint (external file to satisfy the CSP)
(function () {
  try {
    var saved = localStorage.getItem("stallion-theme") || "system";
    var dark = saved === "dark" || (saved === "system" && window.matchMedia("(prefers-color-scheme: dark)").matches);
    document.documentElement.classList.toggle("dark", dark);
  } catch (e) {
    document.documentElement.classList.add("dark");
  }
})();
