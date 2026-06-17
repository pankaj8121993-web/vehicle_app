import { CrudModule } from "@/components/CrudModule";
import { complianceContactConfig } from "@/lib/configs";

export default function ComplianceContacts() {
  return (
    <div data-testid="compliance-contacts-page">
      <div className="mb-6">
        <h1 className="font-heading text-3xl font-black tracking-tighter text-slate-900 md:text-4xl">Compliance Contacts</h1>
        <p className="mt-1 text-sm text-slate-500">Vendor & agency contact directory for RC, Insurance, Fitness, Permit, PUC and Fastag.</p>
      </div>
      <CrudModule {...complianceContactConfig} />
    </div>
  );
}
