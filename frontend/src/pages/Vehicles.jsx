import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { CrudModule } from "@/components/CrudModule";
import { vehicleConfig } from "@/lib/configs";
import { PageHeader } from "@/pages/ModulePages";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";

export default function Vehicles() {
  const navigate = useNavigate();
  const [includeDisposed, setIncludeDisposed] = useState(false);
  return (
    <div data-testid="vehicles-page">
      <PageHeader title="Vehicle Master" subtitle="Click any vehicle to open its complete digital profile" />
      <div className="mb-3 flex items-center gap-3 border border-slate-200 bg-white px-4 py-2.5">
        <Switch
          id="include-disposed"
          checked={includeDisposed}
          onCheckedChange={setIncludeDisposed}
          data-testid="vehicles-include-disposed-toggle"
        />
        <Label htmlFor="include-disposed" className="cursor-pointer text-xs font-bold uppercase tracking-[0.08em] text-slate-600">
          Include Sold / Scrapped
        </Label>
        <p className="ml-auto text-xs text-slate-400">By default, disposed vehicles are hidden everywhere.</p>
      </div>
      <CrudModule
        {...vehicleConfig}
        fixedFilters={{ include_disposed: includeDisposed ? "true" : "false" }}
        onRowClick={(row) => navigate(`/vehicles/${row.id}`)}
      />
    </div>
  );
}
