import { useNavigate } from "react-router-dom";
import { CrudModule } from "@/components/CrudModule";
import { vehicleConfig } from "@/lib/configs";
import { PageHeader } from "@/pages/ModulePages";

export default function Vehicles() {
  const navigate = useNavigate();
  return (
    <div data-testid="vehicles-page">
      <PageHeader title="Vehicle Master" subtitle="Click any vehicle to open its complete digital profile" />
      <CrudModule {...vehicleConfig} onRowClick={(row) => navigate(`/vehicles/${row.id}`)} />
    </div>
  );
}
