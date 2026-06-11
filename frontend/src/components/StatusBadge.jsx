import { STATUS_STYLES, fmtDate } from "@/lib/format";

export const StatusBadge = ({ value }) => {
  if (!value) return <span className="text-slate-400">—</span>;
  const style = STATUS_STYLES[value] || "bg-slate-100 text-slate-600 border-slate-200";
  return (
    <span className={`inline-block border px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide ${style}`}>
      {String(value).replace(/_/g, " ")}
    </span>
  );
};

export const ExpiryBadge = ({ date }) => {
  if (!date) return <span className="text-slate-400">—</span>;
  const today = new Date().toISOString().slice(0, 10);
  const in30 = new Date(Date.now() + 30 * 86400000).toISOString().slice(0, 10);
  let style = "bg-green-50 text-green-700 border-green-200";
  if (date < today) style = "bg-red-50 text-red-700 border-red-200";
  else if (date <= in30) style = "bg-amber-50 text-amber-700 border-amber-200";
  return (
    <span className={`inline-block border px-2 py-0.5 text-[11px] font-semibold font-mono ${style}`}>
      {fmtDate(date)}
    </span>
  );
};
