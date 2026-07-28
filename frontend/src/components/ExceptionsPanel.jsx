import { useEffect, useState } from "react";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import { AlertTriangle } from "lucide-react";

// OPS-05: operational exceptions, derived live from canonical data. Read-only
// aggregation plus acknowledge; no parallel financial calculation here.
const CATEGORY_LABEL = {
  trips_awaiting_dispatch: "Trips awaiting dispatch",
  trips_overdue_completion: "Trips overdue for completion",
  trips_awaiting_settlement: "Trips awaiting settlement",
  missing_closing_odometer: "Missing closing odometer",
  unapproved_expenses: "Unapproved expenses",
  unpaid_approved_expenses: "Unpaid approved expenses",
  repairs_awaiting_approval: "Repairs awaiting approval",
  repairs_overdue_completion: "Repairs overdue for completion",
  open_downtime: "Open downtime",
  vehicles_under_repair: "Vehicles under maintenance",
  documents_expiring_soon: "Documents expiring soon",
  expired_documents: "Expired documents",
  licences_expiring: "Licences expiring",
  open_accident_claims: "Open accident claims",
  claims_awaiting_settlement: "Claims awaiting settlement",
};

const sevCls = (s) =>
  s === "danger" ? "text-red-700" : s === "warning" ? "text-amber-700" : "text-slate-600";

export function ExceptionsPanel() {
  const [feed, setFeed] = useState(null);
  const load = () => api.get("/exceptions").then((r) => setFeed(r.data)).catch(() => setFeed({ items: [], total: 0, by_category: {} }));
  useEffect(() => { load(); }, []);

  const ack = async (id) => {
    try {
      await api.post(`/exceptions/${encodeURIComponent(id)}/acknowledge`, {});
      toast.success("Acknowledged");
      load();
    } catch {
      toast.error("Failed to acknowledge");
    }
  };

  if (!feed) return null;
  if (!feed.items.length) {
    return (
      <div className="border border-slate-200 bg-white p-4" data-testid="exceptions-panel">
        <div className="flex items-center gap-2 text-sm font-semibold text-slate-700">
          <AlertTriangle className="h-4 w-4 text-emerald-600" /> Operational Exceptions
        </div>
        <p className="mt-2 text-sm text-slate-500">No operational exceptions — everything is up to date.</p>
      </div>
    );
  }
  return (
    <div className="border border-slate-200 bg-white" data-testid="exceptions-panel">
      <div className="flex items-center justify-between border-b border-slate-100 p-4">
        <div className="flex items-center gap-2 text-sm font-semibold text-slate-700">
          <AlertTriangle className="h-4 w-4 text-amber-600" /> Operational Exceptions
          <span className="ml-1 rounded-none bg-slate-900 px-2 py-0.5 text-xs text-white">{feed.total}</span>
        </div>
        <span className="text-xs text-slate-500">{feed.unacknowledged} unacknowledged</span>
      </div>
      <div className="max-h-96 divide-y divide-slate-100 overflow-y-auto">
        {feed.items.map((it) => (
          <div key={it.id} className="flex items-center justify-between px-4 py-2 text-sm" data-testid={`exception-${it.id}`}>
            <div>
              <span className={`font-medium ${sevCls(it.severity)}`}>{it.label}</span>
              <span className="ml-2 text-xs text-slate-400">{CATEGORY_LABEL[it.category] || it.category}</span>
            </div>
            {it.acknowledged
              ? <span className="text-xs text-slate-400">Acknowledged</span>
              : <Button data-testid={`ack-${it.id}`} variant="outline" size="sm" className="h-6 rounded-none px-2 text-xs" onClick={() => ack(it.id)}>Acknowledge</Button>}
          </div>
        ))}
      </div>
    </div>
  );
}
