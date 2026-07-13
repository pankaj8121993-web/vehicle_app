import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import {
  Truck, Fuel as FuelIcon, Wrench, AlertTriangle, Camera, FileText, Phone, Flag,
} from "lucide-react";

const FLEET_MGR_PHONE = process.env.REACT_APP_FLEET_MANAGER_PHONE || "";

export default function DriverHome() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [driver, setDriver] = useState(null);
  const [ongoingTrip, setOngoingTrip] = useState(null);

  useEffect(() => {
    // Best-effort: try to look up driver record by full name match (no driver_id linkage yet)
    api.get("/drivers/active").then((r) => {
      const me = (r.data || []).find((d) => d.name?.toLowerCase() === (user?.full_name || "").toLowerCase());
      if (me) setDriver(me);
    }).catch(() => {});
    api.get("/trips", { params: { status: "ongoing", page_size: 1 } }).then((r) => {
      const items = r.data?.items || r.data || [];
      if (items.length) setOngoingTrip(items[0]);
    }).catch(() => {});
  }, [user]);

  const tiles = [
    { id: "start-trip", icon: Truck, label: "Start Trip", action: () => navigate("/trips"), color: "bg-blue-600" },
    { id: "end-trip", icon: Flag, label: ongoingTrip ? "End Trip" : "No Active Trip", action: () => navigate("/trips"), color: ongoingTrip ? "bg-green-700" : "bg-slate-400", disabled: !ongoingTrip },
    { id: "add-fuel", icon: FuelIcon, label: "Add Fuel", action: () => navigate("/fuel"), color: "bg-amber-600" },
    { id: "report-breakdown", icon: Wrench, label: "Report Breakdown", action: () => navigate("/repairs"), color: "bg-orange-600" },
    { id: "report-accident", icon: AlertTriangle, label: "Report Accident", action: () => navigate("/accidents"), color: "bg-red-600" },
    { id: "upload-invoice", icon: Camera, label: "Upload Invoice", action: () => navigate("/expenses"), color: "bg-indigo-600" },
    { id: "view-documents", icon: FileText, label: "View Documents", action: () => navigate("/documents"), color: "bg-slate-700" },
    {
      id: "call-fleet-mgr",
      icon: Phone,
      label: FLEET_MGR_PHONE ? "Call Fleet Manager" : "Contact Not Configured",
      action: () => {
        if (FLEET_MGR_PHONE) window.location.href = `tel:${FLEET_MGR_PHONE}`;
        else toast.info("Fleet manager phone number is not configured. Ask your admin to set REACT_APP_FLEET_MANAGER_PHONE.");
      },
      color: FLEET_MGR_PHONE ? "bg-emerald-700" : "bg-slate-400",
      disabled: !FLEET_MGR_PHONE,
    },
  ];

  return (
    <div className="mx-auto max-w-3xl space-y-6" data-testid="driver-home">
      <header className="border border-slate-200 bg-white p-4">
        <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-slate-500">Driver Home</p>
        <h1 className="mt-1 font-heading text-2xl font-black tracking-tighter text-slate-900" data-testid="driver-home-name">{user?.full_name || user?.username}</h1>
        <div className="mt-2 flex flex-wrap gap-3 text-xs text-slate-600">
          {driver?.employee_number && <span>EMP: <span className="font-mono font-semibold">{driver.employee_number}</span></span>}
          {driver?.assigned_vehicle_number && <span>Vehicle: <span className="font-mono font-semibold">{driver.assigned_vehicle_number}</span></span>}
          {ongoingTrip && <span className="text-amber-700 font-semibold">Ongoing trip — {ongoingTrip.vehicle_number}</span>}
        </div>
      </header>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4">
        {tiles.map((t) => (
          <button
            key={t.id}
            onClick={t.action}
            disabled={t.disabled}
            data-testid={`driver-tile-${t.id}`}
            className={`group flex min-h-[120px] flex-col items-center justify-center gap-2 border border-slate-200 p-4 text-center transition-colors ${t.disabled ? "cursor-not-allowed opacity-50" : "bg-white hover:border-slate-900"}`}
          >
            <span className={`grid h-12 w-12 place-items-center text-white ${t.color}`}>
              <t.icon className="h-6 w-6" />
            </span>
            <span className="text-sm font-semibold text-slate-800">{t.label}</span>
          </button>
        ))}
      </div>
    </div>
  );
}
