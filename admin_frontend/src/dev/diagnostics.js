(function () {
  const box = document.createElement("div");
  box.style.cssText = "position:fixed;bottom:12px;left:12px;max-width:60vw;padding:8px 10px;background:#111;color:#f66;font:12px/1.4 monospace;z-index:99999;border:1px solid #333;border-radius:8px;white-space:pre-wrap";
  box.textContent = "Diagnostics: waiting…";
  window.addEventListener("DOMContentLoaded", () => document.body.appendChild(box));
  const show = (msg) => (box.textContent = "Error: " + msg);
  window.addEventListener("error", (e) => show(e?.error?.stack || e.message || String(e)));
  window.addEventListener("unhandledrejection", (e) => show(e.reason?.stack || e.reason || String(e)));
})();
