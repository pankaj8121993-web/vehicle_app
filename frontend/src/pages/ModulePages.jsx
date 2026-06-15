import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { canApprove } from "@/lib/permissions";
import { CrudModule } from "@/components/CrudModule";
import { PeriodFilter } from "@/components/PeriodFilter";
import {
  tripConfig, fuelConfig, serviceConfig, repairConfig, tyreConfig, tyreEventConfig,
  accidentConfig, fastagConfig, downtimeConfig, documentConfig, driverConfig,
} from "@/lib/configs";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { toast } from "sonner";
import { CheckCircle2, ThumbsUp, Play, Flag, RefreshCw, Loader2 } from "lucide-react";

export const PageHeader = ({ title, subtitle }) => (
  <div className="mb-6">
    <h1 className="font-heading text-3xl font-black tracking-tighter text-slate-900 md:text-4xl">{title}</h1>
    {subtitle && <p className="mt-1 text-sm text-slate-500">{subtitle}</p>}
  </div>
);

// ---- Trip close action ----
export const CloseTripAction = (row, refresh) => {
  if (row.status !== "ongoing") return null;
  return <CloseTripButton row={row} refresh={refresh} />;
};

const CloseTripButton = ({ row, refresh }) => {
  const [open, setOpen] = useState(false);
  const [closingKm, setClosingKm] = useState("");

  const close = async () => {
    try {
      await api.patch(`/trips/${row.id}/close`, { closing_km: parseFloat(closingKm) });
      toast.success("Trip closed");
      setOpen(false);
      refresh();
    } catch (err) {
      toast.error(err.response?.data?.detail ? String(err.response.data.detail) : "Failed to close trip");
    }
  };

  return (
    <>
      <Button data-testid={`close-trip-${row.id}`} variant="outline" size="sm" className="h-7 rounded-none border-green-300 px-2 text-xs text-green-700 hover:bg-green-50" onClick={() => setOpen(true)}>
        <Flag className="mr-1 h-3 w-3" /> Close
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="rounded-none sm:max-w-sm">
          <DialogHeader><DialogTitle>Close Trip — Enter Closing KM</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <Label className="text-xs font-semibold uppercase text-slate-500">Closing Odometer (KM)</Label>
            <Input data-testid="close-trip-km-input" type="number" value={closingKm} onChange={(e) => setClosingKm(e.target.value)} className="rounded-none" />
            <Button data-testid="close-trip-confirm" onClick={close} className="w-full rounded-none bg-slate-900 hover:bg-slate-800">Close Trip</Button>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
};

// ---- Repair workflow action ----
const NEXT_REPAIR = { reported: ["approved", "Approve", ThumbsUp], approved: ["in_repair", "Start", Play], in_repair: ["completed", "Complete", CheckCircle2] };

export const RepairWorkflowAction = (row, refresh) => {
  if (row.repair_type !== "major" || !NEXT_REPAIR[row.status]) return null;
  return <RepairActionButton row={row} refresh={refresh} />;
};

const RepairActionButton = ({ row, refresh }) => {
  const { user } = useAuth();
  const [next, label, Icon] = NEXT_REPAIR[row.status];
  if (next === "approved" && !canApprove(user?.role)) {
    return <span className="text-[11px] font-semibold uppercase text-slate-400">Awaiting approval</span>;
  }
  const advance = async () => {
    try {
      await api.patch(`/repairs/${row.id}/status`, { status: next });
      toast.success(`Repair ${next.replace("_", " ")}`);
      refresh();
    } catch (err) {
      toast.error(err.response?.data?.detail ? String(err.response.data.detail) : "Action failed");
    }
  };
  return (
    <Button data-testid={`repair-action-${row.id}`} variant="outline" size="sm" className="h-7 rounded-none border-blue-300 px-2 text-xs text-blue-700 hover:bg-blue-50" onClick={advance}>
      <Icon className="mr-1 h-3 w-3" /> {label}
    </Button>
  );
};

// ---- Pages ----
const useDateRange = () => {
  const [range, setRange] = useState({});
  const filters = {};
  if (range.start_date) filters.start_date = range.start_date;
  if (range.end_date) filters.end_date = range.end_date;
  return { filters, setRange };
};

export const TripsPage = () => {
  const { filters, setRange } = useDateRange();
  return (
    <div><PageHeader title="Trip Management" subtitle="Record and monitor every vehicle movement" />
      <PeriodFilter testIdPrefix="trips-period" onChange={setRange} />
      <CrudModule {...tripConfig} fixedFilters={filters} rowActions={CloseTripAction} /></div>
  );
};

export const FuelPage = () => {
  const { filters, setRange } = useDateRange();
  return (
    <div><PageHeader title="Fuel Management" subtitle="Fuel entries, mileage and fuel cost per KM are calculated automatically" />
      <PeriodFilter testIdPrefix="fuel-period" onChange={setRange} />
      <CrudModule {...fuelConfig} fixedFilters={filters} /></div>
  );
};

export const MaintenancePage = () => {
  const { filters, setRange } = useDateRange();
  return (
    <div><PageHeader title="Maintenance" subtitle="Scheduled services with next-due tracking by date and KM" />
      <PeriodFilter testIdPrefix="maintenance-period" onChange={setRange} />
      <CrudModule {...serviceConfig} fixedFilters={filters} /></div>
  );
};

export const RepairsPage = () => {
  const { filters, setRange } = useDateRange();
  return (
    <div><PageHeader title="Breakdown & Repairs" subtitle="Minor repairs are logged directly; major repairs follow Reported → Approved → In Repair → Completed" />
      <PeriodFilter testIdPrefix="repairs-period" onChange={setRange} />
      <CrudModule {...repairConfig} fixedFilters={filters} rowActions={RepairWorkflowAction} /></div>
  );
};

export const TyresPage = () => {
  const { filters, setRange } = useDateRange();
  return (
    <div><PageHeader title="Tyre Management" subtitle="Tyre master with punctures, rotations, retreading and replacements" />
      <PeriodFilter testIdPrefix="tyres-period" onChange={setRange} />
      <CrudModule {...tyreConfig} fixedFilters={filters} />
      <h2 className="mb-3 mt-10 text-xl font-bold tracking-tight text-slate-900">Tyre Events</h2>
      <CrudModule {...tyreEventConfig} fixedFilters={filters} /></div>
  );
};

export const AccidentsPage = () => (
  <div><PageHeader title="Accident Register" subtitle="Accident records, FIR, insurance claims and settlements" />
    <CrudModule {...accidentConfig} /></div>
);

export const FastagPage = () => {
  const [refreshKey, setRefreshKey] = useState(0);
  const { filters, setRange } = useDateRange();
  return (
    <div><PageHeader title="Fastag Management" subtitle="Toll transactions and recharges — vehicle balance updates automatically" />
      <FastagSyncBar onSynced={() => setRefreshKey((k) => k + 1)} />
      <PeriodFilter testIdPrefix="fastag-period" onChange={setRange} />
      <CrudModule {...fastagConfig} fixedFilters={filters} refreshKey={refreshKey} /></div>
  );
};

const FastagSyncBar = ({ onSynced }) => {
  const [vehicles, setVehicles] = useState([]);
  const [vid, setVid] = useState("");
  const [syncing, setSyncing] = useState(false);

  useEffect(() => {
    api.get("/vehicles", { params: { all: "true" } }).then((r) => setVehicles(r.data)).catch(() => {});
  }, []);

  const sync = async () => {
    if (!vid) { toast.error("Select a vehicle first"); return; }
    setSyncing(true);
    try {
      const res = await api.post(`/fastag/sync/${vid}`);
      toast.success(`Fastag synced: ${res.data.synced_transactions} transactions fetched · Balance ₹${res.data.balance}`);
      onSynced();
    } catch (err) {
      toast.error(err.response?.data?.detail ? String(err.response.data.detail) : "Sync failed");
    } finally {
      setSyncing(false);
    }
  };

  return (
    <div className="mb-5 border border-blue-200 bg-blue-50 p-4" data-testid="fastag-sync-bar">
      <p className="mb-3 text-xs font-bold uppercase tracking-[0.08em] text-blue-800">
        Link Fastag — Auto-Retrieve Tolls & Balance <span className="font-normal normal-case text-blue-600">(simulated demo sync; a real bank/NPCI API can be plugged in later)</span>
      </p>
      <div className="flex flex-wrap items-center gap-3">
        <Select value={vid} onValueChange={setVid}>
          <SelectTrigger data-testid="fastag-sync-vehicle" className="w-64 rounded-none bg-white">
            <SelectValue placeholder="Select vehicle (must have Fastag number)" />
          </SelectTrigger>
          <SelectContent>
            {vehicles.map((v) => (
              <SelectItem key={v.id} value={v.id}>
                {v.vehicle_number}{v.fastag_number ? ` · ${v.fastag_number}` : " · no Fastag linked"}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Button data-testid="fastag-sync-btn" onClick={sync} disabled={syncing} className="rounded-none bg-blue-700 text-white hover:bg-blue-800">
          {syncing ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <RefreshCw className="mr-2 h-4 w-4" />} Sync Fastag
        </Button>
      </div>
    </div>
  );
};

export const DowntimePage = () => {
  const { filters, setRange } = useDateRange();
  return (
    <div><PageHeader title="Vehicle Downtime" subtitle="Track non-operational periods and reasons" />
      <PeriodFilter testIdPrefix="downtime-period" onChange={setRange} />
      <CrudModule {...downtimeConfig} fixedFilters={filters} /></div>
  );
};

export const DocumentsPage = () => (
  <div><PageHeader title="Document Management" subtitle="RC, Insurance, Fitness, Permit, PUC, Road Tax and more — with expiry tracking" />
    <CrudModule {...documentConfig} /></div>
);

export const DriversPage = () => {
  const navigate = useNavigate();
  return (
    <div><PageHeader title="Driver Management" subtitle="Click a driver to open their performance profile" />
      <CrudModule {...driverConfig} onRowClick={(row) => navigate(`/drivers/${row.id}`)} /></div>
  );
};
