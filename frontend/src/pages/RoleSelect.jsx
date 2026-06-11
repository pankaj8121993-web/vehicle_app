import { useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { Truck, ClipboardEdit, BarChart3, ShieldCheck, ArrowRight } from "lucide-react";

const ROLE_CARDS = [
  { role: "driver", label: "Driver", icon: Truck, desc: "Field operations", rights: ["Add trips & fuel entries", "Report breakdowns", "View fleet data (read-only)"] },
  { role: "data_entry", label: "Data Entry Operator", icon: ClipboardEdit, desc: "Records & documentation", rights: ["Add & edit all records", "Upload documents & invoices", "No delete rights"] },
  { role: "management", label: "Management", icon: BarChart3, desc: "Oversight & decisions", rights: ["Dashboards & reports", "Approve major repairs", "Add & edit records"] },
  { role: "admin", label: "Admin", icon: ShieldCheck, desc: "Full system control", rights: ["Everything in Management", "Delete any record", "Data cleanup"] },
];

export default function RoleSelect() {
  const navigate = useNavigate();
  const { selectRole } = useAuth();

  const pick = (role) => {
    selectRole(role);
    navigate("/", { replace: true });
  };

  return (
    <div className="flex min-h-screen flex-col bg-slate-900 px-6 py-12" data-testid="role-select-page">
      <div className="mx-auto w-full max-w-5xl">
        <p className="text-xs font-bold uppercase tracking-[0.2em] text-slate-500">Rajguru Foods</p>
        <h1 className="mt-2 font-heading text-4xl font-black tracking-tighter text-white sm:text-5xl">Fleet Command Center</h1>
        <p className="mt-3 text-base text-slate-400">Select your profile to enter. Each profile has different access, edit and modify rights.</p>

        <div className="mt-10 grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {ROLE_CARDS.map((r) => (
            <button
              key={r.role}
              data-testid={`role-card-${r.role}`}
              onClick={() => pick(r.role)}
              className="group flex flex-col border border-slate-700 bg-slate-800 p-6 text-left transition-colors hover:border-white hover:bg-slate-800/60"
            >
              <r.icon className="h-7 w-7 text-slate-400 transition-colors group-hover:text-white" strokeWidth={2} />
              <p className="mt-4 font-heading text-lg font-black text-white">{r.label}</p>
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">{r.desc}</p>
              <ul className="mt-4 flex-1 space-y-1.5">
                {r.rights.map((right) => (
                  <li key={right} className="text-sm text-slate-400">· {right}</li>
                ))}
              </ul>
              <span className="mt-5 inline-flex items-center gap-1.5 text-sm font-semibold text-slate-300 group-hover:text-white">
                Enter <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-1" />
              </span>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
