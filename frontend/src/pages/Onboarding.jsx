import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { BrandMark } from "@/pages/Landing";
import { toast } from "sonner";
import { ArrowLeft, ArrowRight, Check, Loader2, Eye, EyeOff } from "lucide-react";

const ORG_TYPES = [
  "Company", "Proprietorship", "Partnership", "LLP", "Private Limited Company",
  "Public Limited Company", "Trust or Institution", "Transport Operator",
  "Logistics Business", "Individual Fleet Owner", "Other",
];
const OWNERSHIP = ["Owned", "Leased", "Hired", "Rented", "Attached", "Mixed"];
const CATEGORIES = ["Cars", "Two-wheelers", "Vans", "Pickups", "LCVs", "HCVs", "Trucks", "Trailers", "Tankers", "Buses", "Construction vehicles", "Other"];
const OPERATIONS = ["Goods transport", "Passenger transport", "Employee transport", "Delivery operations", "Local operations", "Intercity operations", "Interstate operations", "Internal company use", "Mixed operations"];
const COMPLIANCE_DOCS = ["RC", "Insurance", "Permit", "Fitness", "PUC", "Road Tax", "Driver Licence", "FASTag", "GPS Subscription", "Loan Documents", "AMC"];
const PREFERENCES = [
  ["trip_settlement", "Trip settlement & expenses"],
  ["mandatory_odometer", "Mandatory start & end odometer"],
  ["fastag_usage", "FASTag usage"],
  ["tyre_management", "Tyre management"],
  ["vendor_management", "Vendor management"],
  ["driver_performance", "Driver performance tracking"],
  ["vehicle_profitability", "Vehicle cost & profitability"],
  ["insurance_claims", "Insurance claim tracking"],
];
const REMINDER_OPTIONS = [7, 15, 30, 60, 90];
const STATUTORY_TYPES = ["Company", "Partnership", "LLP", "Private Limited Company", "Public Limited Company", "Transport Operator", "Logistics Business", "Trust or Institution"];

const STEP_TITLES = ["Account Type", "Organisation", "Address & Branch", "Administrator", "Preferences", "Review"];

const Field = ({ label, required, children, hint }) => (
  <div className="space-y-1.5">
    <Label className="text-xs font-bold uppercase tracking-[0.08em] text-slate-700">
      {label} {required && <span className="text-red-500">*</span>}
    </Label>
    {children}
    {hint && <p className="text-[11px] text-slate-400">{hint}</p>}
  </div>
);

const TextInput = (props) => <Input {...props} className="rounded-none" />;

