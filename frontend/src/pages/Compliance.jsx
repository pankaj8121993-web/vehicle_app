import { useState, useEffect, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import api from "@/lib/api";
import { fmtDate, fmtINR } from "@/lib/format";
import { Loader2, ShieldAlert, FileText, IdCard, Wrench, Droplets, Radio, Phone, Mail, AlertTriangle } from "lucide-react";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Button } from "@/components/ui/button";

const SEV_COLORS = {
  danger: "border-red-200 bg-red-50 text-red-800",
  warning: "border-amber-200 bg-amber-50 text-amber-800",
  info: "border-blue-200 bg-blue-50 text-blue-800",
};

const SectionIcon = { documents: FileText, licenses: IdCard, services: Wrench, greasings: Droplets, fastag_low: Radio };

const SectionLabel = {
  documents: "Document Expiries",
  licenses: "Driver Licenses",
  services: "Service Due / Overdue",
  greasings: "Greasing Due / Overdue",
  fastag_low: "Fastag Low Balance",
};

const SectionFields = {
  documents: [
    { key: "vehicle_number", label: "Vehicle", isLink: "vehicle" },
    { key: "doc_type", label: "Document" },
    { key: "doc_number", label: "Number" },
    { key: "expiry_date", label: "Expiry", type: "date" },
    { key: "days_remaining", label: "Days" },
    { key: "_contact", label: "Contact", contactType: "doc_type" },
  ],
  licenses: [
    { key: "name", label: "Driver", isLink: "driver" },
    { key: "employee_number", label: "Emp #" },
    { key: "license_number", label: "License No" },
    { key: "license_expiry", label: "Expiry", type: "date" },
    { key: "days_remaining", label: "Days" },
    { key: "_contact", label: "Contact", contactType: "License" },
  ],
  services: [
    { key: "vehicle_number", label: "Vehicle", isLink: "vehicle" },
    { key: "next_due_date", label: "Next Due", type: "date" },
    { key: "next_due_km", label: "Next Due KM" },
    { key: "current_odometer", label: "Current KM" },
    { key: "days_remaining", label: "Days" },
  ],
  greasings: [
    { key: "vehicle_number", label: "Vehicle", isLink: "vehicle" },
    { key: "next_due_date", label: "Next Due", type: "date" },
    { key: "next_due_km", label: "Next Due KM" },
    { key: "current_odometer", label: "Current KM" },
    { key: "days_remaining", label: "Days" },
  ],
  fastag_low: [
    { key: "vehicle_number", label: "Vehicle", isLink: "vehicle" },
    { key: "fastag_number", label: "Fastag #" },
    { key: "balance", label: "Balance", type: "currency" },
    { key: "_contact", label: "Contact", contactType: "Fastag" },
  ],
};

const ContactPopover = ({ contacts }) => {
  if (!contacts || contacts.length === 0) {
    return <span className="text-xs text-slate-400">—</span>;
  }
  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button size="sm" variant="outline" className="h-7 rounded-none px-2 text-xs" data-testid="compliance-contact-trigger">
          <Phone className="mr-1 h-3 w-3" /> Contact
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-72 rounded-none p-3" align="end">
        <p className="mb-2 text-[10px] font-bold uppercase tracking-wide text-slate-500">Compliance Contacts</p>
        <div className="space-y-2">
          {contacts.map((c) => (
            <div key={c.id} className="border-l-2 border-slate-200 pl-2.5">
              <p className="text-sm font-semibold text-slate-900">{c.contact_person_name}</p>
              {c.vendor_name && <p className="font-mono text-[10px] uppercase tracking-wide text-slate-500">{c.vendor_name}</p>}
              <a href={`tel:${c.mobile}`} className="mt-0.5 flex items-center gap-1 text-xs text-blue-700 hover:underline" data-testid={`contact-tel-${c.id}`}>
                <Phone className="h-3 w-3" /> {c.mobile}
              </a>
              {c.email && (
                <a href={`mailto:${c.email}`} className="flex items-center gap-1 text-xs text-blue-700 hover:underline" data-testid={`contact-email-${c.id}`}>
                  <Mail className="h-3 w-3" /> {c.email}
                </a>
              )}
            </div>
          ))}
        </div>
      </PopoverContent>
    </Popover>
  );
};

const renderField = (f, row, contactsByType) => {
  const v = row[f.key];
  if (f.key === "_contact") {
    const ct = f.contactType === "doc_type" ? row.doc_type : f.contactType;
    return <ContactPopover contacts={contactsByType[ct] || []} />;
  }
  if (v === null || v === undefined || v === "") return <span className="text-xs text-slate-400">—</span>;
  if (f.type === "date") return <span className="font-mono">{fmtDate(v)}</span>;
  if (f.type === "currency") return <span className="font-mono">{fmtINR(v)}</span>;
  if (f.key === "days_remaining") {
    const d = Number(v);
    if (d < 0) return <span className="font-mono font-semibold text-red-700">{Math.abs(d)} OVERDUE</span>;
    return <span className="font-mono">{d}</span>;
  }
  return String(v);
};

