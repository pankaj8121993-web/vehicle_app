import { useState, useEffect } from "react";
import api from "@/lib/api";
import { fmtINR, fmtNum } from "@/lib/format";
import { Loader2, TrendingUp, TrendingDown } from "lucide-react";
import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid } from "recharts";

const Card = ({ label, value, sub, accent, testId }) => (
  <div className="border border-slate-200 bg-white px-5 py-4" data-testid={testId}>
    <p className="text-[11px] font-bold uppercase tracking-wide text-slate-500">{label}</p>
    <p className={`mt-1 font-mono text-xl font-bold ${accent || "text-slate-900"}`}>{value}</p>
    {sub && <p className="mt-0.5 text-[11px] text-slate-400">{sub}</p>}
  </div>
);

export const ExpenseOverview = ({ startDate, endDate }) => {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    const params = {};
    if (startDate) params.start_date = startDate;
    if (endDate) params.end_date = endDate;
    api.get("/expenses/overview", { params })
      .then((r) => setData(r.data))
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, [startDate, endDate]);

  if (loading) return <div className="flex h-48 items-center justify-center"><Loader2 className="h-5 w-5 animate-spin text-slate-400" /></div>;
  if (!data) return <p className="text-sm text-slate-400">Could not load expense overview.</p>;

  const mom = data.mom_change_pct;
  const catTotal = data.by_category.reduce((s, c) => s + c.amount, 0) || 1;

  return (
    <div data-testid="expense-overview" className="space-y-6">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-7">
        <Card label="Total Spend" value={fmtINR(data.total)} sub={`${data.count} entries`} testId="ov-total" />
        <Card label="This Month" value={fmtINR(data.current_month)} testId="ov-current-month" />
        <Card label="Last Month" value={fmtINR(data.previous_month)} testId="ov-prev-month" />
        <Card label="MoM Change" testId="ov-mom"
          value={mom === null ? "—" : `${mom > 0 ? "+" : ""}${mom}%`}
          accent={mom === null ? undefined : mom > 0 ? "text-red-600" : "text-green-600"}
          sub={mom === null ? "No prior data" : mom > 0 ? "Higher than last month" : "Lower than last month"} />
        <Card label="Cost / KM" value={data.cost_per_km !== null ? fmtINR(data.cost_per_km) : "—"} sub={`${fmtNum(data.total_km)} km in period`} testId="ov-cpk" />
        <Card label="Cost / Vehicle" value={data.cost_per_vehicle !== null ? fmtINR(data.cost_per_vehicle) : "—"} testId="ov-cpv" />
        <Card label="Cost / Trip" value={data.cost_per_trip !== null ? fmtINR(data.cost_per_trip) : "—"} testId="ov-cpt" />
      </div>

      <div className="grid gap-5 lg:grid-cols-2">
        <div className="border border-slate-200 bg-white p-5">
          <p className="mb-4 text-xs font-bold uppercase tracking-[0.12em] text-slate-500">Category-wise spend</p>
          {data.by_category.length === 0 ? (
            <p className="py-8 text-center text-sm text-slate-400">No expenses recorded in this period.</p>
          ) : (
            <div className="space-y-3">
              {data.by_category.map((c) => (
                <div key={c.category}>
                  <div className="mb-1 flex justify-between text-sm">
                    <span className="font-semibold text-slate-700">{c.category}</span>
                    <span className="font-mono text-slate-900">{fmtINR(c.amount)}</span>
                  </div>
                  <div className="h-1.5 bg-slate-100">
                    <div className="h-1.5 bg-slate-900 transition-all" style={{ width: `${Math.max((c.amount / catTotal) * 100, 1.5)}%` }} />
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="border border-slate-200 bg-white p-5">
          <p className="mb-4 text-xs font-bold uppercase tracking-[0.12em] text-slate-500">12-month trend</p>
          {data.monthly_trend.length === 0 ? (
            <p className="py-8 text-center text-sm text-slate-400">Not enough history for a trend yet.</p>
          ) : (
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={data.monthly_trend} margin={{ top: 5, right: 5, bottom: 5, left: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" vertical={false} />
                <XAxis dataKey="month" tick={{ fontSize: 10 }} tickFormatter={(m) => m.slice(5)} />
                <YAxis tick={{ fontSize: 10 }} tickFormatter={(v) => `${Math.round(v / 1000)}k`} width={36} />
                <Tooltip formatter={(v) => fmtINR(v)} labelStyle={{ fontWeight: 700 }} />
                <Bar dataKey="amount" fill="#0f172a" />
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>

      <div className="border border-slate-200 bg-white">
        <p className="border-b border-slate-200 px-5 py-3 text-xs font-bold uppercase tracking-[0.12em] text-slate-500">Vehicle cost ranking</p>
        {data.by_vehicle.length === 0 ? (
          <p className="py-8 text-center text-sm text-slate-400">No vehicle-linked expenses in this period.</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-200 bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
                <th className="px-5 py-2.5">#</th><th className="px-5 py-2.5">Vehicle</th><th className="px-5 py-2.5 text-right">Total Spend</th>
              </tr>
            </thead>
            <tbody>
              {data.by_vehicle.map((v, i) => (
                <tr key={v.vehicle_id} className="border-b border-slate-100 last:border-0 hover:bg-slate-50">
                  <td className="px-5 py-2.5 font-mono text-slate-400">{i + 1}</td>
                  <td className="px-5 py-2.5 font-semibold text-slate-900">{v.vehicle_number}</td>
                  <td className="px-5 py-2.5 text-right font-mono">{fmtINR(v.amount)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
};

const SEVERITY_STYLES = {
  critical: "border-red-300 bg-red-50 text-red-800",
  warning: "border-amber-300 bg-amber-50 text-amber-800",
  info: "border-slate-200 bg-white text-slate-700",
};

export const ExpenseInsights = () => {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.get("/expenses/insights")
      .then((r) => setData(r.data))
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="flex h-40 items-center justify-center"><Loader2 className="h-5 w-5 animate-spin text-slate-400" /></div>;
  if (!data) return <p className="text-sm text-slate-400">Could not load insights.</p>;

  return (
    <div className="space-y-3" data-testid="expense-insights">
      {data.insights.map((ins, i) => (
        <div key={i} className={`flex items-start gap-3 border-l-4 border p-4 ${SEVERITY_STYLES[ins.severity] || SEVERITY_STYLES.info}`} data-testid={`insight-${ins.type}`}>
          {ins.severity === "critical" || ins.severity === "warning"
            ? <TrendingUp className="mt-0.5 h-4 w-4 flex-shrink-0" />
            : <TrendingDown className="mt-0.5 h-4 w-4 flex-shrink-0" />}
          <div>
            <p className="text-sm font-bold">{ins.title}</p>
            <p className="mt-0.5 text-sm opacity-80">{ins.detail}</p>
          </div>
        </div>
      ))}
      <p className="pt-2 text-[11px] text-slate-400">Insights are computed from your organisation's actual recorded data — nothing is estimated or fabricated.</p>
    </div>
  );
};
