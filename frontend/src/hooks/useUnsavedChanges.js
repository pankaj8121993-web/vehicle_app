import { useEffect } from "react";

export const UNSAVED_MESSAGE = "You have unsaved changes. Leave without saving them?";

export function useUnsavedChanges(enabled) {
  useEffect(() => {
    if (!enabled) return undefined;
    const beforeUnload = (event) => {
      event.preventDefault();
      event.returnValue = "";
    };
    const interceptLinks = (event) => {
      const link = event.target.closest?.("a[href]");
      if (link && !window.confirm(UNSAVED_MESSAGE)) {
        event.preventDefault();
        event.stopPropagation();
      }
    };
    window.addEventListener("beforeunload", beforeUnload);
    document.addEventListener("click", interceptLinks, true);
    return () => {
      window.removeEventListener("beforeunload", beforeUnload);
      document.removeEventListener("click", interceptLinks, true);
    };
  }, [enabled]);
}
