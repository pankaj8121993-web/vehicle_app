export const fmtINR = (n) => {
  if (n === null || n === undefined || isNaN(n)) return "—";
  return "₹" + Number(n).toLocaleString("en-IN", { maximumFractionDigits: 2 });
};

export const fmtNum = (n) => {
  if (n === null || n === undefined || n === "") return "—";
  return Number(n).toLocaleString("en-IN", { maximumFractionDigits: 2 });
};

export const fmtDate = (d) => {
  if (!d) return "—";
  try {
    const dt = new Date(d);
    return dt.toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" });
  } catch {
    return d;
  }
};

export const todayISO = () => new Date().toISOString().slice(0, 10);

export const STATUS_STYLES = {
  active: "bg-green-50 text-green-700 border-green-200",
  completed: "bg-green-50 text-green-700 border-green-200",
  closed: "bg-slate-100 text-slate-600 border-slate-200",
  valid: "bg-green-50 text-green-700 border-green-200",
  ongoing: "bg-blue-50 text-blue-700 border-blue-200",
  open: "bg-amber-50 text-amber-700 border-amber-200",
  reported: "bg-amber-50 text-amber-700 border-amber-200",
  approved: "bg-blue-50 text-blue-700 border-blue-200",
  in_repair: "bg-amber-50 text-amber-700 border-amber-200",
  under_repair: "bg-red-50 text-red-700 border-red-200",
  idle: "bg-slate-100 text-slate-600 border-slate-200",
  sold: "bg-slate-100 text-slate-500 border-slate-200",
  removed: "bg-slate-100 text-slate-500 border-slate-200",
  expired: "bg-red-50 text-red-700 border-red-200",
  minor: "bg-slate-100 text-slate-600 border-slate-200",
  major: "bg-red-50 text-red-700 border-red-200",
  toll: "bg-slate-100 text-slate-600 border-slate-200",
  recharge: "bg-green-50 text-green-700 border-green-200",
  puncture: "bg-amber-50 text-amber-700 border-amber-200",
  rotation: "bg-blue-50 text-blue-700 border-blue-200",
  retreading: "bg-blue-50 text-blue-700 border-blue-200",
  replacement: "bg-red-50 text-red-700 border-red-200",
  service: "bg-blue-50 text-blue-700 border-blue-200",
  breakdown: "bg-red-50 text-red-700 border-red-200",
  accident: "bg-red-50 text-red-700 border-red-200",
  compliance: "bg-amber-50 text-amber-700 border-amber-200",
};

export const ROLE_LABELS = {
  driver: "Driver",
  data_entry: "Data Entry Operator",
  fleet_manager: "Fleet Manager",
  management: "Management",
};
