import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Download, X } from "lucide-react";

const DISMISS_KEY = "pwa_install_dismissed_at";
const DISMISS_DAYS = 30;

export const InstallPrompt = () => {
  const [deferredEvt, setDeferredEvt] = useState(null);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const dismissedAt = parseInt(localStorage.getItem(DISMISS_KEY) || "0", 10);
    if (dismissedAt && Date.now() - dismissedAt < DISMISS_DAYS * 24 * 60 * 60 * 1000) {
      return;
    }
    const handler = (e) => {
      e.preventDefault();
      setDeferredEvt(e);
      setVisible(true);
    };
    window.addEventListener("beforeinstallprompt", handler);
    return () => window.removeEventListener("beforeinstallprompt", handler);
  }, []);

  if (!visible || !deferredEvt) return null;

  const install = async () => {
    deferredEvt.prompt();
    await deferredEvt.userChoice;
    setVisible(false);
    setDeferredEvt(null);
  };

  const dismiss = () => {
    localStorage.setItem(DISMISS_KEY, String(Date.now()));
    setVisible(false);
  };

  return (
    <div className="fixed bottom-4 right-4 z-50 w-72 border border-slate-200 bg-white p-3 shadow-lg sm:hidden" data-testid="pwa-install-prompt">
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1">
          <p className="font-heading text-sm font-bold text-slate-900">Install Rajguru Fleet</p>
          <p className="mt-1 text-xs text-slate-500">Add to home screen for quick access.</p>
        </div>
        <button onClick={dismiss} className="p-1 text-slate-400 hover:text-slate-700" data-testid="pwa-install-dismiss">
          <X className="h-4 w-4" />
        </button>
      </div>
      <Button onClick={install} className="mt-3 w-full rounded-none bg-slate-900 text-white hover:bg-slate-800" data-testid="pwa-install-btn">
        <Download className="mr-2 h-4 w-4" /> Install
      </Button>
    </div>
  );
};
