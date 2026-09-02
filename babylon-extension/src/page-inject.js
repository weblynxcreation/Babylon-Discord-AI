// Runs in the page's own MAIN world (real window.fetch/XHR, real cookies) so it observes
// exactly the API calls the game itself makes - no need to know how the game authenticates
// or reverse-engineer its session/claim tokens.
(function () {
  // /api/game/:id is watched purely as a trigger to keep the session cookie relay fresh (see
  // background.js) - its response data is never relayed anywhere. The member roster
  // (/api/company/:id/members) isn't watched at all anymore - Babylon polls that itself now.
  const WATCHED_PATTERNS = [/\/api\/me(\?|$)/, /\/api\/company\/mine(\?|$)/, /\/api\/game\/[0-9a-f-]+/];

  function isWatched(url) {
    return WATCHED_PATTERNS.some((re) => re.test(url));
  }

  function relay(url, data) {
    window.postMessage({ source: "babylon-extension-page", url, data }, window.location.origin);
  }

  const originalFetch = window.fetch;
  window.fetch = async function patchedFetch(...args) {
    const response = await originalFetch.apply(this, args);
    try {
      const url = typeof args[0] === "string" ? args[0] : args[0]?.url ?? "";
      if (isWatched(url)) {
        response
          .clone()
          .json()
          .then((data) => relay(url, data))
          .catch(() => {});
      }
    } catch {
      // never let observation break the game itself
    }
    return response;
  };

  const OriginalXHR = window.XMLHttpRequest;
  function PatchedXHR() {
    const xhr = new OriginalXHR();
    let requestUrl = "";
    const originalOpen = xhr.open;
    xhr.open = function (method, url, ...rest) {
      requestUrl = url;
      return originalOpen.call(xhr, method, url, ...rest);
    };
    xhr.addEventListener("load", () => {
      try {
        if (isWatched(requestUrl) && (xhr.responseType === "" || xhr.responseType === "text")) {
          relay(requestUrl, JSON.parse(xhr.responseText));
        }
      } catch {
        // ignore non-JSON or unrelated responses
      }
    });
    return xhr;
  }
  window.XMLHttpRequest = PatchedXHR;
})();
