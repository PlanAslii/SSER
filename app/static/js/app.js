/* PlanAsli SSH Manager — client utilities */
(function () {
  "use strict";

  // Sidebar toggle (mobile)
  var toggle = document.getElementById("sidebarToggle");
  var sidebar = document.getElementById("sidebar");
  if (toggle && sidebar) {
    toggle.addEventListener("click", function () {
      sidebar.classList.toggle("open");
    });
    document.addEventListener("click", function (e) {
      if (
        sidebar.classList.contains("open") &&
        !sidebar.contains(e.target) &&
        !toggle.contains(e.target)
      ) {
        sidebar.classList.remove("open");
      }
    });
  }

  // Theme toggle
  var themeBtn = document.getElementById("themeToggle");
  if (themeBtn) {
    themeBtn.addEventListener("click", function () {
      var html = document.documentElement;
      var current = html.getAttribute("data-theme") || "light";
      var next = current === "dark" ? "light" : "dark";
      html.setAttribute("data-theme", next);
      localStorage.setItem("planasli-theme", next);
    });
  }

  // System theme listener
  if (window.matchMedia) {
    window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", function (e) {
      if (localStorage.getItem("planasli-theme") === "system") {
        document.documentElement.setAttribute("data-theme", e.matches ? "dark" : "light");
      }
    });
  }
})();
