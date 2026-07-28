import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import api from "@/lib/api";
import { CrudModule } from "@/components/CrudModule";
import { PeriodFilter } from "@/components/PeriodFilter";
import { TicketDetail } from "@/components/TicketDetail";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  tripConfig, fuelConfig, serviceConfig, repairConfig, tyreConfig, tyreEventConfig,
  accidentConfig, fastagConfig, downtimeConfig, documentConfig, driverConfig,
  greasingConfig,
} from "@/lib/configs";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { StatusTabs } from "@/components/StatusTabs";
import { toast } from "sonner";
import { Flag, RefreshCw, Loader2 } from "lucide-react";

export const PageHeader = ({ title, subtitle }) => (
  <div className="mb-6">
    <h1 className="font-heading text-3xl font-black tracking-tighter text-slate-900 md:text-4xl">{title}</h1>
    {subtitle && <p className="mt-1 text-sm text-slate-500">{subtitle}</p>}
  </div>
);

// ---- Trip lifecycle actions (OPS-01) ----
// Every button below calls a dedicated backend action (dispatch / close /
// finalize / cancel) — never a generic status write, which the API refuses.
const patchTrip = async (id, action, body, okMsg, refresh) => {
  try {
    await api.patch(`/trips/${id}/${action}`, body || {});
    toast.success(okMsg);
    refresh();
  } catch (err) {
    toast.error(err.response?.data?.detail ? String(err.response.data.detail) : `Failed to ${action} trip`);
  }
};

export const TripLifecycleActions = (row, refresh) => <TripActions row={row} refresh={refresh} />;
// Backward-compatible alias — VehicleProfile/DriverProfile import this name.
export const CloseTripAction = TripLifecycleActions;

const btnCls = "h-7 rounded-none px-2 text-xs";