export default function Compliance() {
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [contacts, setContacts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [severity, setSeverity] = useState("all");

  useEffect(() => {
    let mounted = true;
    setLoading(true);
    Promise.all([
      api.get("/compliance", { params: { severity, days_ahead: 90 } }),
      api.get("/compliance/contacts").catch(() => ({ data: [] })),
    ]).then(([cRes, cContacts]) => {
      if (!mounted) return;
      setData(cRes.data); setContacts(cContacts.data || []);
    }).finally(() => mounted && setLoading(false));
    return () => { mounted = false; };
  }, [severity]);

  const contactsByType = useMemo(() => {
    const out = {};
    for (const c of contacts) {
      if (!c.is_active) continue;
      (out[c.compliance_type] = out[c.compliance_type] || []).push(c);
    }
    return out;
  }, [contacts]);

  if (loading) {
    return <div className="flex h-64 items-center justify-center"><Loader2 className="h-6 w-6 animate-spin text-slate-400" /></div>;
  }
  if (!data) return <p>Could not load compliance data.</p>;

  const summary = data.summary;
  const sections = ["documents", "licenses", "services", "greasings", "fastag_low"];

  return (
    <div data-testid="compliance-page">
      <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="font-heading text-3xl font-black tracking-tighter text-slate-900 md:text-4xl">Compliance & Expiry Alerts</h1>
          <p className="mt-1 text-sm text-slate-500">Auto-aggregated from documents, licenses, services, greasing and Fastag.</p>
        </div>
        <div className="flex items-end gap-3">
          <Button variant="outline" className="rounded-none" onClick={() => navigate("/compliance/contacts")} data-testid="compliance-contacts-link">
            <Phone className="mr-1 h-4 w-4" /> Manage Contacts
          </Button>
          <div>
            <p className="mb-1 text-[10px] font-bold uppercase tracking-[0.08em] text-slate-500">Severity</p>
            <Select value={severity} onValueChange={setSeverity}>
              <SelectTrigger className="w-40 rounded-none" data-testid="compliance-severity-filter"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All</SelectItem>
                <SelectItem value="danger">Danger (red)</SelectItem>
                <SelectItem value="warning">Warning (amber)</SelectItem>
                <SelectItem value="info">Info (blue)</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>
      </div>

      <div className="mb-8 grid grid-cols-2 gap-3 md:grid-cols-5">
        <div className="border border-slate-200 bg-white p-4" data-testid="compliance-summary-total"><p className="text-xs font-bold uppercase tracking-wide text-slate-500">Items in scope</p><p className="font-mono text-2xl font-bold">{summary.total_items}</p></div>
        <div className="border border-red-200 bg-red-50 p-4" data-testid="compliance-summary-expired"><p className="text-xs font-bold uppercase tracking-wide text-red-700">Expired</p><p className="font-mono text-2xl font-bold text-red-700">{summary.expired}</p></div>
        <div className="border border-red-200 bg-red-50/60 p-4"><p className="text-xs font-bold uppercase tracking-wide text-red-700">≤ 7 days</p><p className="font-mono text-2xl font-bold text-red-700">{summary.expiring_7}</p></div>
        <div className="border border-amber-200 bg-amber-50 p-4"><p className="text-xs font-bold uppercase tracking-wide text-amber-700">≤ 30 days</p><p className="font-mono text-2xl font-bold text-amber-700">{summary.expiring_30}</p></div>
        <div className="border border-blue-200 bg-blue-50 p-4"><p className="text-xs font-bold uppercase tracking-wide text-blue-700">≤ 90 days</p><p className="font-mono text-2xl font-bold text-blue-700">{summary.expiring_90}</p></div>
      </div>

      <div className="space-y-6">
        {sections.map((s) => {
          const rows = data[s] || [];
          const Icon = SectionIcon[s] || ShieldAlert;
          const fields = SectionFields[s];
          return (
            <div key={s} className="border border-slate-200 bg-white" data-testid={`compliance-section-${s}`}>
              <div className="flex items-center justify-between border-b border-slate-200 px-5 py-3">
                <p className="flex items-center gap-2 text-sm font-bold uppercase tracking-tight text-slate-800">
                  <Icon className="h-4 w-4" /> {SectionLabel[s]}
                </p>
                <p className="text-xs text-slate-500">{rows.length} record{rows.length === 1 ? "" : "s"}</p>
              </div>
              {rows.length === 0 ? (
                <p className="px-5 py-6 text-center text-sm text-slate-400">Nothing in this category.</p>
              ) : (
                <table className="w-full text-sm">
                  <thead className="bg-slate-50">
                    <tr className="border-b border-slate-200">
                      {fields.map((f) => <th key={f.key} className="px-4 py-2 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">{f.label}</th>)}
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((r, i) => (
                      <tr key={i} className={`border-b border-slate-100 ${r.severity === "danger" ? "bg-red-50/40" : r.severity === "warning" ? "bg-amber-50/40" : ""}`} data-testid={`compliance-row-${s}-${i}`}>
                        {fields.map((f) => (
                          <td key={f.key} className="px-4 py-2.5">
                            {f.isLink === "vehicle" && r.vehicle_id ? (
                              <button onClick={() => navigate(`/vehicles/${r.vehicle_id}`)} className="font-mono font-semibold text-blue-700 hover:underline">
                                {r[f.key]}
                              </button>
                            ) : f.isLink === "driver" && r.driver_id ? (
                              <button onClick={() => navigate(`/drivers/${r.driver_id}`)} className="font-semibold text-blue-700 hover:underline">
                                {r[f.key]}
                              </button>
                            ) : (
                              renderField(f, r, contactsByType)
                            )}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          );
        })}
      </div>

      {summary.total_items === 0 && (
        <div className="mt-8 flex flex-col items-center gap-2 border border-dashed border-slate-300 bg-white py-12 text-slate-500">
          <AlertTriangle className="h-6 w-6 text-slate-300" />
          <p className="text-sm">All clear. No compliance items in the current window.</p>
        </div>
      )}
    </div>
  );
}
