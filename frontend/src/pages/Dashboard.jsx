import { useState, useEffect } from "react";
import api from "@/lib/api";
import { fmtINR, fmtNum, fmtDate } from "@/lib/format";
import { Loader2, Truck, Route, Hammer, PauseCircle, ShieldAlert, Fuel, Wrench, IndianRupee, AlertTriangle, TrendingUp } from "lucide-react";
import { ResponsiveContainer, BarChart, Bar, LineChart, Line, XAxis, YAxis, Tooltip, CartesianGrid, Legend } from "recharts";

const fmtMonth = (m) => {
  const [y, mo] = m.split("-");
  return new Date(Number(y), Number(mo) - 1, 1).toLocaleDateString("en-IN", { month: "short" }) + " " + y.slice(2);
};

const Metric = ({ label, value, icon: Icon, tone = "default", testId }) => {
  const tones = {
    default: "border-slate-200 bg-white",
    danger: "border-red-200 bg-red-50",
    warning: "border-amber-200 bg-amber-50",
    success: "border-green-200 bg-green-50",
  };
  return (
    <div className={`border p-5 ${tones[tone]}`} data-testid={testId}>
      <div className="flex items-center justify-between">
        <p className="text-xs font-semibold uppercase tracking-[0.08em] text-slate-500">{label}</p>
        {Icon && <Icon className="h-4 w-4 text-slate-400" strokeWidth={2} />}
      </div>
      <p className="mt-2 font-mono text-2xl font-bold text-slate-900">{value ?? "—"}</p>
    </div>
  );
};

const ListCard = ({ title, items, render, emptyText, testId }) => (
  <div className="border border-slate-200 bg-white" data-testid={testId}>
    <p className="border-b border-slate-200 px-5 py-3 text-xs font-bold uppercase tracking-[0.1em] text-slate-500">{title}</p>
    <div className="divide-y divide-slate-100">
      {items?.length ? items.map((it, i) => <div key={i} className="flex items-center justify-between px-5 py-2.5 text-sm">{render(it)}</div>)
        : <p className="px-5 py-6 text-center text-sm text-slate-400">{emptyText || "No data yet"}</p>}
    </div>
  </div>
);

