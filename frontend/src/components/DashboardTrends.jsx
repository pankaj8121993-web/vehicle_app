import { ResponsiveContainer, BarChart, Bar, LineChart, Line, XAxis, YAxis, Tooltip, CartesianGrid, Legend } from "recharts";
import { fmtINR, fmtNum } from "@/lib/format";

// Recharts is heavy (~360 KB gzip chunk). Keeping it in this separately
// lazy-loaded component keeps it off the dashboard's critical render path, so
// the text metrics (the LCP content) paint first and recharts streams in below
// them. The parent reserves this block's height to avoid layout shift.
export default function DashboardTrends({ trends }) {
  return (
    <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
      <div className="border border-slate-200 bg-white p-4" data-testid="trend-cost-chart">
        <p className="mb-3 text-xs font-bold uppercase tracking-[0.1em] text-slate-500">Monthly Cost (₹)</p>
        <ResponsiveContainer width="100%" height={220}>
          <BarChart data={trends}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" vertical={false} />
            <XAxis dataKey="label" tick={{ fontSize: 11 }} />
            <YAxis tick={{ fontSize: 11 }} />
            <Tooltip formatter={(v) => fmtINR(v)} />
            <Legend wrapperStyle={{ fontSize: 12 }} />
            <Bar dataKey="expense" name="Total Cost" fill="#0f172a" />
            <Bar dataKey="fuel_cost" name="Fuel Cost" fill="#2563eb" />
          </BarChart>
        </ResponsiveContainer>
      </div>
      <div className="border border-slate-200 bg-white p-4" data-testid="trend-km-chart">
        <p className="mb-3 text-xs font-bold uppercase tracking-[0.1em] text-slate-500">KM Run Per Month</p>
        <ResponsiveContainer width="100%" height={220}>
          <LineChart data={trends}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" vertical={false} />
            <XAxis dataKey="label" tick={{ fontSize: 11 }} />
            <YAxis tick={{ fontSize: 11 }} />
            <Tooltip formatter={(v) => `${fmtNum(v)} KM`} />
            <Line type="monotone" dataKey="km" name="KM Run" stroke="#16a34a" strokeWidth={2} dot={{ r: 3 }} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
