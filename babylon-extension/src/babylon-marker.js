// Runs on holdings.thebabylon.hu itself (unlike content-script.js, which only runs on the game) -
// its only job is to give the Babylon web app a way to detect the extension is installed (see
// apps/web/src/hooks/useExtensionDetected.ts). No page access, no messaging, just a DOM marker.
document.documentElement.setAttribute("data-babylon-extension", "installed");
try {
  document.documentElement.setAttribute("data-babylon-extension-version", chrome.runtime.getManifest().version);
} catch {
  // getManifest() is always available to a content script in practice - fall back quietly if not.
}
