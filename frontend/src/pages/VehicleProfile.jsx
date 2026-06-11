import { useState, useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import api from "@/lib/api";
import { fmtINR, fmtNum, fmtDate } from "@/lib/format";
import { StatusBadge, ExpiryBadge } from "@/components/StatusBadge";
import { CrudModule } from "@/components/CrudModule";
import { ExpenseLedger } from "@/components/ExpenseLedger";
import { CloseTripAction, RepairWorkflowAction } from "@/pages/ModulePages";
import {
  documentConfig, tripConfig, fuelConfig, serviceConfig, repairConfig,
  tyreConfig, tyreEventConfig, accidentConfig, downtimeConfig, fastagConfig,
} from "@/lib/configs";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Loader2, ArrowLeft } from "lucide-react";

const Stat = ({ label, children, testId }) => (
  <div className="border border-slate-200 bg-white p-4" data-testid={testId}>
    <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-slate-500">{label}</p>
    <div className="mt-1.5 font-mono text-lg font-bold text-slate-900">{children}</div>
  </div>
);

const TABS = [
  { value: "documents", label: "Documents" },
  { value: "trips", label: "Trips" },
  { value: "fuel", label: "Fuel" },
  { value: "services", label: "Service" },
  { value: "repairs", label: "Repairs" },
  { value: "tyres", label: "Tyres" },
  { value: "accidents", label: "Accidents" },
  { value: "fastag", label: "Fastag" },
  { value: "expenses", label: "Expenses" },
  { value: "downtime", label: "Downtime" },
];

export default function VehicleProfile() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api.get(`/vehicles/${id}/summary`)
      .then((res) => setSummary(res.data))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [id]);

  if (loading) return <div className="flex h-64 items-center justify-center"><Loader2 className="h-6 w-6 animate-spin text-slate-400" /></div>;
  if (!summary) return <p className="text-slate-500">Vehicle not found.</p>;

  const v = summary.vehicle;
  const exp = summary.document_expiries || {};
  const ff = { vehicle_id: id };

  return (
    <div data-testid="vehicle-profile-page">
      <Button variant="ghost" size="sm" onClick={() => navigate("/vehicles")} className="mb-4 -ml-2 text-slate-500 hover:text-slate-900" data-testid="back-to-vehicles">
        <ArrowLeft className="mr-1 h-4 w-4" /> All Vehicles
      </Button>

      <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="font-heading text-3xl font-black tracking-tighter text-slate-900 md:text-4xl" data-testid="vehicle-number-heading">{v.vehicle_number}</h1>
            <StatusBadge value={v.status} />
          </div>
          <p className="mt-1 text-sm text-slate-500">
            {[v.make, v.model, v.vtype, v.fuel_type].filter(Boolean).join(" · ") || "No details"}
            {v.chassis_number && <span className="ml-3 font-mono text-xs">CH: {v.chassis_number}</span>}
            {v.engine_number && <span className="ml-2 font-mono text-xs">EN: {v.engine_number}</span>}
          </p>
        </div>
        <div className="text-right text-sm text-slate-500">
          {v.purchase_date && <p>Purchased: {fmtDate(v.purchase_date)}{v.purchase_price ? ` · ${fmtINR(v.purchase_price)}` : ""}</p>}
          <p className="font-mono font-semibold text-slate-800">Odometer: {fmtNum(v.current_odometer)} KM</p>
        </div>
      </div>

      <div className="mb-8 grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-6">
        <Stat label="Insurance Expiry" testId="stat-insurance"><ExpiryBadge date={exp["Insurance"]} /></Stat>
        <Stat label="Fitness Expiry" testId="stat-fitness"><ExpiryBadge date={exp["Fitness"]} /></Stat>
        <Stat label="Permit Expiry" testId="stat-permit"><ExpiryBadge date={exp["Permit"]} /></Stat>
        <Stat label="Next Service" testId="stat-next-service">
          {summary.next_service_due_date ? <ExpiryBadge date={summary.next_service_due_date} /> : summary.next_service_due_km ? `${fmtNum(summary.next_service_due_km)} KM` : "—"}
        </Stat>
        <Stat label="Fastag Balance" testId="stat-fastag">{fmtINR(v.fastag_balance)}</Stat>
        <Stat label="Total KM Run" testId="stat-total-km">{fmtNum(summary.total_km)}</Stat>
        <Stat label="Total Trips" testId="stat-total-trips">{fmtNum(summary.total_trips)}</Stat>
        <Stat label="Avg Mileage" testId="stat-avg-mileage">{summary.avg_mileage ? `${summary.avg_mileage} KM/L` : "—"}</Stat>
        <Stat label="Fuel Cost" testId="stat-fuel-cost">{fmtINR(summary.total_fuel_cost)}</Stat>
        <Stat label="Operating Cost" testId="stat-operating-cost">{fmtINR(summary.total_operating_cost)}</Stat>
        <Stat label="Cost / KM" testId="stat-cost-per-km">{summary.cost_per_km ? fmtINR(summary.cost_per_km) : "—"}</Stat>
        <Stat label="Downtime Days" testId="stat-downtime">{fmtNum(summary.downtime_days)}</Stat>
      </div>

      <Tabs defaultValue="documents">
        <TabsList className="h-auto w-full justify-start overflow-x-auto rounded-none border border-slate-200 bg-white p-0">
          {TABS.map((t) => (
            <TabsTrigger
              key={t.value}
              value={t.value}
              data-testid={`vehicle-tab-${t.value}`}
              className="rounded-none border-b-2 border-transparent px-4 py-3 text-sm font-semibold data-[state=active]:border-slate-900 data-[state=active]:bg-white data-[state=active]:text-slate-900"
            >
              {t.label}
            </TabsTrigger>
          ))}
        </TabsList>

        <div className="mt-5">
          <TabsContent value="documents"><CrudModule {...documentConfig} fixedFilters={ff} testIdPrefix="vp-documents" /></TabsContent>
          <TabsContent value="trips"><CrudModule {...tripConfig} fixedFilters={ff} rowActions={CloseTripAction} testIdPrefix="vp-trips" /></TabsContent>
          <TabsContent value="fuel"><CrudModule {...fuelConfig} fixedFilters={ff} testIdPrefix="vp-fuel" /></TabsContent>
          <TabsContent value="services"><CrudModule {...serviceConfig} fixedFilters={ff} testIdPrefix="vp-services" /></TabsContent>
          <TabsContent value="repairs"><CrudModule {...repairConfig} fixedFilters={ff} rowActions={RepairWorkflowAction} testIdPrefix="vp-repairs" /></TabsContent>
          <TabsContent value="tyres">
            <CrudModule {...tyreConfig} fixedFilters={ff} testIdPrefix="vp-tyres" />
            <h3 className="mb-3 mt-8 text-base font-bold uppercase tracking-tight text-slate-800">Tyre Events</h3>
            <CrudModule {...tyreEventConfig} fixedFilters={ff} testIdPrefix="vp-tyre-events" />
          </TabsContent>
          <TabsContent value="accidents"><CrudModule {...accidentConfig} fixedFilters={ff} testIdPrefix="vp-accidents" /></TabsContent>
          <TabsContent value="fastag"><CrudModule {...fastagConfig} fixedFilters={ff} testIdPrefix="vp-fastag" /></TabsContent>
          <TabsContent value="expenses"><ExpenseLedger vehicleId={id} /></TabsContent>
          <TabsContent value="downtime"><CrudModule {...downtimeConfig} fixedFilters={ff} testIdPrefix="vp-downtime" /></TabsContent>
        </div>
      </Tabs>
    </div>
  );
}
