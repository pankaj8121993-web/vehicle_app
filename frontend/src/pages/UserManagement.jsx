import { useState, useEffect } from "react";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from "@/components/ui/sheet";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { Plus, KeyRound, Trash2, Pencil, Loader2, CheckCircle2, Copy } from "lucide-react";
import { ROLE_LABELS } from "@/lib/format";
import { StatusBadge } from "@/components/StatusBadge";
import { toast } from "sonner";

const ROLES = ["driver", "data_entry", "management", "admin", "test"];

export default function UserManagement() {
  const { user: currentUser } = useAuth();
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(null);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ username: "", full_name: "", password: "", role: "data_entry", is_active: true });
  const [saving, setSaving] = useState(false);
  const [resetResult, setResetResult] = useState(null);
  const [deleteTarget, setDeleteTarget] = useState(null);

  const load = async () => {
    setLoading(true);
    try {
      const r = await api.get("/users");
      setUsers(r.data);
    } finally { setLoading(false); }
  };
  useEffect(() => { load(); }, []);

  const openAdd = () => {
    setEditing(null);
    setForm({ username: "", full_name: "", password: "", role: "data_entry", is_active: true });
    setOpen(true);
  };
  const openEdit = (u) => {
    setEditing(u);
    setForm({ username: u.username, full_name: u.full_name, password: "", role: u.role, is_active: u.is_active });
    setOpen(true);
  };

  const save = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      if (editing) {
        await api.put(`/users/${editing.id}`, {
          full_name: form.full_name, role: form.role, is_active: form.is_active,
        });
        toast.success("User updated");
      } else {
        await api.post("/users", form);
        toast.success(`User created. They must change their password on first login.`);
      }
      setOpen(false);
      await load();
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Failed");
    } finally { setSaving(false); }
  };

  const resetPwd = async (u) => {
    if (!window.confirm(`Reset password for ${u.username}? They'll be forced to change it on next login.`)) return;
    try {
      const r = await api.post(`/users/${u.id}/reset-password`);
      setResetResult(r.data);
    } catch (err) { toast.error(err?.response?.data?.detail || "Failed"); }
  };

  const doDelete = async () => {
    if (!deleteTarget) return;
    try {
      await api.delete(`/users/${deleteTarget.id}`);
      toast.success("User deleted");
      setDeleteTarget(null);
      await load();
    } catch (err) { toast.error(err?.response?.data?.detail || "Failed"); }
  };

  return (
    <div data-testid="users-page">
      <div className="mb-6 flex items-end justify-between">
        <div>
          <h1 className="font-heading text-3xl font-black tracking-tighter text-slate-900 md:text-4xl">User Management</h1>
          <p className="mt-1 text-sm text-slate-500">Create, edit, deactivate and reset passwords for system users.</p>
        </div>
        <Button onClick={openAdd} className="rounded-none bg-slate-900 text-white hover:bg-slate-800" data-testid="users-add-btn">
          <Plus className="mr-1 h-4 w-4" /> Add User
        </Button>
      </div>

      <div className="border border-slate-200 bg-white">
        {loading ? (
          <div className="flex h-32 items-center justify-center"><Loader2 className="h-5 w-5 animate-spin text-slate-400" /></div>
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-slate-50">
              <tr className="border-b border-slate-200">
                {["Username", "Name", "Role", "Status", "First Login?", ""].map((h) => (
                  <th key={h} className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.id} className="border-b border-slate-100" data-testid={`user-row-${u.username}`}>
                  <td className="px-4 py-2.5 font-mono font-semibold">{u.username}{u.id === currentUser?.id && <span className="ml-2 text-[10px] uppercase tracking-wide text-slate-400">(you)</span>}</td>
                  <td className="px-4 py-2.5">{u.full_name}</td>
                  <td className="px-4 py-2.5"><span className="border border-slate-200 bg-slate-50 px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide">{ROLE_LABELS[u.role] || u.role}</span></td>
                  <td className="px-4 py-2.5"><StatusBadge value={u.is_active ? "active" : "inactive"} /></td>
                  <td className="px-4 py-2.5">{u.must_change_password ? <span className="text-amber-700 text-xs font-semibold uppercase tracking-wide">Pending</span> : <span className="text-slate-400 text-xs">—</span>}</td>
                  <td className="px-4 py-2.5">
                    <div className="flex justify-end gap-1">
                      <Button variant="ghost" size="sm" className="h-7 w-7 p-0" onClick={() => openEdit(u)} data-testid={`user-edit-${u.username}`}><Pencil className="h-3.5 w-3.5 text-slate-500" /></Button>
                      <Button variant="ghost" size="sm" className="h-7 w-7 p-0" onClick={() => resetPwd(u)} data-testid={`user-reset-${u.username}`} disabled={u.id === currentUser?.id}><KeyRound className="h-3.5 w-3.5 text-amber-600" /></Button>
                      <Button variant="ghost" size="sm" className="h-7 w-7 p-0" onClick={() => setDeleteTarget(u)} data-testid={`user-delete-${u.username}`} disabled={u.id === currentUser?.id || u.username === "admin"}><Trash2 className="h-3.5 w-3.5 text-red-500" /></Button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Edit/Add sheet */}
      <Sheet open={open} onOpenChange={setOpen}>
        <SheetContent className="overflow-y-auto sm:max-w-md">
          <SheetHeader>
            <SheetTitle className="font-heading text-xl font-bold">{editing ? "Edit User" : "Add User"}</SheetTitle>
            <SheetDescription className="sr-only">User form</SheetDescription>
          </SheetHeader>
          <form onSubmit={save} className="mt-6 space-y-4">
            <div className="space-y-1.5">
              <Label className="text-xs font-bold uppercase tracking-[0.08em] text-slate-700">Username</Label>
              <Input required value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} disabled={!!editing} className="rounded-none" data-testid="user-form-username" />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs font-bold uppercase tracking-[0.08em] text-slate-700">Full Name</Label>
              <Input required value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} className="rounded-none" data-testid="user-form-fullname" />
            </div>
            {!editing && (
              <div className="space-y-1.5">
                <Label className="text-xs font-bold uppercase tracking-[0.08em] text-slate-700">Initial Password</Label>
                <Input required minLength={6} type="text" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} className="rounded-none" data-testid="user-form-password" />
                <p className="text-[10px] uppercase tracking-wide text-slate-400">User must change on first login</p>
              </div>
            )}
            <div className="space-y-1.5">
              <Label className="text-xs font-bold uppercase tracking-[0.08em] text-slate-700">Role</Label>
              <Select value={form.role} onValueChange={(v) => setForm({ ...form, role: v })}>
                <SelectTrigger className="rounded-none" data-testid="user-form-role"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {ROLES.map((r) => <SelectItem key={r} value={r}>{ROLE_LABELS[r]}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="flex items-center gap-2">
              <Switch checked={form.is_active} onCheckedChange={(c) => setForm({ ...form, is_active: c })} data-testid="user-form-active" />
              <Label className="text-xs font-bold uppercase tracking-[0.08em] text-slate-700">Active</Label>
            </div>
            <Button type="submit" disabled={saving} className="rounded-none bg-slate-900 text-white hover:bg-slate-800" data-testid="user-form-submit">
              {saving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
              {editing ? "Update" : "Create"}
            </Button>
          </form>
        </SheetContent>
      </Sheet>

      {/* Reset password result */}
      <Dialog open={!!resetResult} onOpenChange={(o) => !o && setResetResult(null)}>
        <DialogContent className="rounded-none" data-testid="reset-pw-result">
          <DialogHeader>
            <DialogTitle className="font-heading text-xl font-black tracking-tighter">Temporary Password</DialogTitle>
            <DialogDescription>Copy and share with the user. They must change on next login.</DialogDescription>
          </DialogHeader>
          <div className="my-4 border border-slate-200 bg-slate-50 p-4">
            <p className="text-[10px] font-bold uppercase tracking-wide text-slate-500">Username</p>
            <p className="font-mono text-lg font-semibold text-slate-900">{resetResult?.username}</p>
            <p className="mt-3 text-[10px] font-bold uppercase tracking-wide text-slate-500">Temporary Password</p>
            <div className="flex items-center justify-between gap-3">
              <p className="font-mono text-2xl font-black tracking-tight text-slate-900">{resetResult?.temporary_password}</p>
              <Button size="sm" variant="outline" className="rounded-none" onClick={() => {
                navigator.clipboard?.writeText(resetResult?.temporary_password || "");
                toast.success("Copied to clipboard");
              }}><Copy className="h-3.5 w-3.5" /></Button>
            </div>
          </div>
          <DialogFooter>
            <Button onClick={() => setResetResult(null)} className="rounded-none bg-slate-900 text-white hover:bg-slate-800">Done</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete confirm */}
      <Dialog open={!!deleteTarget} onOpenChange={(o) => !o && setDeleteTarget(null)}>
        <DialogContent className="rounded-none" data-testid="user-delete-confirm">
          <DialogHeader>
            <DialogTitle className="font-heading text-xl font-black tracking-tighter">Delete user?</DialogTitle>
            <DialogDescription>This deletes <span className="font-mono font-bold">{deleteTarget?.username}</span> and revokes all their sessions.</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteTarget(null)} className="rounded-none">Cancel</Button>
            <Button onClick={doDelete} className="rounded-none bg-red-600 text-white hover:bg-red-700" data-testid="user-delete-confirm-btn">Delete</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
