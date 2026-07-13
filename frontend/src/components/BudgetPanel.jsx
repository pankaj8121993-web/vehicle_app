import { useState, useEffect, useCallback } from "react";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { fmtINR, roleTier } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { toast } from "sonner";
import { Loader2, Plus, Trash2 } from "lucide-react";

const monthLabel = (m) => {
  const [y, mo] = m.split("-");
  return new Date(Number(y), Number(mo) - 1, 1).toLocaleDateString("en-IN", { month: "long", year: "numeric" });
};

export const BudgetPanel = () => {
  const { user } = useAuth();
  const canEdit = !["driver", "viewer"].includes(roleTier(user?.role));
  const canDelete = ["management", "admin"].includes(roleTier(user?.role));
  const [month, setMonth] = useState(new Date().toISOString().slice(0, 7));
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ category: "", amount: "" });
  const [saving, setSaving] = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    api.get("/budgets/status", { params: { month } })
      .then((r) => setData(r.data))
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, [month]);

  useEffect(() => { load(); }, [load]);

  const save = async () => {
    if (!form.category || !form.amount) { toast.error("Select a category and enter an amount"); return; }
    setSaving(true);
    try {
      await api.post("/budgets", { category: form.category, month, amount: parseFloat(form.amount) });
      toast.success("Budget saved");
      setOpen(false);
      setForm({ category: "", amount: "" });
      load();
    } catch (err) {
      toast.error(err?.response?.data?.detail ? String(err.response.data.detail) : "Failed to save budget");
    } finally {
      setSaving(false);
    }
  };

  const remove = async (id) => {
    try {
      await api.delete(`/budgets/${id}`);
      toast.success("Budget removed");
      load();
    } catch {
      toast.error("Failed to remove budget");
    }
  };

  return (
    <div data-testid="budget-panel">
      <div className="mb-5 flex flex-wrap items-center gap-3">
        <Input type="month" value={month} onChange={(e) => setMonth(e.target.value)} data-testid="budget-month-input" className="w-44 rounded-none" />
        {canEdit && (
          <Button onClick={() => setOpen(true)} data-testid="budget-add-btn" className="rounded-none bg-slate-900 text-white hover:bg-slate-800">
            <Plus className="mr-1.5 h-4 w-4" /> Set Budget
          </Button>
        )}
      </div>

      {loading ? (
        <div className="flex h-32 items-center justify-center"><Loader2 className="h-5 w-5 animate-spin text-slate-400" /></div>
      ) : !data ? (
        <p className="text-sm text-slate-400">Could not load budgets.</p>
      ) : (
        <>
          <div className="overflow-x-auto border border-slate-200 bg-white">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-200 bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
                  <th className="px-4 py-2.5">Category</th>
                  <th className="px-4 py-2.5 text-right">Budget</th>
                  <th className="px-4 py-2.5 text-right">Actual</th>
                  <th className="px-4 py-2.5 text-right">Variance</th>
                  <th className="px-4 py-2.5 w-52">Utilisation</th>
                  {canDelete && <th className="px-4 py-2.5 w-12" />}
                </tr>
              </thead>
              <tbody>
                {data.rows.length === 0 && (
                  <tr><td colSpan={6} className="px-4 py-10 text-center text-sm text-slate-400">
                    No budgets set for {monthLabel(month)}. {canEdit ? "Use “Set Budget” to define spending limits per category." : ""}
                  </td></tr>
                )}
                {data.rows.map((r) => {
                  const pct = r.budget ? Math.min((r.actual / r.budget) * 100, 100) : 0;
                  return (
                    <tr key={r.id} className="border-b border-slate-100 last:border-0" data-testid={`budget-row-${r.category}`}>
                      <td className="px-4 py-3 font-semibold text-slate-900">{r.category}</td>
                      <td className="px-4 py-3 text-right font-mono">{fmtINR(r.budget)}</td>
                      <td className="px-4 py-3 text-right font-mono">{fmtINR(r.actual)}</td>
                      <td className={`px-4 py-3 text-right font-mono ${r.over_budget ? "text-red-600" : "text-green-700"}`}>
                        {r.over_budget ? "-" : "+"}{fmtINR(Math.abs(r.variance))}
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          <div className="h-1.5 flex-1 bg-slate-100">
                            <div className={`h-1.5 ${r.over_budget ? "bg-red-500" : "bg-slate-900"}`} style={{ width: `${pct}%` }} />
                          </div>
                          <span className={`w-12 text-right font-mono text-xs ${r.over_budget ? "font-bold text-red-600" : "text-slate-500"}`}>
                            {r.budget ? Math.round((r.actual / r.budget) * 100) : 0}%
                          </span>
                        </div>
                      </td>
                      {canDelete && (
                        <td className="px-4 py-3 text-right">
                          <button onClick={() => remove(r.id)} data-testid={`budget-delete-${r.category}`} className="text-slate-300 hover:text-red-600" aria-label="Delete budget">
                            <Trash2 className="h-4 w-4" />
                          </button>
                        </td>
                      )}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {data.unbudgeted.length > 0 && (
            <div className="mt-4 border border-amber-200 bg-amber-50 p-4">
              <p className="mb-2 text-xs font-bold uppercase tracking-wide text-amber-800">Spend without a budget this month</p>
              <div className="flex flex-wrap gap-2">
                {data.unbudgeted.map((u) => (
                  <span key={u.category} className="border border-amber-300 bg-white px-2.5 py-1 text-xs font-semibold text-amber-900">
                    {u.category} · {fmtINR(u.actual)}
                  </span>
                ))}
              </div>
            </div>
          )}
        </>
      )}

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="rounded-none sm:max-w-sm">
          <DialogHeader><DialogTitle>Set Budget — {monthLabel(month)}</DialogTitle></DialogHeader>
          <div className="space-y-4">
            <div className="space-y-1.5">
              <Label className="text-xs font-semibold uppercase text-slate-500">Category</Label>
              <Select value={form.category} onValueChange={(v) => setForm({ ...form, category: v })}>
                <SelectTrigger data-testid="budget-category-select" className="rounded-none"><SelectValue placeholder="Select category" /></SelectTrigger>
                <SelectContent>
                  {(data?.categories || []).map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs font-semibold uppercase text-slate-500">Amount (₹)</Label>
              <Input type="number" min="1" data-testid="budget-amount-input" value={form.amount} onChange={(e) => setForm({ ...form, amount: e.target.value })} className="rounded-none" />
            </div>
            <Button onClick={save} disabled={saving} data-testid="budget-save-btn" className="w-full rounded-none bg-slate-900 text-white hover:bg-slate-800">
              {saving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null} Save Budget
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
};
