import { useState, useEffect, useCallback } from "react";
import api from "@/lib/api";
import { fmtINR, fmtNum } from "@/lib/format";
import { Loader2 } from "lucide-react";

export const ExpenseLedger = ({ vehicleId }) => {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.get("/expenses/ledger", { params: vehicleId ? { vehicle_id: vehicleId } : {} });
      setData(res.data);
    } catch { /* handled by empty state */ } finally {
      setLoading(false);
    }
  }, [vehicleId]);

  useEffect(() => { load(); }, [load]);

  if (loading) return <div className="flex h-40 items-center justify-center"><Loader2 className="h-5 w-5 animate-spin text-slate-400" /></div>;
  if (!data) return <p className="text-sm text-slate-400">Could not load ledger.</p>;

  return (
    <div data-testid="expense-ledger">
      <div className="mb-5 flex flex-wrap gap-4">
        <div className="border border-slate-200 bg-white px-5 py-3">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Total Spend</p>
          <p className="font-mono text-xl font-bold text-slate-900" data-testid="ledger-total">{fmtINR(data.total)}</p>
        </div>
        {Object.entries(data.by_category).map(([cat, amt]) => (
          <div key={cat} className="border border-slate-200 bg-white px-5 py-3">
            <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">{cat}</p>
            <p className="font-mono text-base font-bold text-slate-800">{fmtINR(amt)}</p>
          </div>
        ))}
      </div>

      <div className="overflow-x-auto border border-slate-200 bg-white">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-200 bg-slate-50">
              <th className="px-3 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">Date</th>
              {!vehicleId && <th className="px-3 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">Vehicle</th>}
              <th className="px-3 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">Category</th>
              <th className="px-3 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">Description</th>
              <th className="px-3 py-2.5 text-right text-xs font-semibold uppercase tracking-wide text-slate-500">Amount</th>
            </tr>
          </thead>
          <tbody>
            {data.rows.length === 0 ? (
              <tr><td colSpan={5} className="px-3 py-10 text-center text-sm text-slate-400">No expenses recorded yet.</td></tr>
            ) : data.rows.map((r, i) => (
              <tr key={i} className="border-b border-slate-100 hover:bg-slate-50">
                <td className="px-3 py-2.5 font-mono text-xs">{r.date || "—"}</td>
                {!vehicleId && <td className="px-3 py-2.5 font-mono">{r.vehicle_number || "—"}</td>}
                <td className="px-3 py-2.5"><span className="border border-slate-200 bg-slate-50 px-2 py-0.5 text-[11px] font-semibold uppercase">{r.category}</span></td>
                <td className="px-3 py-2.5 text-slate-600">{r.description || "—"}</td>
                <td className="px-3 py-2.5 text-right font-mono">{fmtINR(r.amount)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-2 text-xs text-slate-400">Ledger combines fuel, services, repairs, tyres, accidents, tolls, trip expenses and manual entries. Total entries: {fmtNum(data.rows.length)}</p>
    </div>
  );
};
