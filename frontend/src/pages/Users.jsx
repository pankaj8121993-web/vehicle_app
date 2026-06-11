import { useState, useEffect } from "react";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { PageHeader } from "@/pages/ModulePages";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ROLE_LABELS } from "@/lib/format";
import { toast } from "sonner";
import { Loader2 } from "lucide-react";

export default function UsersPage() {
  const { user } = useAuth();
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const canEdit = user?.role === "management";

  const load = () => {
    api.get("/users").then((r) => setUsers(r.data)).catch(() => toast.error("Failed to load users")).finally(() => setLoading(false));
  };
  useEffect(load, []);

  const setRole = async (uid, role) => {
    try {
      await api.patch(`/users/${uid}/role`, { role });
      toast.success("Role updated");
      load();
    } catch (err) {
      toast.error(err.response?.data?.detail ? String(err.response.data.detail) : "Failed to update role");
    }
  };

  return (
    <div data-testid="users-page">
      <PageHeader title="Users & Roles" subtitle="Driver · Data Entry Operator · Fleet Manager · Management" />
      {loading ? (
        <div className="flex h-40 items-center justify-center"><Loader2 className="h-5 w-5 animate-spin text-slate-400" /></div>
      ) : (
        <div className="overflow-x-auto border border-slate-200 bg-white">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-200 bg-slate-50">
                <th className="px-3 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">Name</th>
                <th className="px-3 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">Email</th>
                <th className="px-3 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">Role</th>
              </tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.user_id} className="border-b border-slate-100 hover:bg-slate-50" data-testid={`user-row-${u.user_id}`}>
                  <td className="px-3 py-2.5 font-medium">{u.name}</td>
                  <td className="px-3 py-2.5 text-slate-600">{u.email}</td>
                  <td className="px-3 py-2.5">
                    {canEdit ? (
                      <Select value={u.role} onValueChange={(v) => setRole(u.user_id, v)}>
                        <SelectTrigger className="w-52 rounded-none" data-testid={`role-select-${u.user_id}`}><SelectValue /></SelectTrigger>
                        <SelectContent>
                          {Object.entries(ROLE_LABELS).map(([k, label]) => <SelectItem key={k} value={k}>{label}</SelectItem>)}
                        </SelectContent>
                      </Select>
                    ) : (
                      <span className="border border-slate-200 bg-slate-50 px-2 py-0.5 text-[11px] font-semibold uppercase">{ROLE_LABELS[u.role] || u.role}</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
