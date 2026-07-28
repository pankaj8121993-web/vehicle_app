import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { BrandMark } from "@/pages/Landing";
import { toast } from "sonner";
import api from "@/lib/api";
import {
  ShieldCheck, Crown, Truck, ClipboardList, Wrench, Car,
  Calculator, FileSearch, ArrowLeft, ArrowRight, Loader2,
} from "lucide-react";

const ROLE_CARDS = [
  { role: "owner", label: "Owner / Management", icon: Crown, text: "Dashboards, approvals and organisation-wide visibility." },
  { role: "org_admin", label: "Organisation Super Admin", icon: ShieldCheck, text: "Full workspace control — users, settings, everything." },
  { role: "fleet_manager", label: "Fleet Manager", icon: Truck, text: "Fleet health, tickets, compliance and driver management." },
  { role: "operations", label: "Operations User", icon: ClipboardList, text: "Day-to-day trips, fuel and operational data entry." },
  { role: "maintenance", label: "Maintenance Manager", icon: Wrench, text: "Services, repairs, tyres and vendor jobs." },
  { role: "driver", label: "Driver", icon: Car, text: "Mobile home with quick actions for trips and fuel." },
  { role: "accounts", label: "Accounts User", icon: Calculator, text: "Expenses, budgets, FASTag and payment records." },
  { role: "viewer", label: "Auditor / Viewer", icon: FileSearch, text: "Read-only access to every module and report." },
];

export default function DemoEntry() {
  const navigate = useNavigate();
  const { enterDemo } = useAuth();
  const [selected, setSelected] = useState("owner");
  const [loading, setLoading] = useState(false);
  const [roles, setRoles] = useState([]);
  const [rolesLoading, setRolesLoading] = useState(true);
  const [rolesError, setRolesError] = useState("");

  const loadRoles = async () => {
    setRolesLoading(true);
    setRolesError("");
    try {
      const response = await api.get("/demo/roles");
      const available = new Set(response.data.map((item) => item.role));
      setRoles(ROLE_CARDS.filter((item) => available.has(item.role)));
    } catch {
      setRolesError("Demo roles could not be loaded.");
    } finally {
      setRolesLoading(false);
    }
  };

  useEffect(() => { loadRoles(); }, []);

  const enter = async () => {
    setLoading(true);
    try {
      const u = await enterDemo(selected);
      toast.success(`Welcome to the FleetFlow demo, ${u.full_name}`);
      navigate("/dashboard", { replace: true });
    } catch (err) {
      toast.error(err?.response?.data?.detail ? String(err.response.data.detail) : "Could not start the demo. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-300" data-testid="demo-entry-page">
      <header className="border-b border-white/10">
        <div className="mx-auto flex h-16 max-w-5xl items-center justify-between px-5">
          <Link to="/"><BrandMark dark /></Link>
          <Link to="/" className="flex items-center gap-1.5 text-sm font-semibold text-slate-400 hover:text-white" data-testid="demo-back-link">
            <ArrowLeft className="h-4 w-4" /> Back to home
          </Link>
        </div>
      </header>

      <main className="mx-auto max-w-5xl px-5 py-14">
        <p className="text-[11px] font-bold uppercase tracking-[0.22em] text-amber-400">Demo Environment</p>
        <h1 className="mt-2 font-heading text-3xl font-black tracking-tighter text-white sm:text-4xl">Explore FleetFlow as any role</h1>
        <p className="mt-3 max-w-xl text-sm leading-relaxed text-slate-400">
          The demo workspace is loaded with a realistic sample fleet — vehicles, drivers, 90 days of trips and fuel,
          service tickets, compliance documents and expenses. Pick a role to see FleetFlow through their eyes.
          Changes stay inside the demo and reset periodically.
        </p>

        {rolesLoading && (
          <div className="mt-10 flex items-center gap-2 text-sm text-slate-400" role="status">
            <Loader2 className="h-4 w-4 animate-spin" /> Loading demo roles…
          </div>
        )}
        {rolesError && (
          <div className="mt-10 text-sm text-rose-300" role="alert">
            {rolesError}{" "}
            <button className="font-bold underline" onClick={loadRoles}>Retry</button>
          </div>
        )}
        <div className="mt-10 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {roles.map((r) => (
            <button
              key={r.role}
              disabled={loading}
              onClick={() => setSelected(r.role)}
              data-testid={`demo-role-${r.role}`}
              className={`group border p-5 text-left transition-all ${
                selected === r.role
                  ? "border-amber-400 bg-amber-400/10"
                  : "border-white/10 bg-slate-900/40 hover:border-white/30"
              }`}
            >
              <r.icon className={`h-6 w-6 ${selected === r.role ? "text-amber-400" : "text-slate-400 group-hover:text-white"}`} strokeWidth={1.8} />
              <p className={`mt-3 text-sm font-bold ${selected === r.role ? "text-white" : "text-slate-200"}`}>{r.label}</p>
              <p className="mt-1.5 text-xs leading-relaxed text-slate-400">{r.text}</p>
            </button>
          ))}
        </div>

        <div className="mt-10 flex flex-wrap items-center gap-4">
          <Button onClick={enter} disabled={loading || rolesLoading || !!rolesError} data-testid="enter-demo-btn"
            className="group rounded-none bg-amber-400 px-8 py-6 text-sm font-bold text-slate-950 hover:bg-amber-300">
            {loading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
            {loading ? "Preparing demo…" : "Enter Demo"}
            {!loading && <ArrowRight className="ml-2 h-4 w-4 transition-transform group-hover:translate-x-1" />}
          </Button>
          <p className="text-xs text-slate-500">No sign-up needed · Demo data resets automatically</p>
        </div>
      </main>
    </div>
  );
}
