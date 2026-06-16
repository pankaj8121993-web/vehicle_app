import { useState, useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import api from "@/lib/api";
import { fmtINR, fmtNum } from "@/lib/format";
import { StatusBadge, ExpiryBadge } from "@/components/StatusBadge";
import { CrudModule } from "@/components/CrudModule";
import { tripConfig, fuelConfig, accidentConfig } from "@/lib/configs";
import { CloseTripAction } from "@/pages/ModulePages";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Loader2, ArrowLeft, Phone } from "lucide-react";

const Stat = ({ label, children, testId }) => (
  <div className="border border-slate-200 bg-white p-4" data-testid={testId}>
    <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-slate-500">{label}</p>
    <div className="mt-1.5 font-mono text-lg font-bold text-slate-900">{children}</div>
  </div>
);

export default function DriverProfile() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [stats, setStats] = useState(null);
  const [photoUrl, setPhotoUrl] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api.get(`/drivers/${id}/stats`)
      .then((res) => setStats(res.data))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [id]);

  useEffect(() => {
    const fid = stats?.driver?.photo_file_id;
    if (!fid) { setPhotoUrl(null); return; }
    let blobUrl;
    api.get(`/files/${fid}`, { responseType: "blob" })
      .then((r) => { blobUrl = URL.createObjectURL(r.data); setPhotoUrl(blobUrl); })
      .catch(() => setPhotoUrl(null));
    return () => { if (blobUrl) URL.revokeObjectURL(blobUrl); };
  }, [stats?.driver?.photo_file_id]);

  if (loading) return <div className="flex h-64 items-center justify-center"><Loader2 className="h-6 w-6 animate-spin text-slate-400" /></div>;
  if (!stats) return <p className="text-slate-500">Driver not found.</p>;

  const d = stats.driver;
  const ff = { driver_id: id };
  const skills = Array.isArray(d.skills) ? d.skills : [];

  return (
    <div data-testid="driver-profile-page">
      <Button variant="ghost" size="sm" onClick={() => navigate("/drivers")} className="mb-4 -ml-2 text-slate-500 hover:text-slate-900" data-testid="back-to-drivers">
        <ArrowLeft className="mr-1 h-4 w-4" /> All Drivers
      </Button>

      <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div className="flex items-start gap-4">
          {photoUrl ? (
            <img src={photoUrl} alt={d.name} className="h-24 w-24 border border-slate-200 object-cover" data-testid="driver-photo" />
          ) : (
            <div className="flex h-24 w-24 items-center justify-center border border-dashed border-slate-300 text-[10px] font-semibold uppercase tracking-wide text-slate-400" data-testid="driver-photo-empty">No Photo</div>
          )}
          <div>
            <div className="flex items-center gap-3">
              <h1 className="font-heading text-3xl font-black tracking-tighter text-slate-900 md:text-4xl" data-testid="driver-name-heading">{d.name}</h1>
              <StatusBadge value={d.status} />
            </div>
            {d.employee_number && (
              <p className="mt-1 font-mono text-xs font-bold uppercase tracking-[0.1em] text-slate-700" data-testid="driver-employee-number">EMP: {d.employee_number}</p>
            )}
            <p className="mt-1 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-slate-500">
              {d.mobile && <span className="inline-flex items-center gap-1"><Phone className="h-3.5 w-3.5" />{d.mobile}</span>}
              {d.license_number && <span className="font-mono text-xs">DL: {d.license_number}</span>}
              {d.assigned_vehicle_number && <span>Assigned: <span className="font-mono font-semibold text-slate-800">{d.assigned_vehicle_number}</span></span>}
            </p>
            {skills.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-1" data-testid="driver-skills">
                {skills.map((s) => (
                  <span key={s} className="border border-slate-300 bg-slate-50 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-slate-700">{s}</span>
                ))}
              </div>
            )}
          </div>
        </div>
        <div className="text-right">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">License Expiry</p>
          <ExpiryBadge date={d.license_expiry} />
        </div>
      </div>

      <div className="mb-8 grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-7">
        <Stat label="Total Trips" testId="driver-stat-trips">{fmtNum(stats.total_trips)}</Stat>
        <Stat label="Total KM Driven" testId="driver-stat-km">{fmtNum(stats.total_km)}</Stat>
        <Stat label="Avg Mileage" testId="driver-stat-mileage">{stats.avg_mileage ? `${stats.avg_mileage} KM/L` : "—"}</Stat>
        <Stat label="Fuel Entries" testId="driver-stat-fuel-entries">{fmtNum(stats.fuel_entries)}</Stat>
        <Stat label="Fuel Cost" testId="driver-stat-fuel-cost">{fmtINR(stats.total_fuel_cost)}</Stat>
        <Stat label="Trip Expenses" testId="driver-stat-trip-expenses">{fmtINR(stats.trip_expenses)}</Stat>
        <Stat label="Accidents" testId="driver-stat-accidents">{fmtNum(stats.accidents_count)}</Stat>
      </div>

      <Tabs defaultValue="trips">
        <TabsList className="h-auto w-full justify-start overflow-x-auto rounded-none border border-slate-200 bg-white p-0">
          {[{ v: "trips", l: "Trips" }, { v: "fuel", l: "Fuel" }, { v: "accidents", l: "Accidents" }].map((t) => (
            <TabsTrigger key={t.v} value={t.v} data-testid={`driver-tab-${t.v}`}
              className="rounded-none border-b-2 border-transparent px-4 py-3 text-sm font-semibold data-[state=active]:border-slate-900 data-[state=active]:bg-white data-[state=active]:text-slate-900">
              {t.l}
            </TabsTrigger>
          ))}
        </TabsList>
        <div className="mt-5">
          <TabsContent value="trips"><CrudModule {...tripConfig} fixedFilters={ff} rowActions={CloseTripAction} testIdPrefix="dp-trips" /></TabsContent>
          <TabsContent value="fuel"><CrudModule {...fuelConfig} fixedFilters={ff} testIdPrefix="dp-fuel" /></TabsContent>
          <TabsContent value="accidents"><CrudModule {...accidentConfig} fixedFilters={ff} testIdPrefix="dp-accidents" /></TabsContent>
        </div>
      </Tabs>
    </div>
  );
}
