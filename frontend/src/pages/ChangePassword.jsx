import { useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Loader2, KeyRound, CheckCircle2 } from "lucide-react";

export default function ChangePassword({ forced = false }) {
  const navigate = useNavigate();
  const { refresh, logout } = useAuth();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [loading, setLoading] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState(null);

  const submit = async (e) => {
    e.preventDefault();
    setError(null);
    if (next.length < 6) { setError("New password must be at least 6 characters"); return; }
    if (next !== confirm) { setError("New passwords do not match"); return; }
    setLoading(true);
    try {
      await api.post("/auth/change-password", { current_password: current, new_password: next });
      setDone(true);
      await refresh();
      setTimeout(() => navigate(forced ? "/" : "/", { replace: true }), 1200);
    } catch (err) {
      setError(err?.response?.data?.detail || "Could not change password");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="mx-auto max-w-md py-12">
      <div className="border border-slate-200 bg-white p-8">
        <div className="mb-6 flex items-center gap-3">
          <div className="border border-slate-200 bg-slate-50 p-2.5"><KeyRound className="h-5 w-5 text-slate-700" /></div>
          <div>
            <h1 className="font-heading text-2xl font-black tracking-tighter text-slate-900">Change Password</h1>
            <p className="mt-0.5 text-xs text-slate-500">
              {forced ? "First-time login — please set a new password." : "Update your account password."}
            </p>
          </div>
        </div>

        {done ? (
          <div className="flex items-center gap-2 border-l-2 border-green-600 bg-green-50 px-3 py-3 text-sm text-green-800" data-testid="change-pw-success">
            <CheckCircle2 className="h-4 w-4" /> Password updated. Redirecting…
          </div>
        ) : (
          <form onSubmit={submit} className="space-y-4" data-testid="change-pw-form">
            <div className="space-y-1.5">
              <Label className="text-xs font-bold uppercase tracking-[0.08em] text-slate-700">Current Password</Label>
              <Input type="password" required value={current} onChange={(e) => setCurrent(e.target.value)} className="rounded-none" data-testid="change-pw-current" />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs font-bold uppercase tracking-[0.08em] text-slate-700">New Password</Label>
              <Input type="password" required minLength={6} value={next} onChange={(e) => setNext(e.target.value)} className="rounded-none" data-testid="change-pw-new" />
              <p className="font-mono text-[10px] uppercase tracking-wide text-slate-400">Minimum 6 characters</p>
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs font-bold uppercase tracking-[0.08em] text-slate-700">Confirm New Password</Label>
              <Input type="password" required value={confirm} onChange={(e) => setConfirm(e.target.value)} className="rounded-none" data-testid="change-pw-confirm" />
            </div>
            {error && <p className="border-l-2 border-red-500 bg-red-50 px-3 py-2 text-sm text-red-700" data-testid="change-pw-error">{error}</p>}
            <div className="flex gap-2 pt-2">
              <Button type="submit" disabled={loading} data-testid="change-pw-submit" className="rounded-none bg-slate-900 text-white hover:bg-slate-800">
                {loading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null} Update Password
              </Button>
              {forced && (
                <Button type="button" variant="outline" onClick={logout} className="rounded-none" data-testid="change-pw-logout">Sign Out</Button>
              )}
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
