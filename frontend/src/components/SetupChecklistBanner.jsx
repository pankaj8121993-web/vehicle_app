import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { roleTier } from "@/lib/format";
import { CheckCircle2, X, ArrowRight } from "lucide-react";

export const SetupChecklistBanner = () => {
  const { user } = useAuth();
  const [data, setData] = useState(null);
  const [hidden, setHidden] = useState(false);
  const isManager = ["admin", "management"].includes(roleTier(user?.role));

  useEffect(() => {
    if (!isManager || user?.is_demo) return;
    api.get("/onboarding/checklist").then((r) => setData(r.data)).catch(() => {});
  }, [isManager, user?.is_demo]);

  // While the checklist is loading for a manager, reserve the banner's height
  // so it does not shift the dashboard metrics down when it appears (UX-05 CLS).
  if (isManager && !user?.is_demo && !hidden && !data) {
    return <div className="min-h-[128px] md:min-h-[88px]" aria-hidden="true" />;
  }
  if (!isManager || user?.is_demo || hidden || !data || data.dismissed || data.completed >= data.total) return null;

  const dismiss = async () => {
    setHidden(true);
    try { await api.post("/onboarding/checklist/dismiss"); } catch { /* ignore */ }
  };

  return (
    <div className="flex min-h-[128px] md:min-h-[88px] flex-wrap items-center gap-4 border border-amber-300 bg-amber-50 px-5 py-3.5" data-testid="dashboard-setup-banner">
      <CheckCircle2 className="h-5 w-5 text-amber-600" />
      <div className="min-w-0 flex-1">
        <p className="text-sm font-bold text-slate-900">Finish setting up your workspace — {data.completed}/{data.total} done</p>
        <div className="mt-1.5 h-1.5 max-w-xs bg-amber-200">
          <div className="h-1.5 bg-amber-500 transition-all" style={{ width: `${(data.completed / data.total) * 100}%` }} />
        </div>
      </div>
      <Link to="/settings/organisation" data-testid="setup-banner-link"
        className="flex items-center gap-1.5 bg-slate-900 px-4 py-2 text-xs font-bold uppercase tracking-wide text-white hover:bg-slate-800">
        Continue setup <ArrowRight className="h-3.5 w-3.5" />
      </Link>
      <button onClick={dismiss} data-testid="setup-banner-dismiss" className="text-slate-400 hover:text-slate-700" aria-label="Dismiss">
        <X className="h-4 w-4" />
      </button>
    </div>
  );
};
