import { useState } from "react";
import api from "@/lib/api";
import { CrudModule } from "@/components/CrudModule";
import {
  tripConfig, fuelConfig, serviceConfig, repairConfig, tyreConfig, tyreEventConfig,
  accidentConfig, fastagConfig, downtimeConfig, documentConfig, driverConfig,
} from "@/lib/configs";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { toast } from "sonner";
import { CheckCircle2, ThumbsUp, Play, Flag } from "lucide-react";

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
  const [next, label, Icon] = NEXT_REPAIR[row.status];
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
export const TripsPage = () => (
  <div><PageHeader title="Trip Management" subtitle="Record and monitor every vehicle movement" />
    <CrudModule {...tripConfig} rowActions={CloseTripAction} /></div>
);

export const FuelPage = () => (
  <div><PageHeader title="Fuel Management" subtitle="Fuel entries, mileage and fuel cost per KM are calculated automatically" />
    <CrudModule {...fuelConfig} /></div>
);

export const MaintenancePage = () => (
  <div><PageHeader title="Maintenance" subtitle="Scheduled services with next-due tracking by date and KM" />
    <CrudModule {...serviceConfig} /></div>
);

export const RepairsPage = () => (
  <div><PageHeader title="Breakdown & Repairs" subtitle="Minor repairs are logged directly; major repairs follow Reported → Approved → In Repair → Completed" />
    <CrudModule {...repairConfig} rowActions={RepairWorkflowAction} /></div>
);

export const TyresPage = () => (
  <div><PageHeader title="Tyre Management" subtitle="Tyre master with punctures, rotations, retreading and replacements" />
    <CrudModule {...tyreConfig} />
    <h2 className="mb-3 mt-10 text-xl font-bold tracking-tight text-slate-900">Tyre Events</h2>
    <CrudModule {...tyreEventConfig} /></div>
);

export const AccidentsPage = () => (
  <div><PageHeader title="Accident Register" subtitle="Accident records, FIR, insurance claims and settlements" />
    <CrudModule {...accidentConfig} /></div>
);

export const FastagPage = () => (
  <div><PageHeader title="Fastag Management" subtitle="Toll transactions and recharges — vehicle balance updates automatically" />
    <CrudModule {...fastagConfig} /></div>
);

export const DowntimePage = () => (
  <div><PageHeader title="Vehicle Downtime" subtitle="Track non-operational periods and reasons" />
    <CrudModule {...downtimeConfig} /></div>
);

export const DocumentsPage = () => (
  <div><PageHeader title="Document Management" subtitle="RC, Insurance, Fitness, Permit, PUC, Road Tax and more — with expiry tracking" />
    <CrudModule {...documentConfig} /></div>
);

export const DriversPage = () => (
  <div><PageHeader title="Driver Management" subtitle="Driver profiles, licenses and vehicle assignments" />
    <CrudModule {...driverConfig} /></div>
);