const TripActions = ({ row, refresh }) => {
  const [closeOpen, setCloseOpen] = useState(false);
  const [cancelOpen, setCancelOpen] = useState(false);
  const [closingKm, setClosingKm] = useState("");
  const [reason, setReason] = useState("");
  const s = row.status;

  const doClose = async () => {
    await patchTrip(row.id, "close", { closing_km: parseFloat(closingKm) }, "Trip completed", refresh);
    setCloseOpen(false);
  };
  const doCancel = async () => {
    await patchTrip(row.id, "cancel", { reason }, "Trip cancelled", refresh);
    setCancelOpen(false);
  };

  return (
    <div className="flex flex-wrap gap-1">
      {s === "assigned" && (
        <Button data-testid={`dispatch-trip-${row.id}`} variant="outline" size="sm"
          className={`${btnCls} border-blue-300 text-blue-700 hover:bg-blue-50`}
          onClick={() => patchTrip(row.id, "dispatch", {}, "Trip dispatched", refresh)}>Dispatch</Button>
      )}
      {s === "ongoing" && (
        <Button data-testid={`close-trip-${row.id}`} variant="outline" size="sm"
          className={`${btnCls} border-green-300 text-green-700 hover:bg-green-50`}
          onClick={() => setCloseOpen(true)}><Flag className="mr-1 h-3 w-3" /> Complete</Button>
      )}
      {(s === "completed" || s === "settlement_pending") && (
        <Button data-testid={`finalize-trip-${row.id}`} variant="outline" size="sm"
          className={`${btnCls} border-slate-400 text-slate-700 hover:bg-slate-100`}
          onClick={() => patchTrip(row.id, "finalize", {}, "Trip closed out", refresh)}>Close out</Button>
      )}
      {["planned", "assigned", "ongoing"].includes(s) && (
        <Button data-testid={`cancel-trip-${row.id}`} variant="outline" size="sm"
          className={`${btnCls} border-red-300 text-red-700 hover:bg-red-50`}
          onClick={() => setCancelOpen(true)}>Cancel</Button>
      )}
      <Dialog open={closeOpen} onOpenChange={setCloseOpen}>
        <DialogContent className="rounded-none sm:max-w-sm">
          <DialogHeader><DialogTitle>Complete Trip — Enter Closing KM</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <Label className="text-xs font-semibold uppercase text-slate-500">Closing Odometer (KM)</Label>
            <Input data-testid="close-trip-km-input" type="number" value={closingKm} onChange={(e) => setClosingKm(e.target.value)} className="rounded-none" />
            <Button data-testid="close-trip-confirm" onClick={doClose} className="w-full rounded-none bg-slate-900 hover:bg-slate-800">Complete Trip</Button>
          </div>
        </DialogContent>
      </Dialog>
      <Dialog open={cancelOpen} onOpenChange={setCancelOpen}>
        <DialogContent className="rounded-none sm:max-w-sm">
          <DialogHeader><DialogTitle>Cancel Trip</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <Label className="text-xs font-semibold uppercase text-slate-500">Reason (optional)</Label>
            <Input data-testid="cancel-trip-reason" value={reason} onChange={(e) => setReason(e.target.value)} className="rounded-none" />
            <Button data-testid="cancel-trip-confirm" onClick={doCancel} className="w-full rounded-none bg-red-700 hover:bg-red-800">Cancel Trip</Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
};

// ---- Expense approval / payment actions (OPS-02) ----
// Each button calls a dedicated backend action; approval and payment are
// separate events and only management/admin may perform them.
export const ExpenseApprovalActions = (row, refresh) => <ExpenseActions row={row} refresh={refresh} />;

const ExpenseActions = ({ row, refresh }) => {
  const [approveOpen, setApproveOpen] = useState(false);
  const [payOpen, setPayOpen] = useState(false);
  const [approvedAmount, setApprovedAmount] = useState(String(row.amount ?? ""));
  const [payAmount, setPayAmount] = useState("");
  const s = row.approval_status || "submitted";
  const outstanding = (row.approved_amount ?? 0) - (row.paid_amount ?? 0);

  const call = async (method, url, body, okMsg) => {
    try {
      await api[method](url, body || {});
      toast.success(okMsg);
      refresh();
    } catch (err) {
      toast.error(err.response?.data?.detail ? String(err.response.data.detail) : "Action failed");
    }
  };

  return (
    <div className="flex flex-wrap gap-1">
      {s === "submitted" && (
        <>
          <Button data-testid={`approve-expense-${row.id}`} variant="outline" size="sm"
            className="h-7 rounded-none border-green-300 px-2 text-xs text-green-700 hover:bg-green-50"
            onClick={() => setApproveOpen(true)}>Approve</Button>
          <Button data-testid={`reject-expense-${row.id}`} variant="outline" size="sm"
            className="h-7 rounded-none border-red-300 px-2 text-xs text-red-700 hover:bg-red-50"
            onClick={() => call("patch", `/expenses/${row.id}/reject`, { reason: "Rejected" }, "Expense rejected")}>Reject</Button>
        </>
      )}
      {s === "approved" && outstanding > 0 && (
        <Button data-testid={`pay-expense-${row.id}`} variant="outline" size="sm"
          className="h-7 rounded-none border-blue-300 px-2 text-xs text-blue-700 hover:bg-blue-50"
          onClick={() => setPayOpen(true)}>Record Payment</Button>
      )}
      <Dialog open={approveOpen} onOpenChange={setApproveOpen}>
        <DialogContent className="rounded-none sm:max-w-sm">
          <DialogHeader><DialogTitle>Approve Expense</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <Label className="text-xs font-semibold uppercase text-slate-500">Approved Amount (₹)</Label>
            <Input data-testid="approve-expense-amount" type="number" value={approvedAmount} onChange={(e) => setApprovedAmount(e.target.value)} className="rounded-none" />
            <Button data-testid="approve-expense-confirm" onClick={async () => { await call("patch", `/expenses/${row.id}/approve`, { approved_amount: parseFloat(approvedAmount) }, "Expense approved"); setApproveOpen(false); }} className="w-full rounded-none bg-slate-900 hover:bg-slate-800">Approve</Button>
          </div>
        </DialogContent>
      </Dialog>
      <Dialog open={payOpen} onOpenChange={setPayOpen}>
        <DialogContent className="rounded-none sm:max-w-sm">
          <DialogHeader><DialogTitle>Record Payment (outstanding ₹{outstanding})</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <Label className="text-xs font-semibold uppercase text-slate-500">Payment Amount (₹)</Label>
            <Input data-testid="pay-expense-amount" type="number" value={payAmount} onChange={(e) => setPayAmount(e.target.value)} className="rounded-none" />
            <Button data-testid="pay-expense-confirm" onClick={async () => { await call("post", `/expenses/${row.id}/payments`, { amount: parseFloat(payAmount) }, "Payment recorded"); setPayOpen(false); }} className="w-full rounded-none bg-slate-900 hover:bg-slate-800">Record Payment</Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
};

// ---- Downtime close action (OPS-03) ----
export const DowntimeCloseAction = (row, refresh) => {
  if (row.status !== "open") return null;
  return <DowntimeCloseButton row={row} refresh={refresh} />;
};

const DowntimeCloseButton = ({ row, refresh }) => {
  const [open, setOpen] = useState(false);
  const [endDate, setEndDate] = useState("");
  const [reason, setReason] = useState("");
  const close = async () => {
    try {
      await api.patch(`/downtime/${row.id}/close`, { end_date: endDate || undefined, reason });
      toast.success("Downtime closed");
      setOpen(false);
      refresh();
    } catch (err) {
      toast.error(err.response?.data?.detail ? String(err.response.data.detail) : "Failed to close downtime");
    }
  };
  return (
    <>
      <Button data-testid={`close-downtime-${row.id}`} variant="outline" size="sm"
        className="h-7 rounded-none border-green-300 px-2 text-xs text-green-700 hover:bg-green-50"
        onClick={() => setOpen(true)}>Close</Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="rounded-none sm:max-w-sm">
          <DialogHeader><DialogTitle>Close Downtime</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <Label className="text-xs font-semibold uppercase text-slate-500">End Date</Label>
            <Input data-testid="close-downtime-date" type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} className="rounded-none" />
            <Label className="text-xs font-semibold uppercase text-slate-500">Reason</Label>
            <Input data-testid="close-downtime-reason" value={reason} onChange={(e) => setReason(e.target.value)} className="rounded-none" />
            <Button data-testid="close-downtime-confirm" onClick={close} className="w-full rounded-none bg-slate-900 hover:bg-slate-800">Close Downtime</Button>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
};

// ---- Tyre lifecycle actions (OPS-03) ----
export const TyreActions = (row, refresh) => <TyreActionButtons row={row} refresh={refresh} />;

const TyreActionButtons = ({ row, refresh }) => {
  const [transferOpen, setTransferOpen] = useState(false);
  const [scrapOpen, setScrapOpen] = useState(false);
  const [vehicles, setVehicles] = useState([]);
  const [toVehicle, setToVehicle] = useState("");
  const [odo, setOdo] = useState("");
  const [reason, setReason] = useState("");
  const terminal = row.status === "scrapped" || row.status === "removed";

  const loadVehicles = async () => {
    try {
      const res = await api.get("/vehicles?all=true");
      setVehicles((res.data || []).filter((v) => v.id !== row.vehicle_id));
    } catch { /* ignore */ }
  };
  const doTransfer = async () => {
    try {
      await api.patch(`/tyres/${row.id}/transfer`, { to_vehicle_id: toVehicle, odometer: odo ? parseFloat(odo) : undefined });
      toast.success("Tyre transferred");
      setTransferOpen(false);
      refresh();
    } catch (err) {
      toast.error(err.response?.data?.detail ? String(err.response.data.detail) : "Transfer failed");
    }
  };
  const doScrap = async () => {
    try {
      await api.patch(`/tyres/${row.id}/scrap`, { odometer: odo ? parseFloat(odo) : undefined, reason });
      toast.success("Tyre scrapped");
      setScrapOpen(false);
      refresh();
    } catch (err) {
      toast.error(err.response?.data?.detail ? String(err.response.data.detail) : "Scrap failed");
    }
  };
  if (terminal) return null;
  return (
    <div className="flex flex-wrap gap-1">
      <Button data-testid={`transfer-tyre-${row.id}`} variant="outline" size="sm"
        className="h-7 rounded-none border-blue-300 px-2 text-xs text-blue-700 hover:bg-blue-50"
        onClick={() => { setTransferOpen(true); loadVehicles(); }}>Transfer</Button>
      <Button data-testid={`scrap-tyre-${row.id}`} variant="outline" size="sm"
        className="h-7 rounded-none border-red-300 px-2 text-xs text-red-700 hover:bg-red-50"
        onClick={() => setScrapOpen(true)}>Scrap</Button>
      <Dialog open={transferOpen} onOpenChange={setTransferOpen}>
        <DialogContent className="rounded-none sm:max-w-sm">
          <DialogHeader><DialogTitle>Transfer Tyre</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <Label className="text-xs font-semibold uppercase text-slate-500">To Vehicle</Label>
            <Select value={toVehicle} onValueChange={setToVehicle}>
              <SelectTrigger data-testid="transfer-tyre-vehicle" className="rounded-none"><SelectValue placeholder="Select vehicle" /></SelectTrigger>
              <SelectContent>{vehicles.map((v) => <SelectItem key={v.id} value={v.id}>{v.vehicle_number}</SelectItem>)}</SelectContent>
            </Select>
            <Label className="text-xs font-semibold uppercase text-slate-500">Odometer</Label>
            <Input data-testid="transfer-tyre-odo" type="number" value={odo} onChange={(e) => setOdo(e.target.value)} className="rounded-none" />
            <Button data-testid="transfer-tyre-confirm" onClick={doTransfer} className="w-full rounded-none bg-slate-900 hover:bg-slate-800">Transfer</Button>
          </div>
        </DialogContent>
      </Dialog>
      <Dialog open={scrapOpen} onOpenChange={setScrapOpen}>
        <DialogContent className="rounded-none sm:max-w-sm">
          <DialogHeader><DialogTitle>Scrap Tyre</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <Label className="text-xs font-semibold uppercase text-slate-500">Odometer</Label>
            <Input data-testid="scrap-tyre-odo" type="number" value={odo} onChange={(e) => setOdo(e.target.value)} className="rounded-none" />
            <Label className="text-xs font-semibold uppercase text-slate-500">Reason</Label>
            <Input data-testid="scrap-tyre-reason" value={reason} onChange={(e) => setReason(e.target.value)} className="rounded-none" />
            <Button data-testid="scrap-tyre-confirm" onClick={doScrap} className="w-full rounded-none bg-red-700 hover:bg-red-800">Scrap Tyre</Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
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
  const [status, setStatus] = useState("");
  if (status) filters.status = status;
  return (
    <div><PageHeader title="Trip Management" subtitle="Record and monitor every vehicle movement" />
      <PeriodFilter testIdPrefix="trips-period" onChange={setRange} />
      <StatusTabs testIdPrefix="trips" value={status} onChange={setStatus}
        tabs={[{ value: "", label: "All" }, { value: "planned", label: "Planned" }, { value: "assigned", label: "Assigned" }, { value: "ongoing", label: "Ongoing" }, { value: "completed", label: "Completed" }, { value: "closed", label: "Closed" }, { value: "cancelled", label: "Cancelled" }]} />
      <CrudModule {...tripConfig} fixedFilters={filters} rowActions={TripLifecycleActions} /></div>
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
    <div><PageHeader title="Maintenance" subtitle="Scheduled services and greasing with next-due tracking by date and KM" />
      <PeriodFilter testIdPrefix="maintenance-period" onChange={setRange} />
      <Tabs defaultValue="services">
        <TabsList className="rounded-none border border-slate-200 bg-white p-0">
          <TabsTrigger value="services" data-testid="maintenance-tab-services" className="rounded-none px-5 py-2.5 data-[state=active]:bg-slate-900 data-[state=active]:text-white">Services</TabsTrigger>
          <TabsTrigger value="greasing" data-testid="maintenance-tab-greasing" className="rounded-none px-5 py-2.5 data-[state=active]:bg-slate-900 data-[state=active]:text-white">Greasing</TabsTrigger>
        </TabsList>
        <TabsContent value="services" className="mt-5"><CrudModule {...serviceConfig} fixedFilters={filters} /></TabsContent>
        <TabsContent value="greasing" className="mt-5"><CrudModule {...greasingConfig} fixedFilters={filters} /></TabsContent>
      </Tabs>
    </div>
  );
};

export const RepairsPage = () => {
  const { filters, setRange } = useDateRange();
  const [status, setStatus] = useState("");
  const [activeTicket, setActiveTicket] = useState(null);
  const [refreshKey, setRefreshKey] = useState(0);
  if (status) filters.status = status;
  const handleUpdated = (updated) => {
    // Preserve enriched fields (vehicle_number, driver_name, etc.) that
    // list GET populates but PATCH responses may omit.
    setActiveTicket((prev) => ({ ...(prev || {}), ...updated, vehicle_number: updated.vehicle_number || prev?.vehicle_number }));
    setRefreshKey((k) => k + 1);
  };
  return (
    <div data-testid="tickets-page">
      <PageHeader title="Service Tickets" subtitle="7-stage workflow: Open → Under Review → Approved → Sent for Repair → In Repair → Repaired → Closed" />
      <PeriodFilter testIdPrefix="repairs-period" onChange={setRange} />
      <StatusTabs testIdPrefix="tickets" value={status} onChange={setStatus}
        tabs={[
          { value: "", label: "All" }, { value: "open", label: "Open" },
          { value: "under_review", label: "Under Review" }, { value: "approved", label: "Approved" },
          { value: "sent_for_repair", label: "Sent for Repair" }, { value: "in_repair", label: "In Repair" },
          { value: "repaired", label: "Repaired" }, { value: "closed", label: "Closed" },
        ]} />
      <CrudModule
        {...repairConfig}
        fixedFilters={filters}
        onRowClick={(row) => setActiveTicket(row)}
        refreshKey={refreshKey}
      />
      <TicketDetail
        ticket={activeTicket}
        open={!!activeTicket}
        onClose={() => setActiveTicket(null)}
        onUpdated={handleUpdated}
      />
    </div>
  );
};

export const TyresPage = () => {
  const { filters, setRange } = useDateRange();
  return (
    <div><PageHeader title="Tyre Management" subtitle="Tyre master with punctures, rotations, retreading and replacements" />
      <PeriodFilter testIdPrefix="tyres-period" onChange={setRange} />
      <CrudModule {...tyreConfig} fixedFilters={filters} rowActions={TyreActions} />
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
      <CrudModule {...downtimeConfig} fixedFilters={filters} rowActions={DowntimeCloseAction} /></div>
  );
};

export const DocumentsPage = () => (
  <div><PageHeader title="Document Management" subtitle="RC, Insurance, Fitness, Permit, PUC, Road Tax and more — with expiry tracking" />
    <CrudModule {...documentConfig} /></div>
);

export const DriversPage = () => {
  const navigate = useNavigate();
  const [status, setStatus] = useState("");
  const filters = status ? { status } : {};
  return (
    <div><PageHeader title="Driver Management" subtitle="Click a driver to open their performance profile" />
      <StatusTabs testIdPrefix="drivers" value={status} onChange={setStatus}
        tabs={[
          { value: "", label: "All" }, { value: "active", label: "Active" },
          { value: "on_leave", label: "On Leave" }, { value: "resigned", label: "Resigned" },
          { value: "terminated", label: "Terminated" },
        ]} />
      <CrudModule {...driverConfig} fixedFilters={filters} onRowClick={(row) => navigate(`/drivers/${row.id}`)} /></div>
  );
};
