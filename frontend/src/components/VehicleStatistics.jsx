import { useEffect, useState } from "react";
import api from "@/lib/api";
import { fmtINR, fmtNum } from "@/lib/format";
import { Loader2 } from "lucide-react";
import { LineChart, Line, BarChart, Bar, PieChart, Pie, Cell, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Legend } from "recharts";

const PIE_COLORS = ["#0f172a", "#2563eb", "#16a34a", "#dc2626", "#d97706", "#7c3aed", "#0891b2", "#be185d"];

const Stat = ({ label, value, sub }) => (
  <div className="border border-slate-200 bg-white p-4">
    <p className="text-[10px] font-bold uppercase tracking-[0.08em] text-slate-500">{label}</p>
    <p className="mt-1 font-mono text-xl font-bold text-slate-900">{value ?? "—"}</p>
    {sub && <p className="font-mono text-[10px] text-slate-400">{sub}</p>}
  </div>
);

export const VehicleStatistics = ({ vehicleId }) => {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api.get(`/vehicles/${vehicleId}/statistics`)
      .then((r) => setData(r.data))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [vehicleId]);

  if (loading) return <div className="flex h-32 items-center justify-center"><Loader2 className="h-5 w-5 animate-spin text-slate-400" /></div>;
  if (!data) return <p className="text-sm text-slate-500">No statistics available.</p>;
  const L = data.lifetime;

  return (
    <div className="space-y-6" data-testid="vehicle-statistics">
      <div>
        <p className="mb-2 text-xs font-bold uppercase tracking-[0.12em] text-slate-500">Lifetime</p>
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-6">
          <Stat label="Total Trips" value={fmtNum(L.total_trips)} />
          <Stat label="Total KM" value={fmtNum(L.total_km)} />
          <Stat label="Fuel Litres" value={fmtNum(L.total_fuel_litres)} />
          <Stat label="Fuel Cost" value={fmtINR(L.total_fuel_cost)} />
          <Stat label="Avg Mileage" value={L.avg_mileage ? `${L.avg_mileage} KM/L` : "—"} />
          <Stat label="Operating Cost" value={fmtINR(L.total_operating_cost)} />
          <Stat label="Services" value={fmtNum(L.total_services)} />
          <Stat label="Greasings" value={fmtNum(L.total_greasings)} />
          <Stat label="Repairs/Tickets" value={fmtNum(L.total_repairs)} />
          <Stat label="Accidents" value={fmtNum(L.total_accidents)} />
          <Stat label="Downtime Days" value={fmtNum(L.total_downtime_days)} />
          <Stat label="Utilization" value={L.utilization_pct != null ? `${L.utilization_pct}%` : "—"} sub="last 12 months" />
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <div className="border border-slate-200 bg-white p-4" data-testid="stats-mileage-chart">
          <p className="mb-2 text-[10px] font-bold uppercase tracking-[0.1em] text-slate-500">Mileage Trend (KM/L)</p>
          <ResponsiveContainer width="100%" height={220}>
            <LineChart data={data.mileage_trend}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" vertical={false} />
              <XAxis dataKey="label" tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 11 }} />
              <Tooltip />
              <Line type="monotone" dataKey="avg_mileage" stroke="#16a34a" strokeWidth={2} dot={{ r: 3 }} name="KM/L" />
            </LineChart>
          </ResponsiveContainer>
        </div>

        <div className="border border-slate-200 bg-white p-4" data-testid="stats-cost-composition">
          <p className="mb-2 text-[10px] font-bold uppercase tracking-[0.1em] text-slate-500">Cost Composition</p>
          {data.cost_composition.length === 0 ? (
            <p className="py-12 text-center text-sm text-slate-400">No expenses in period.</p>
          ) : (
            <ResponsiveContainer width="100%" height={220}>
              <PieChart>
                <Pie data={data.cost_composition} dataKey="amount" nameKey="category" outerRadius={80} label={(d) => `${d.category} ${d.pct}%`}>
                  {data.cost_composition.map((_, i) => (<Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />))}
                </Pie>
                <Tooltip formatter={(v) => fmtINR(v)} />
              </PieChart>
            </ResponsiveContainer>
          )}
        </div>

        <div className="border border-slate-200 bg-white p-4 xl:col-span-2" data-testid="stats-cost-vs-km">
          <p className="mb-2 text-[10px] font-bold uppercase tracking-[0.1em] text-slate-500">Monthly Cost vs KM Run</p>
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={data.monthly_cost_vs_km}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" vertical={false} />
              <XAxis dataKey="label" tick={{ fontSize: 11 }} />
              <YAxis yAxisId="left" tick={{ fontSize: 11 }} />
              <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 11 }} />
              <Tooltip />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Bar yAxisId="left" dataKey="cost" fill="#0f172a" name="Cost (₹)" />
              <Bar yAxisId="right" dataKey="km" fill="#16a34a" name="KM" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
};

export default VehicleStatistics;
