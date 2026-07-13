import { CrudModule } from "@/components/CrudModule";
import { vendorConfig } from "@/lib/configs";
import { PageHeader } from "@/pages/ModulePages";

export default function Vendors() {
  return (
    <div data-testid="vendors-page">
      <PageHeader title="Vendor Master" subtitle="Saved vendors auto-fill service & repair forms — keep mobile, GST and contact info up to date" />
      <CrudModule {...vendorConfig} />
    </div>
  );
}
