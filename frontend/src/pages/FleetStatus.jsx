import { useState, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import api from "@/lib/api";
import { fmtNum, fmtDate } from "@/lib/format";
import { Loader2, RefreshCw, Route, PauseCircle, Wrench, Clock, Archive } from "lucide-react";
import { Button } from "@/components/ui/button";

const STATUS_META = {
  RUNNING: { label: "Running", color: "border-green-200 bg-green-50 text-green-800", icon: Route },
  IDLE: { label: "Idle", color: "border-slate-200 bg-slate-50 text-slate-700", icon: PauseCircle },
  UNDER_REPAIR: { label: "Under Repair", color: "border-red-200 bg-red-50 text-red-800", icon: Wrench },
  DOWNTIME: { label: "Downtime", color: "border-amber-200 bg-amber-50 text-amber-800", icon: Clock },
  DISPOSED: { label: "Disposed", color: "border-slate-300 bg-slate-100 text-slate-500", icon: Archive },
};
const ORDER = ["RUNNING", "IDLE", "UNDER_REPAIR", "DOWNTIME", "DISPOSED"];

const Card = ({ row, onClick }) => {
  const M = STATUS_META[row.status];
  return (
    <button
      onClick={onClick}
      data-testid={`fleet-status-card-${row.vehicle_number}`}
      className={`flex w-full items-start gap-3 border ${M.color} p-3 text-left transition-all hover:-translate-y-0.5 hover:shadow-md`}
    >
      <M.icon className="mt-0.5 h-4 w-4 flex-shrink-0" strokeWidth={2} />
      <div className="min-w-0 flex-1">
        <p className="truncate font-mono text-sm font-bold tracking-wide">{row.vehicle_number}</p>
        <p className="font-mono text-[10px] uppercase tracking-wide opacity-70">{row.vtype || "—"}</p>
        {row.status === "RUNNING" && row.detail?.driver_name && (
          <p className="mt-1 truncate text-xs">→ {row.detail.driver_name}</p>
        )}
        {row.status === "RUNNING" && row.detail?.destination && (
          <p className="truncate text-xs opacity-80">to {row.detail.destination}</p>
        )}
        {row.status === "UNDER_REPAIR" && row.detail?.ticket_number && (
          <p className="mt-1 truncate font-mono text-[10px]">#{row.detail.ticket_number}</p>
        )}
        {row.status === "DOWNTIME" && row.detail?.reason && (
          <p className="mt-1 truncate text-xs capitalize">{row.detail.reason}{row.detail.days_since ? ` · ${row.detail.days_since}d` : ""}</p>
        )}
        {row.status === "DISPOSED" && row.detail?.disposal_date && (
          <p className="mt-1 font-mono text-[10px]">{fmtDate(row.detail.disposal_date)}</p>
        )}
      </div>
    </button>
  );
};

export default function FleetStatus() {
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    try {
      const r = await api.get("/fleet-status");
      setData(r.data);
    } catch {
      // A route change or logout may cancel/reject an in-flight refresh.
      // The page already has an explicit no-data state; do not leak an
      // unhandled promise rejection into the browser.
      setData((current) => current);
    } finally { setLoading(false); setRefreshing(false); }
  }, []);

  useEffect(() => {
    load();
    const id = setInterval(() => { setRefreshing(true); load(); }, 60000);
    return () => clearInterval(id);
  }, [load]);

  if (loading) return <div className="flex h-64 items-center justify-center"><Loader2 className="h-6 w-6 animate-spin text-slate-400" /></div>;
  if (!data) return <p>Could not load fleet status.</p>;

  return (
    <div data-testid="fleet-status-page">
      <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="font-heading text-3xl font-black tracking-tighter text-slate-900 md:text-4xl">Fleet Status Board</h1>
          <p className="mt-1 text-sm text-slate-500">Live view across {data.total} vehicles · auto-refresh every 60s · as of <span className="font-mono">{new Date(data.as_of).toLocaleTimeString()}</span></p>
        </div>
        <Button variant="outline" onClick={() => { setRefreshing(true); load(); }} className="rounded-none" disabled={refreshing} data-testid="fleet-status-refresh">
          <RefreshCw className={`mr-1 h-4 w-4 ${refreshing ? "animate-spin" : ""}`} /> Refresh
        </Button>
      </div>

      <div className="mb-6 grid grid-cols-2 gap-3 md:grid-cols-5">
        {ORDER.map((s) => {
          const M = STATUS_META[s];
          const n = data.counts[s] || 0;
          return (
            <div key={s} className={`border p-4 ${M.color}`} data-testid={`fleet-status-count-${s.toLowerCase()}`}>
              <div className="flex items-center justify-between">
                <p className="text-xs font-bold uppercase tracking-[0.08em]">{M.label}</p>
                <M.icon className="h-4 w-4" strokeWidth={2} />
              </div>
              <p className="mt-1 font-mono text-3xl font-bold">{n}</p>
            </div>
          );
        })}
      </div>

      <div className="space-y-6">
        {ORDER.map((s) => {
          const rows = data.rows.filter((r) => r.status === s);
          if (rows.length === 0) return null;
          const M = STATUS_META[s];
          return (
            <div key={s} data-testid={`fleet-status-section-${s.toLowerCase()}`}>
              <p className="mb-2 flex items-center gap-2 text-xs font-bold uppercase tracking-[0.12em] text-slate-600">
                <M.icon className="h-3.5 w-3.5" /> {M.label} <span className="font-mono text-slate-400">· {rows.length}</span>
              </p>
              <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
                {rows.map((r) => (
                  <Card key={r.vehicle_id} row={r} onClick={() => navigate(`/vehicles/${r.vehicle_id}`)} />
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
