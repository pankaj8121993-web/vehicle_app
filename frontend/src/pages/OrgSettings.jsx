import { useState, useEffect, useCallback } from "react";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { roleTier } from "@/lib/format";
import { PageHeader } from "@/pages/ModulePages";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { toast } from "sonner";
import { Loader2, Plus, Building2, CheckCircle2, Circle } from "lucide-react";

const Field = ({ label, children }) => (
  <div className="space-y-1.5">
    <Label className="text-xs font-bold uppercase tracking-[0.08em] text-slate-600">{label}</Label>
    {children}
  </div>
);

export default function OrgSettings() {
  const { user } = useAuth();
  const canEdit = ["management", "admin"].includes(roleTier(user?.role)) && !user?.is_demo;
  const [org, setOrg] = useState(null);
  const [checklist, setChecklist] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({});
  const [branchOpen, setBranchOpen] = useState(false);
  const [branchForm, setBranchForm] = useState({ name: "", code: "", address: "", contact_person: "", phone: "" });

  const load = useCallback(() => {
    setLoading(true);
    Promise.all([api.get("/org"), api.get("/onboarding/checklist")])
      .then(([o, c]) => {
        setOrg(o.data);
        setForm({
          trade_name: o.data.trade_name || "", industry: o.data.industry || "",
          gstin: o.data.gstin || "", pan: o.data.pan || "", email: o.data.email || "",
          phone: o.data.phone || "", website: o.data.website || "",
          city: o.data.city || "", state: o.data.state || "", reminder_days: o.data.reminder_days || 30,
        });
        setChecklist(c.data);
      })
      .catch(() => toast.error("Could not load organisation settings"))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(); }, [load]);

  const save = async () => {
    setSaving(true);
    try {
      await api.put("/org", { ...form, reminder_days: Number(form.reminder_days) || 30 });
      toast.success("Organisation profile updated");
      load();
    } catch (err) {
      toast.error(err?.response?.data?.detail ? String(err.response.data.detail) : "Failed to save");
    } finally {
      setSaving(false);
    }
  };

  const addBranch = async () => {
    if (!branchForm.name.trim()) { toast.error("Branch name is required"); return; }
    try {
      await api.post("/branches", branchForm);
      toast.success("Branch added");
      setBranchOpen(false);
      setBranchForm({ name: "", code: "", address: "", contact_person: "", phone: "" });
      load();
    } catch (err) {
      toast.error(err?.response?.data?.detail ? String(err.response.data.detail) : "Failed to add branch");
    }
  };

  if (loading) return <div className="flex h-64 items-center justify-center"><Loader2 className="h-6 w-6 animate-spin text-slate-400" /></div>;
  if (!org) return <p className="text-sm text-slate-400">Organisation not found.</p>;

  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  return (
    <div data-testid="org-settings-page">
      <PageHeader title="Organisation Settings" subtitle={`${org.legal_name} · ${org.org_type} · Workspace created ${new Date(org.created_at).toLocaleDateString("en-IN")}`} />

      {checklist && checklist.completed < checklist.total && (
        <div className="mb-6 border border-slate-200 bg-white p-5" data-testid="setup-checklist">
          <div className="mb-3 flex items-center justify-between">
            <p className="text-xs font-bold uppercase tracking-[0.12em] text-slate-500">Workspace setup — {checklist.completed}/{checklist.total} complete</p>
            <div className="h-1.5 w-40 bg-slate-100"><div className="h-1.5 bg-amber-400" style={{ width: `${(checklist.completed / checklist.total) * 100}%` }} /></div>
          </div>
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
            {checklist.items.map((i) => (
              <div key={i.key} className="flex items-center gap-2 text-sm">
                {i.done ? <CheckCircle2 className="h-4 w-4 text-green-600" /> : <Circle className="h-4 w-4 text-slate-300" />}
                <span className={i.done ? "text-slate-400 line-through" : "text-slate-700"}>{i.label}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="border border-slate-200 bg-white p-6 lg:col-span-2">
          <p className="mb-5 text-xs font-bold uppercase tracking-[0.12em] text-slate-500">Profile</p>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Trade / display name"><Input data-testid="org-trade-name" value={form.trade_name} onChange={set("trade_name")} disabled={!canEdit} className="rounded-none" /></Field>
            <Field label="Industry"><Input value={form.industry} onChange={set("industry")} disabled={!canEdit} className="rounded-none" /></Field>
            <Field label="GSTIN"><Input value={form.gstin} onChange={set("gstin")} disabled={!canEdit} maxLength={15} className="rounded-none" /></Field>
            <Field label="PAN"><Input value={form.pan} onChange={set("pan")} disabled={!canEdit} maxLength={10} className="rounded-none" /></Field>
            <Field label="Email"><Input value={form.email} onChange={set("email")} disabled={!canEdit} className="rounded-none" /></Field>
            <Field label="Phone"><Input value={form.phone} onChange={set("phone")} disabled={!canEdit} className="rounded-none" /></Field>
            <Field label="City"><Input value={form.city} onChange={set("city")} disabled={!canEdit} className="rounded-none" /></Field>
            <Field label="State"><Input value={form.state} onChange={set("state")} disabled={!canEdit} className="rounded-none" /></Field>
            <Field label="Compliance reminder (days before expiry)"><Input type="number" min="1" max="180" value={form.reminder_days} onChange={set("reminder_days")} disabled={!canEdit} className="rounded-none" /></Field>
          </div>
          {canEdit && (
            <Button onClick={save} disabled={saving} data-testid="org-save-btn" className="mt-6 rounded-none bg-slate-900 text-white hover:bg-slate-800">
              {saving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null} Save Changes
            </Button>
          )}
          {user?.is_demo && <p className="mt-4 text-xs text-amber-700">Organisation settings are read-only in the demo environment.</p>}
        </div>

        <div className="border border-slate-200 bg-white p-6">
          <div className="mb-5 flex items-center justify-between">
            <p className="text-xs font-bold uppercase tracking-[0.12em] text-slate-500">Branches</p>
            {canEdit && (
              <Button size="sm" variant="outline" onClick={() => setBranchOpen(true)} data-testid="branch-add-btn" className="h-8 rounded-none">
                <Plus className="mr-1 h-3.5 w-3.5" /> Add
              </Button>
            )}
          </div>
          <div className="space-y-3">
            {(org.branches || []).map((b) => (
              <div key={b.id} className="flex items-start gap-3 border border-slate-100 p-3" data-testid={`branch-${b.code || b.id}`}>
                <Building2 className="mt-0.5 h-4 w-4 text-slate-400" />
                <div>
                  <p className="text-sm font-bold text-slate-900">{b.name} {b.is_default && <span className="ml-1 bg-slate-900 px-1.5 py-0.5 text-[9px] font-bold uppercase text-white">Default</span>}</p>
                  <p className="text-xs text-slate-500">{[b.code, b.address, b.phone].filter(Boolean).join(" · ") || "No details"}</p>
                </div>
              </div>
            ))}
            {(org.branches || []).length === 0 && <p className="text-sm text-slate-400">No branches yet.</p>}
          </div>
        </div>
      </div>

      <Dialog open={branchOpen} onOpenChange={setBranchOpen}>
        <DialogContent className="rounded-none sm:max-w-md">
          <DialogHeader><DialogTitle>Add Branch</DialogTitle></DialogHeader>
          <div className="space-y-4">
            <Field label="Branch name"><Input data-testid="branch-name-input" value={branchForm.name} onChange={(e) => setBranchForm({ ...branchForm, name: e.target.value })} className="rounded-none" /></Field>
            <div className="grid grid-cols-2 gap-4">
              <Field label="Code"><Input value={branchForm.code} onChange={(e) => setBranchForm({ ...branchForm, code: e.target.value })} className="rounded-none" /></Field>
              <Field label="Phone"><Input value={branchForm.phone} onChange={(e) => setBranchForm({ ...branchForm, phone: e.target.value })} className="rounded-none" /></Field>
            </div>
            <Field label="Address"><Input value={branchForm.address} onChange={(e) => setBranchForm({ ...branchForm, address: e.target.value })} className="rounded-none" /></Field>
            <Field label="Contact person"><Input value={branchForm.contact_person} onChange={(e) => setBranchForm({ ...branchForm, contact_person: e.target.value })} className="rounded-none" /></Field>
            <Button onClick={addBranch} data-testid="branch-save-btn" className="w-full rounded-none bg-slate-900 text-white hover:bg-slate-800">Add Branch</Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
