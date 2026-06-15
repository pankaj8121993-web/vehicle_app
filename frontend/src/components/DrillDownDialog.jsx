import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import api from "@/lib/api";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Loader2 } from "lucide-react";
import { fmtINR, fmtNum, fmtDate } from "@/lib/format";

const renderCell = (col, row) => {
  const v = row[col.key];
  if (v === null || v === undefined || v === "") return <span className="text-slate-400">—</span>;
  if (col.type === "currency") return <span className="font-mono">{fmtINR(v)}</span>;
  if (col.type === "number") return <span className="font-mono">{fmtNum(v)}</span>;
  if (col.type === "date") return <span className="font-mono">{fmtDate(v)}</span>;
  return String(v);
};

/**
 * DrillDownDialog — generic table modal for dashboard widget drill-down.
 * Props:
 *   open, onClose
 *   title         — modal heading
 *   endpoint      — path under /drilldowns (e.g. "docs_expiring")
 *   params        — query params object
 *   columns       — [{ key, label, type? }]
 *   rowLink(row)  — optional fn returning a route to navigate (e.g. /vehicles/:id)
 *   emptyText
 */
export const DrillDownDialog = ({ open, onClose, title, endpoint, params, columns, rowLink, emptyText }) => {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    if (!open || !endpoint) return;
    setLoading(true);
    api.get(`/drilldowns/${endpoint}`, { params: params || {} })
      .then((r) => setRows(r.data || []))
      .catch(() => setRows([]))
      .finally(() => setLoading(false));
  }, [open, endpoint, JSON.stringify(params || {})]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-h-[85vh] max-w-4xl overflow-hidden rounded-none p-0" data-testid="drilldown-dialog">
        <DialogHeader className="border-b border-slate-200 px-6 py-4">
          <DialogTitle className="font-heading text-xl font-black tracking-tighter text-slate-900">{title}</DialogTitle>
          <p className="text-xs text-slate-500" data-testid="drilldown-count">{loading ? "Loading…" : `${rows.length} record${rows.length === 1 ? "" : "s"}`}</p>
        </DialogHeader>
        <div className="max-h-[65vh] overflow-auto">
          {loading ? (
            <div className="flex h-40 items-center justify-center"><Loader2 className="h-5 w-5 animate-spin text-slate-400" /></div>
          ) : rows.length === 0 ? (
            <p className="px-6 py-12 text-center text-sm text-slate-400" data-testid="drilldown-empty">{emptyText || "Nothing to show here."}</p>
          ) : (
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-slate-50">
                <tr className="border-b border-slate-200">
                  {columns.map((c) => (
                    <th key={c.key} className={`px-4 py-2.5 text-xs font-semibold uppercase tracking-wide text-slate-500 ${["currency", "number"].includes(c.type) ? "text-right" : "text-left"}`}>{c.label}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((row, i) => (
                  <tr
                    key={i}
                    data-testid={`drilldown-row-${i}`}
                    className={`border-b border-slate-100 hover:bg-slate-50 ${rowLink ? "cursor-pointer" : ""}`}
                    onClick={rowLink ? () => { const to = rowLink(row); if (to) { onClose(); navigate(to); } } : undefined}
                  >
                    {columns.map((c) => (
                      <td key={c.key} className={`px-4 py-2.5 ${["currency", "number"].includes(c.type) ? "text-right" : ""}`}>
                        {renderCell(c, row)}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
};

export default DrillDownDialog;
