import { useState, useMemo } from "react";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

const iso = (d) => d.toISOString().slice(0, 10);
const startOfDay = (d) => { const x = new Date(d); x.setHours(0, 0, 0, 0); return x; };

const PRESETS = [
  { value: "all", label: "All Time" },
  { value: "today", label: "Today" },
  { value: "yesterday", label: "Yesterday" },
  { value: "this_week", label: "This Week" },
  { value: "this_month", label: "This Month" },
  { value: "last_month", label: "Last Month" },
  { value: "this_quarter", label: "This Quarter" },
  { value: "this_year", label: "This Year" },
  { value: "custom", label: "Custom" },
];

function rangeFor(preset) {
  if (preset === "all") return { start: "", end: "" };
  const now = startOfDay(new Date());
  if (preset === "today") return { start: iso(now), end: iso(now) };
  if (preset === "yesterday") {
    const y = new Date(now); y.setDate(now.getDate() - 1);
    return { start: iso(y), end: iso(y) };
  }
  if (preset === "this_week") {
    // Week starts Monday
    const day = (now.getDay() + 6) % 7;
    const s = new Date(now); s.setDate(now.getDate() - day);
    return { start: iso(s), end: iso(now) };
  }
  if (preset === "this_month") {
    const s = new Date(now.getFullYear(), now.getMonth(), 1);
    return { start: iso(s), end: iso(now) };
  }
  if (preset === "last_month") {
    const s = new Date(now.getFullYear(), now.getMonth() - 1, 1);
    const e = new Date(now.getFullYear(), now.getMonth(), 0);
    return { start: iso(s), end: iso(e) };
  }
  if (preset === "this_quarter") {
    const q = Math.floor(now.getMonth() / 3);
    const s = new Date(now.getFullYear(), q * 3, 1);
    return { start: iso(s), end: iso(now) };
  }
  if (preset === "this_year") {
    const s = new Date(now.getFullYear(), 0, 1);
    return { start: iso(s), end: iso(now) };
  }
  return { start: "", end: "" };
}

/**
 * PeriodFilter — emits {start_date, end_date} to parent via onChange.
 * Use with CrudModule's fixedFilters or any list query.
 */
export const PeriodFilter = ({ value, onChange, testIdPrefix = "period" }) => {
  const [preset, setPreset] = useState(value?.preset || "all");
  const [custom, setCustom] = useState({ start: value?.start_date || "", end: value?.end_date || "" });

  const apply = (next, customRange) => {
    setPreset(next);
    if (next === "custom") {
      onChange({ start_date: customRange.start || "", end_date: customRange.end || "", preset: next });
      return;
    }
    const r = rangeFor(next);
    onChange({ start_date: r.start, end_date: r.end, preset: next });
  };

  const onPresetChange = (v) => apply(v, custom);
  const onCustomChange = (k, v) => {
    const next = { ...custom, [k]: v };
    setCustom(next);
    if (preset === "custom") onChange({ start_date: next.start || "", end_date: next.end || "", preset: "custom" });
  };

  const summary = useMemo(() => {
    if (preset === "all") return "All time";
    const r = preset === "custom" ? custom : rangeFor(preset);
    if (!r.start && !r.end) return "—";
    if (r.start === r.end) return r.start;
    return `${r.start || "…"} → ${r.end || "…"}`;
  }, [preset, custom]);

  return (
    <div className="mb-4 flex flex-wrap items-end gap-3 border border-slate-200 bg-white p-3" data-testid={`${testIdPrefix}-filter`}>
      <div className="space-y-1">
        <Label className="text-[10px] font-bold uppercase tracking-[0.08em] text-slate-500">Period</Label>
        <Select value={preset} onValueChange={onPresetChange}>
          <SelectTrigger data-testid={`${testIdPrefix}-preset`} className="w-44 rounded-none">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {PRESETS.map((p) => (
              <SelectItem key={p.value} value={p.value} data-testid={`${testIdPrefix}-option-${p.value}`}>{p.label}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      {preset === "custom" && (
        <>
          <div className="space-y-1">
            <Label className="text-[10px] font-bold uppercase tracking-[0.08em] text-slate-500">From</Label>
            <Input data-testid={`${testIdPrefix}-start`} type="date" value={custom.start} onChange={(e) => onCustomChange("start", e.target.value)} className="rounded-none" />
          </div>
          <div className="space-y-1">
            <Label className="text-[10px] font-bold uppercase tracking-[0.08em] text-slate-500">To</Label>
            <Input data-testid={`${testIdPrefix}-end`} type="date" value={custom.end} onChange={(e) => onCustomChange("end", e.target.value)} className="rounded-none" />
          </div>
        </>
      )}
      <p className="ml-auto self-center font-mono text-xs text-slate-500" data-testid={`${testIdPrefix}-summary`}>{summary}</p>
    </div>
  );
};

export default PeriodFilter;