export default function Dashboard() {
  const [data, setData] = useState(null);
  const [trends, setTrends] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.get("/dashboard")
      .then((res) => setData(res.data))
      .catch(() => {})
      .finally(() => setLoading(false));
    api.get("/dashboard/trends")
      .then((res) => setTrends(res.data.map((t) => ({ ...t, label: fmtMonth(t.month) }))))
      .catch(() => {});
  }, []);

  if (loading) {
    return <div className="flex h-64 items-center justify-center"><Loader2 className="h-6 w-6 animate-spin text-slate-400" /></div>;
  }
  if (!data) return <p className="text-slate-500">Could not load dashboard.</p>;

  const { compliance, operations, fuel, maintenance, financial, alerts } = data;

  return (
    <div className="space-y-8" data-testid="dashboard-page">
      <div>
        <h1 className="font-heading text-3xl font-black tracking-tighter text-slate-900 md:text-4xl">Fleet Dashboard</h1>
        <p className="mt-1 text-sm text-slate-500">Live operational, compliance and financial overview</p>
      </div>

      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <Metric label="Total Vehicles" value={compliance.total_vehicles} icon={Truck} testId="metric-total-vehicles" />
        <Metric label="Running Today" value={operations.running_today} icon={Route} tone="success" testId="metric-running-today" />
        <Metric label="Under Repair" value={operations.under_repair} icon={Hammer} tone={operations.under_repair ? "danger" : "default"} testId="metric-under-repair" />
        <Metric label="Idle Vehicles" value={operations.idle} icon={PauseCircle} testId="metric-idle" />
      </div>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-3">
        <div className="space-y-6 xl:col-span-2">
          <div>
            <h2 className="mb-3 flex items-center gap-2 text-base font-bold uppercase tracking-tight text-slate-800"><ShieldAlert className="h-4 w-4" /> Compliance</h2>
            <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
              <Metric label="Expiring in 30 Days" value={compliance.docs_expiring_30} tone={compliance.docs_expiring_30 ? "warning" : "default"} testId="metric-docs-expiring" />
              <Metric label="Documents Expired" value={compliance.docs_expired} tone={compliance.docs_expired ? "danger" : "default"} testId="metric-docs-expired" />
              <Metric label="Licenses Expiring" value={compliance.licenses_expiring} tone={compliance.licenses_expiring ? "warning" : "default"} testId="metric-licenses-expiring" />
              <Metric label="Active Trips" value={operations.active_trips} testId="metric-active-trips" />
            </div>
          </div>

          <div>
            <h2 className="mb-3 flex items-center gap-2 text-base font-bold uppercase tracking-tight text-slate-800"><Fuel className="h-4 w-4" /> Fuel & Maintenance</h2>
            <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
              <Metric label="Fuel Cost This Month" value={fmtINR(fuel.cost_this_month)} testId="metric-fuel-month" />
              <Metric label="Avg Fleet Mileage" value={fuel.avg_mileage ? `${fuel.avg_mileage} KM/L` : "—"} testId="metric-avg-mileage" />
              <Metric label="Service Due" value={maintenance.service_due} tone={maintenance.service_due ? "warning" : "default"} icon={Wrench} testId="metric-service-due" />
              <Metric label="Service Overdue" value={maintenance.service_overdue} tone={maintenance.service_overdue ? "danger" : "default"} testId="metric-service-overdue" />
            </div>
          </div>

          <div>
            <h2 className="mb-3 flex items-center gap-2 text-base font-bold uppercase tracking-tight text-slate-800"><IndianRupee className="h-4 w-4" /> Financial</h2>
            <div className="grid grid-cols-2 gap-4 md:grid-cols-3">
              <Metric label="Monthly Fleet Cost" value={fmtINR(financial.monthly_cost)} testId="metric-monthly-cost" />
              <Metric label="Cost Per KM" value={financial.cost_per_km ? fmtINR(financial.cost_per_km) : "—"} testId="metric-cost-per-km" />
              <Metric label="KM This Month" value={fmtNum(financial.month_km)} testId="metric-month-km" />
            </div>
          </div>

          {trends.some((t) => t.expense || t.km || t.fuel_cost) && (
            <div>
              <h2 className="mb-3 flex items-center gap-2 text-base font-bold uppercase tracking-tight text-slate-800"><TrendingUp className="h-4 w-4" /> 6-Month Trends</h2>
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
            </div>
          )}

          <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
            <ListCard
              title="Highest Fuel Consumers (Month)"
              items={fuel.top_consumers}
              testId="top-fuel-consumers"
              render={(it) => (<><span className="font-mono font-semibold">{it.vehicle_number || "—"}</span><span className="font-mono">{fmtINR(it.amount)}</span></>)}
            />
            <ListCard
              title="Highest Cost Vehicles (Month)"
              items={financial.top_cost_vehicles}
              testId="top-cost-vehicles"
              render={(it) => (<><span className="font-mono font-semibold">{it.vehicle_number || "—"}</span><span className="font-mono">{fmtINR(it.amount)}</span></>)}
            />
          </div>
        </div>

        <div className="border border-slate-200 bg-white" data-testid="alerts-panel">
          <p className="flex items-center gap-2 border-b border-slate-200 px-5 py-3 text-xs font-bold uppercase tracking-[0.1em] text-slate-500">
            <AlertTriangle className="h-4 w-4 text-amber-600" /> Alerts Panel ({alerts.length})
          </p>
          <div className="max-h-[640px] divide-y divide-slate-100 overflow-y-auto">
            {alerts.length === 0 && <p className="px-5 py-8 text-center text-sm text-slate-400">All clear. No alerts.</p>}
            {alerts.map((a, i) => (
              <div key={i} className={`px-5 py-3 ${a.severity === "danger" ? "border-l-2 border-l-red-600" : "border-l-2 border-l-amber-500"}`} data-testid={`alert-item-${i}`}>
                <p className="text-sm font-medium text-slate-800">{a.message}</p>
                {a.due_date && <p className="mt-0.5 font-mono text-xs text-slate-500">Due: {fmtDate(a.due_date)}</p>}
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
