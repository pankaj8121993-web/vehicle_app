// Resilient dynamic import for React.lazy.
//
// A code-split chunk request can fail transiently — a flaky network, a CDN
// hiccup, or a static host briefly dropping a connection — which otherwise
// surfaces to the user as a hard ChunkLoadError / blank screen. Retry the
// import a few times with a short backoff before giving up, so a momentary
// failure is invisible.
export function lazyWithRetry(importer, retries = 3, delayMs = 350) {
  return () =>
    new Promise((resolve, reject) => {
      const attempt = (remaining) => {
        importer().then(resolve).catch((error) => {
          if (remaining <= 0) {
            reject(error);
            return;
          }
          setTimeout(() => attempt(remaining - 1), delayMs);
        });
      };
      attempt(retries);
    });
}
