import { useState, useEffect, useMemo, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { canEdit, canDelete } from "@/lib/permissions";
import { fmtDate } from "@/lib/format";
import { Loader2, ChevronLeft, ChevronRight, Plus, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { toast } from "sonner";

const TYPE_COLORS = {
  doc_expiry: "bg-red-100 text-red-800 border-red-200",
  license_expiry: "bg-red-100 text-red-800 border-red-200",
  service_due: "bg-amber-100 text-amber-800 border-amber-200",
  greasing_due: "bg-amber-100 text-amber-800 border-amber-200",
  downtime_open: "bg-orange-100 text-orange-800 border-orange-200",
  ticket_open: "bg-yellow-100 text-yellow-800 border-yellow-200",
  accident: "bg-rose-100 text-rose-800 border-rose-200",
  vehicle_disposed: "bg-slate-100 text-slate-500 border-slate-200",
  driver_exit: "bg-slate-100 text-slate-500 border-slate-200",
  custom: "bg-blue-100 text-blue-800 border-blue-200",
};

const monthStart = (y, m) => new Date(y, m, 1);
const monthEnd = (y, m) => new Date(y, m + 1, 0);
const iso = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;

export default function CalendarPage() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const today = new Date();
  const [year, setYear] = useState(today.getFullYear());
  const [month, setMonth] = useState(today.getMonth());
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ title: "", date: "", time: "", responsible_person: "", notes: "", recurrence: "none" });

  const load = useCallback(async () => {
    setLoading(true);
    const start = iso(monthStart(year, month));
    const end = iso(monthEnd(year, month));
    try {
      const r = await api.get("/calendar", { params: { start, end } });
      setEvents(r.data.events || []);
    } finally { setLoading(false); }
  }, [year, month]);

  useEffect(() => { load(); }, [load]);

  const eventsByDate = useMemo(() => {
    const out = {};
    for (const e of events) (out[e.date] = out[e.date] || []).push(e);
    return out;
  }, [events]);

  const grid = useMemo(() => {
    const start = monthStart(year, month);
    const end = monthEnd(year, month);
    const firstDay = (start.getDay() + 6) % 7; // Monday-first
    const days = [];
    for (let i = 0; i < firstDay; i++) days.push(null);
    for (let d = 1; d <= end.getDate(); d++) days.push(new Date(year, month, d));
    while (days.length % 7) days.push(null);
    return days;
  }, [year, month]);

  const prev = () => { const m = month - 1; if (m < 0) { setMonth(11); setYear(year - 1); } else setMonth(m); };
  const next = () => { const m = month + 1; if (m > 11) { setMonth(0); setYear(year + 1); } else setMonth(m); };

  const openAdd = (d) => {
    setForm({ title: "", date: d ? iso(d) : "", time: "", responsible_person: "", notes: "", recurrence: "none" });
    setOpen(true);
  };

  const saveEvent = async (e) => {
    e.preventDefault();
    try {
      await api.post("/calendar/events", {
        title: form.title, date: form.date,
        time: form.time || null,
        responsible_person: form.responsible_person || null,
        notes: form.notes || null,
        recurrence: form.recurrence === "none" ? null : form.recurrence,
      });
      toast.success("Event added");
      setOpen(false);
      await load();
    } catch (err) { toast.error(err?.response?.data?.detail || "Failed"); }
  };

  const onEventClick = (e) => {
    if (e.vehicle_id) navigate(`/vehicles/${e.vehicle_id}`);
    else if (e.driver_id) navigate(`/drivers/${e.driver_id}`);
  };

  const deleteCustom = async (e) => {
    if (!window.confirm(`Delete "${e.title}"?`)) return;
    try {
      await api.delete(`/calendar/events/${e.source_id}`);
      toast.success("Event deleted");
      await load();
    } catch (err) { toast.error(err?.response?.data?.detail || "Failed"); }
  };

  const monthLabel = monthStart(year, month).toLocaleDateString("en-IN", { month: "long", year: "numeric" });
  const editable = canEdit(user?.role);

  return (
    <div data-testid="calendar-page">
      <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="font-heading text-3xl font-black tracking-tighter text-slate-900 md:text-4xl">Fleet Calendar</h1>
          <p className="mt-1 text-sm text-slate-500">Document, license, service, greasing and custom events on a single calendar.</p>
        </div>
        <div className="flex items-end gap-2">
          <Button variant="outline" size="sm" onClick={prev} className="rounded-none" data-testid="calendar-prev"><ChevronLeft className="h-4 w-4" /></Button>
          <div className="border border-slate-200 bg-white px-4 py-1.5">
            <p className="font-heading text-sm font-bold tracking-tight text-slate-900" data-testid="calendar-month-label">{monthLabel}</p>
          </div>
          <Button variant="outline" size="sm" onClick={next} className="rounded-none" data-testid="calendar-next"><ChevronRight className="h-4 w-4" /></Button>
          {editable && (
            <Button onClick={() => openAdd(null)} className="rounded-none bg-slate-900 text-white hover:bg-slate-800" data-testid="calendar-add-event">
              <Plus className="mr-1 h-4 w-4" /> Event
            </Button>
          )}
        </div>
      </div>

      <div className="border border-slate-200 bg-white">
        <div className="grid grid-cols-7 border-b border-slate-200 bg-slate-50">
          {["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].map((d) => (
            <p key={d} className="border-r border-slate-200 px-2 py-2 text-[10px] font-bold uppercase tracking-wide text-slate-500 last:border-r-0">{d}</p>
          ))}
        </div>
        {loading ? (
          <div className="flex h-64 items-center justify-center"><Loader2 className="h-5 w-5 animate-spin text-slate-400" /></div>
        ) : (
          <div className="grid grid-cols-7">
            {grid.map((d, i) => {
              if (!d) return <div key={i} className="min-h-[110px] border-b border-r border-slate-100 bg-slate-50/40" />;
              const k = iso(d);
              const dayEvents = eventsByDate[k] || [];
              const isToday = iso(today) === k;
              return (
                <div key={i} data-testid={`calendar-day-${k}`} className={`min-h-[110px] border-b border-r border-slate-100 p-1.5 ${isToday ? "bg-blue-50/40" : "bg-white"}`}>
                  <div className="flex items-center justify-between">
                    <p className={`text-xs font-semibold ${isToday ? "text-blue-700" : "text-slate-500"}`}>{d.getDate()}</p>
                    {editable && <button onClick={() => openAdd(d)} className="opacity-0 hover:opacity-100 group-hover:opacity-100 text-slate-400 hover:text-slate-700" data-testid={`calendar-add-${k}`}><Plus className="h-3 w-3" /></button>}
                  </div>
                  <div className="mt-1 space-y-0.5">
                    {dayEvents.slice(0, 4).map((e) => (
                      <div key={e.id + e.date} className={`flex items-center gap-1 truncate border-l-2 px-1.5 py-0.5 text-[10px] ${TYPE_COLORS[e.type] || "bg-slate-100"}`} title={e.title} data-testid={`calendar-event-${e.id}`}>
                        <button onClick={() => onEventClick(e)} className="min-w-0 flex-1 truncate text-left hover:underline">{e.title}</button>
                        {!e.is_auto && canDelete(user?.role) && <button onClick={() => deleteCustom(e)} className="text-slate-500 hover:text-red-600"><Trash2 className="h-2.5 w-2.5" /></button>}
                      </div>
                    ))}
                    {dayEvents.length > 4 && <p className="px-1 text-[10px] font-semibold text-slate-500">+{dayEvents.length - 4} more</p>}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="rounded-none" data-testid="calendar-event-dialog">
          <DialogHeader>
            <DialogTitle className="font-heading text-xl font-black tracking-tighter">New Custom Event</DialogTitle>
            <DialogDescription>One-off or recurring event for the fleet calendar.</DialogDescription>
          </DialogHeader>
          <form onSubmit={saveEvent} className="space-y-3">
            <div className="space-y-1.5">
              <Label className="text-xs font-bold uppercase tracking-[0.08em] text-slate-700">Title</Label>
              <Input required value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} className="rounded-none" data-testid="calendar-form-title" />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label className="text-xs font-bold uppercase tracking-[0.08em] text-slate-700">Date</Label>
                <Input required type="date" value={form.date} onChange={(e) => setForm({ ...form, date: e.target.value })} className="rounded-none" data-testid="calendar-form-date" />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs font-bold uppercase tracking-[0.08em] text-slate-700">Time (optional)</Label>
                <Input type="time" value={form.time} onChange={(e) => setForm({ ...form, time: e.target.value })} className="rounded-none" />
              </div>
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs font-bold uppercase tracking-[0.08em] text-slate-700">Responsible Person</Label>
              <Input value={form.responsible_person} onChange={(e) => setForm({ ...form, responsible_person: e.target.value })} className="rounded-none" />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs font-bold uppercase tracking-[0.08em] text-slate-700">Recurrence</Label>
              <Select value={form.recurrence} onValueChange={(v) => setForm({ ...form, recurrence: v })}>
                <SelectTrigger className="rounded-none" data-testid="calendar-form-recurrence"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">One-off</SelectItem>
                  <SelectItem value="weekly">Weekly</SelectItem>
                  <SelectItem value="monthly">Monthly</SelectItem>
                  <SelectItem value="yearly">Yearly</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs font-bold uppercase tracking-[0.08em] text-slate-700">Notes</Label>
              <Textarea rows={2} value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} className="rounded-none" />
            </div>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setOpen(false)} className="rounded-none">Cancel</Button>
              <Button type="submit" className="rounded-none bg-slate-900 text-white hover:bg-slate-800" data-testid="calendar-form-submit">Save Event</Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}
