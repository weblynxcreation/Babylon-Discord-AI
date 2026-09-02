// Isolated world - has chrome.runtime access but not the page's real fetch/XHR. Injects
// page-inject.js into the page itself via a classic <script src> tag rather than the MV3
// declarative "world": "MAIN" content script key, since that key only works on Firefox 128+ -
// this approach works identically on any browser's extension implementation.
(function injectPageScript() {
  const script = document.createElement("script");
  script.src = chrome.runtime.getURL("src/page-inject.js");
  script.onload = () => script.remove();
  (document.head || document.documentElement).appendChild(script);
})();

window.addEventListener("message", (event) => {
  if (event.source !== window) return;
  if (event.origin !== window.location.origin) return;
  const msg = event.data;
  if (!msg || msg.source !== "babylon-extension-page") return;

  chrome.runtime.sendMessage({ type: "GAME_API_OBSERVED", url: msg.url, data: msg.data }).catch(() => {});
});