export default function Onboarding() {
  const navigate = useNavigate();
  const { setSession } = useAuth();
  const [step, setStep] = useState(0);
  const [loading, setLoading] = useState(false);
  const [showPw, setShowPw] = useState(false);
  const [f, setF] = useState({
    org_type: "", fleet_ownership: "Owned", fleet_size: "", driver_count: "",
    categories: [], operations: [],
    legal_name: "", trade_name: "", industry: "", gstin: "", pan: "", email_org: "",
    phone_org: "", website: "", year_established: "", state: "", city: "",
    address: "", pin: "", branch_name: "Head Office", branch_code: "HO",
    full_name: "", designation: "", email: "", mobile: "", username: "",
    password: "", confirm_password: "", terms: false,
    preferences: { trip_settlement: true, mandatory_odometer: true, fastag_usage: true, tyre_management: true, vendor_management: true, driver_performance: true, vehicle_profitability: true, insurance_claims: false },
    compliance_docs: ["RC", "Insurance", "Permit", "Fitness", "PUC", "Road Tax"],
    reminder_days: 30,
  });
  const set = (k, v) => setF((p) => ({ ...p, [k]: v }));
  const toggle = (k, v) => set(k, f[k].includes(v) ? f[k].filter((x) => x !== v) : [...f[k], v]);
  const showStatutory = STATUTORY_TYPES.includes(f.org_type);

  const errors = useMemo(() => {
    const e = {};
    if (step === 0 && !f.org_type) e.org_type = "Select an account type";
    if (step === 1) {
      if (!f.legal_name.trim()) e.legal_name = "Legal name is required";
      if (f.gstin && !/^[0-9A-Z]{15}$/.test(f.gstin.toUpperCase())) e.gstin = "GSTIN must be 15 characters";
      if (f.pan && !/^[A-Z]{5}[0-9]{4}[A-Z]$/.test(f.pan.toUpperCase())) e.pan = "PAN format: AAAAA9999A";
    }
    if (step === 3) {
      if (!f.full_name.trim()) e.full_name = "Full name is required";
      if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(f.email)) e.email = "Enter a valid email";
      if (!/^[a-z0-9._-]{3,40}$/.test(f.username)) e.username = "3–40 chars: letters, numbers, . _ -";
      if (f.password.length < 8) e.password = "Minimum 8 characters";
      if (f.password !== f.confirm_password) e.confirm_password = "Passwords do not match";
      if (!f.terms) e.terms = "Please accept the terms to continue";
    }
    return e;
  }, [step, f]);

  const next = () => {
    if (Object.keys(errors).length) {
      toast.error(Object.values(errors)[0]);
      return;
    }
    setStep((s) => Math.min(s + 1, 5));
  };

  const submit = async () => {
    setLoading(true);
    try {
      const r = await api.post("/onboarding/register", {
        org: {
          legal_name: f.legal_name.trim(), trade_name: f.trade_name.trim() || f.legal_name.trim(),
          org_type: f.org_type, fleet_ownership: f.fleet_ownership, industry: f.industry,
          gstin: f.gstin.toUpperCase() || null, pan: f.pan.toUpperCase() || null,
          email: f.email_org, phone: f.phone_org, website: f.website,
          year_established: f.year_established, state: f.state, city: f.city,
          address: { line1: f.address, city: f.city, state: f.state, pin: f.pin },
          reminder_days: f.reminder_days,
        },
        admin: {
          full_name: f.full_name.trim(), designation: f.designation, email: f.email.toLowerCase().trim(),
          mobile: f.mobile, username: f.username.toLowerCase().trim(), password: f.password,
        },
        branch: { name: f.branch_name || "Head Office", code: f.branch_code || "HO", address: f.address },
        preferences: f.preferences,
        compliance_docs: f.compliance_docs,
        fleet_profile: {
          fleet_size: f.fleet_size, driver_count: f.driver_count,
          categories: f.categories, operations: f.operations,
        },
      });
      setSession(r.data.token, r.data.user);
      toast.success("Your FleetFlow workspace is ready.");
      navigate("/dashboard", { replace: true });
    } catch (err) {
      const d = err?.response?.data?.detail;
      toast.error(typeof d === "string" ? d : "Registration failed. Please review your details.");
    } finally {
      setLoading(false);
    }
  };

  const chip = (list, item, key) => (
    <button key={item} type="button" onClick={() => toggle(key, item)}
      data-testid={`onb-chip-${key}-${item.toLowerCase().replace(/\s+/g, "-")}`}
      className={`border px-3 py-1.5 text-xs font-semibold transition-colors ${
        list.includes(item) ? "border-slate-900 bg-slate-900 text-white" : "border-slate-300 bg-white text-slate-600 hover:border-slate-500"
      }`}>
      {item}
    </button>
  );

  return (
    <div className="min-h-screen bg-slate-50" data-testid="onboarding-page">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex h-16 max-w-4xl items-center justify-between px-5">
          <Link to="/"><BrandMark /></Link>
          <Link to="/login" className="text-sm font-semibold text-slate-500 hover:text-slate-900" data-testid="onb-login-link">
            Already have a workspace? <span className="text-slate-900 underline underline-offset-4">Login</span>
          </Link>
        </div>
      </header>

      <main className="mx-auto max-w-4xl px-5 py-10">
        {/* Progress */}
        <div className="mb-10">
          <p className="text-[11px] font-bold uppercase tracking-[0.2em] text-slate-500">Create your workspace</p>
          <h1 className="mt-1 font-heading text-3xl font-black tracking-tighter text-slate-900">Step {step + 1} of 6 — {STEP_TITLES[step]}</h1>
          <div className="mt-5 flex gap-1.5" data-testid="onb-progress">
            {STEP_TITLES.map((t, i) => (
              <div key={t} className="flex-1">
                <div className={`h-1.5 ${i < step ? "bg-slate-900" : i === step ? "bg-amber-400" : "bg-slate-200"}`} />
                <p className={`mt-1.5 hidden text-[10px] font-bold uppercase tracking-wide sm:block ${i === step ? "text-slate-900" : "text-slate-400"}`}>{t}</p>
              </div>
            ))}
          </div>
        </div>

        <div className="border border-slate-200 bg-white p-6 sm:p-8">
          {step === 0 && (
            <div className="space-y-7">
              <Field label="What kind of organisation is this?" required>
                <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
                  {ORG_TYPES.map((t) => (
                    <button key={t} type="button" onClick={() => set("org_type", t)}
                      data-testid={`onb-orgtype-${t.toLowerCase().replace(/\s+/g, "-")}`}
                      className={`border px-3 py-3 text-left text-sm font-semibold transition-colors ${
                        f.org_type === t ? "border-slate-900 bg-slate-900 text-white" : "border-slate-200 bg-white text-slate-700 hover:border-slate-400"
                      }`}>{t}</button>
                  ))}
                </div>
              </Field>
              <Field label="Fleet ownership type">
                <div className="flex flex-wrap gap-2">
                  {OWNERSHIP.map((o) => (
                    <button key={o} type="button" onClick={() => set("fleet_ownership", o)}
                      className={`border px-4 py-2 text-sm font-semibold transition-colors ${
                        f.fleet_ownership === o ? "border-slate-900 bg-slate-900 text-white" : "border-slate-300 text-slate-600 hover:border-slate-500"
                      }`}>{o}</button>
                  ))}
                </div>
              </Field>
              <div className="grid gap-5 sm:grid-cols-2">
                <Field label="Approximate fleet size"><TextInput type="number" min="0" data-testid="onb-fleet-size" value={f.fleet_size} onChange={(e) => set("fleet_size", e.target.value)} placeholder="e.g. 12" /></Field>
                <Field label="Number of drivers"><TextInput type="number" min="0" value={f.driver_count} onChange={(e) => set("driver_count", e.target.value)} placeholder="e.g. 10" /></Field>
              </div>
              <Field label="Vehicle categories (select all that apply)">
                <div className="flex flex-wrap gap-2">{CATEGORIES.map((c) => chip(f.categories, c, "categories"))}</div>
              </Field>
              <Field label="Nature of operations">
                <div className="flex flex-wrap gap-2">{OPERATIONS.map((o) => chip(f.operations, o, "operations"))}</div>
              </Field>
            </div>
          )}

          {step === 1 && (
            <div className="grid gap-5 sm:grid-cols-2">
              <Field label="Legal name" required><TextInput data-testid="onb-legal-name" value={f.legal_name} onChange={(e) => set("legal_name", e.target.value)} placeholder="Registered legal name" /></Field>
              <Field label="Trade / display name" hint="Shown across your workspace (defaults to legal name)"><TextInput value={f.trade_name} onChange={(e) => set("trade_name", e.target.value)} /></Field>
              <Field label="Industry"><TextInput value={f.industry} onChange={(e) => set("industry", e.target.value)} placeholder="e.g. FMCG distribution" /></Field>
              <Field label="Year of establishment"><TextInput type="number" value={f.year_established} onChange={(e) => set("year_established", e.target.value)} placeholder="e.g. 2012" /></Field>
              {showStatutory && (
                <>
                  <Field label="GSTIN" hint="Optional — 15 characters"><TextInput data-testid="onb-gstin" value={f.gstin} onChange={(e) => set("gstin", e.target.value.toUpperCase())} maxLength={15} placeholder="27AAAAA0000A1Z5" /></Field>
                  <Field label="PAN" hint="Optional"><TextInput value={f.pan} onChange={(e) => set("pan", e.target.value.toUpperCase())} maxLength={10} placeholder="AAAAA9999A" /></Field>
                </>
              )}
              <Field label="Organisation email"><TextInput type="email" value={f.email_org} onChange={(e) => set("email_org", e.target.value)} placeholder="office@company.in" /></Field>
              <Field label="Phone"><TextInput value={f.phone_org} onChange={(e) => set("phone_org", e.target.value)} placeholder="020-00000000" /></Field>
              <Field label="Website"><TextInput value={f.website} onChange={(e) => set("website", e.target.value)} placeholder="https://" /></Field>
            </div>
          )}

          {step === 2 && (
            <div className="grid gap-5 sm:grid-cols-2">
              <div className="sm:col-span-2">
                <Field label="Registered / operational address"><TextInput data-testid="onb-address" value={f.address} onChange={(e) => set("address", e.target.value)} placeholder="Street, area, landmark" /></Field>
              </div>
              <Field label="City"><TextInput value={f.city} onChange={(e) => set("city", e.target.value)} /></Field>
              <Field label="State"><TextInput value={f.state} onChange={(e) => set("state", e.target.value)} /></Field>
              <Field label="PIN code"><TextInput value={f.pin} onChange={(e) => set("pin", e.target.value)} maxLength={6} /></Field>
              <div className="sm:col-span-2 border-t border-slate-100 pt-5">
                <p className="mb-4 text-xs font-bold uppercase tracking-[0.14em] text-slate-500">First branch</p>
                <div className="grid gap-5 sm:grid-cols-2">
                  <Field label="Branch name"><TextInput data-testid="onb-branch-name" value={f.branch_name} onChange={(e) => set("branch_name", e.target.value)} /></Field>
                  <Field label="Branch code"><TextInput value={f.branch_code} onChange={(e) => set("branch_code", e.target.value)} /></Field>
                </div>
              </div>
            </div>
          )}

          {step === 3 && (
            <div className="grid gap-5 sm:grid-cols-2">
              <Field label="Full name" required><TextInput data-testid="onb-admin-name" value={f.full_name} onChange={(e) => set("full_name", e.target.value)} /></Field>
              <Field label="Designation"><TextInput value={f.designation} onChange={(e) => set("designation", e.target.value)} placeholder="e.g. Director" /></Field>
              <Field label="Email" required><TextInput data-testid="onb-admin-email" type="email" value={f.email} onChange={(e) => set("email", e.target.value)} /></Field>
              <Field label="Mobile"><TextInput value={f.mobile} onChange={(e) => set("mobile", e.target.value)} maxLength={10} /></Field>
              <Field label="Username" required hint="You'll sign in with this"><TextInput data-testid="onb-admin-username" value={f.username} onChange={(e) => set("username", e.target.value.toLowerCase())} /></Field>
              <div />
              <Field label="Password" required hint="Minimum 8 characters">
                <div className="relative">
                  <TextInput data-testid="onb-admin-password" type={showPw ? "text" : "password"} value={f.password} onChange={(e) => set("password", e.target.value)} />
                  <button type="button" onClick={() => setShowPw(!showPw)} className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-700">
                    {showPw ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  </button>
                </div>
              </Field>
              <Field label="Confirm password" required><TextInput data-testid="onb-admin-confirm" type={showPw ? "text" : "password"} value={f.confirm_password} onChange={(e) => set("confirm_password", e.target.value)} /></Field>
              <div className="sm:col-span-2 flex items-start gap-2.5 border-t border-slate-100 pt-5">
                <Checkbox id="terms" data-testid="onb-terms" checked={f.terms} onCheckedChange={(v) => set("terms", !!v)} className="mt-0.5 rounded-none" />
                <label htmlFor="terms" className="text-sm text-slate-600">
                  I confirm I'm authorised to create this workspace and accept FleetFlow's terms of use and privacy practices. This account becomes the <strong>Organisation Super Admin</strong>.
                </label>
              </div>
            </div>
          )}

          {step === 4 && (
            <div className="space-y-8">
              <div>
                <p className="mb-3 text-xs font-bold uppercase tracking-[0.14em] text-slate-500">Operational preferences <span className="font-normal normal-case text-slate-400">(editable later in settings)</span></p>
                <div className="grid gap-2.5 sm:grid-cols-2">
                  {PREFERENCES.map(([k, label]) => (
                    <label key={k} className="flex cursor-pointer items-center gap-2.5 border border-slate-200 bg-white px-4 py-3 text-sm font-medium text-slate-700 hover:border-slate-400">
                      <Checkbox data-testid={`onb-pref-${k}`} checked={!!f.preferences[k]} onCheckedChange={(v) => set("preferences", { ...f.preferences, [k]: !!v })} className="rounded-none" />
                      {label}
                    </label>
                  ))}
                </div>
              </div>
              <div>
                <p className="mb-3 text-xs font-bold uppercase tracking-[0.14em] text-slate-500">Compliance documents to track</p>
                <div className="flex flex-wrap gap-2">{COMPLIANCE_DOCS.map((d) => chip(f.compliance_docs, d, "compliance_docs"))}</div>
              </div>
              <Field label="Remind me before expiry">
                <Select value={String(f.reminder_days)} onValueChange={(v) => set("reminder_days", Number(v))}>
                  <SelectTrigger data-testid="onb-reminder-days" className="w-48 rounded-none"><SelectValue /></SelectTrigger>
                  <SelectContent>{REMINDER_OPTIONS.map((d) => <SelectItem key={d} value={String(d)}>{d} days before</SelectItem>)}</SelectContent>
                </Select>
              </Field>
            </div>
          )}

          {step === 5 && (
            <div className="space-y-6" data-testid="onb-review">
              <p className="text-sm text-slate-500">Review everything before we create your workspace. Use <em>Previous</em> to edit any section.</p>
              {[
                ["Account type", [["Organisation type", f.org_type], ["Fleet ownership", f.fleet_ownership], ["Fleet size", f.fleet_size || "—"], ["Categories", f.categories.join(", ") || "—"]]],
                ["Organisation", [["Legal name", f.legal_name], ["Trade name", f.trade_name || f.legal_name], ["GSTIN", f.gstin || "—"], ["PAN", f.pan || "—"], ["City / State", [f.city, f.state].filter(Boolean).join(", ") || "—"]]],
                ["Administrator", [["Name", f.full_name], ["Email", f.email], ["Username", f.username], ["Role", "Organisation Super Admin"]]],
                ["Setup", [["First branch", `${f.branch_name} (${f.branch_code})`], ["Documents tracked", f.compliance_docs.join(", ")], ["Reminders", `${f.reminder_days} days before expiry`]]],
              ].map(([title, rows]) => (
                <div key={title} className="border border-slate-200">
                  <p className="border-b border-slate-200 bg-slate-50 px-4 py-2 text-xs font-bold uppercase tracking-[0.12em] text-slate-500">{title}</p>
                  <dl className="divide-y divide-slate-100">
                    {rows.map(([k, v]) => (
                      <div key={k} className="flex justify-between gap-6 px-4 py-2.5 text-sm">
                        <dt className="text-slate-500">{k}</dt><dd className="text-right font-semibold text-slate-900">{v}</dd>
                      </div>
                    ))}
                  </dl>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Nav buttons */}
        <div className="mt-6 flex items-center justify-between">
          <Button variant="outline" onClick={() => (step === 0 ? navigate("/") : setStep(step - 1))} data-testid="onb-prev-btn"
            className="rounded-none border-slate-300 px-6">
            <ArrowLeft className="mr-2 h-4 w-4" /> {step === 0 ? "Back to home" : "Previous"}
          </Button>
          {step < 5 ? (
            <Button onClick={next} data-testid="onb-next-btn" className="rounded-none bg-slate-900 px-8 text-white hover:bg-slate-800">
              Next <ArrowRight className="ml-2 h-4 w-4" />
            </Button>
          ) : (
            <Button onClick={submit} disabled={loading} data-testid="onb-submit-btn" className="rounded-none bg-amber-400 px-8 font-bold text-slate-950 hover:bg-amber-300">
              {loading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Check className="mr-2 h-4 w-4" />}
              {loading ? "Creating workspace…" : "Create my workspace"}
            </Button>
          )}
        </div>
      </main>
    </div>
  );
}
