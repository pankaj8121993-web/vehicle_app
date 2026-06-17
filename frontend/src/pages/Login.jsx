import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Loader2, Truck, ShieldAlert } from "lucide-react";

export default function Login() {
  const navigate = useNavigate();
  const { login } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const u = await login(username.trim().toLowerCase(), password);
      if (u.must_change_password) navigate("/change-password", { replace: true });
      else navigate("/", { replace: true });
    } catch (err) {
      setError(err?.response?.data?.detail || "Login failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-50">
      <div className="grid min-h-screen lg:grid-cols-2">
        <aside className="hidden flex-col justify-between bg-slate-900 p-12 text-white lg:flex">
          <div className="flex items-center gap-3">
            <Truck className="h-8 w-8" />
            <div>
              <p className="font-heading text-2xl font-black tracking-tighter">RAJGURU FOODS</p>
              <p className="text-xs uppercase tracking-[0.2em] text-slate-400">Fleet Management</p>
            </div>
          </div>
          <div className="space-y-6">
            <h1 className="font-heading text-5xl font-black leading-[0.95] tracking-tighter">
              The complete<br />digital file<br />for every vehicle.
            </h1>
            <p className="max-w-md text-sm leading-relaxed text-slate-300">
              Documents, trips, fuel, maintenance, repairs, accidents, Fastag and expense — one operating system for the entire fleet.
            </p>
          </div>
          <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-slate-500">© 2026 Rajguru Foods · Pune</p>
        </aside>

        <main className="flex items-center justify-center p-6 sm:p-12">
          <form onSubmit={handleSubmit} className="w-full max-w-sm space-y-6" data-testid="login-form">
            <div>
              <p className="text-xs font-bold uppercase tracking-[0.18em] text-slate-500">Sign in to</p>
              <h2 className="font-heading text-3xl font-black tracking-tighter text-slate-900">Your Account</h2>
              <p className="mt-2 text-sm text-slate-500">Use your username and password to continue.</p>
            </div>

            <div className="space-y-4">
              <div className="space-y-1.5">
                <Label htmlFor="username" className="text-xs font-bold uppercase tracking-[0.08em] text-slate-700">Username</Label>
                <Input
                  id="username" type="text" autoComplete="username" required autoFocus
                  data-testid="login-username"
                  value={username} onChange={(e) => setUsername(e.target.value)}
                  className="rounded-none"
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="password" className="text-xs font-bold uppercase tracking-[0.08em] text-slate-700">Password</Label>
                <Input
                  id="password" type="password" autoComplete="current-password" required
                  data-testid="login-password"
                  value={password} onChange={(e) => setPassword(e.target.value)}
                  className="rounded-none"
                />
              </div>
            </div>

            {error && (
              <div className="flex items-center gap-2 border-l-2 border-red-500 bg-red-50 px-3 py-2 text-sm text-red-700" data-testid="login-error">
                <ShieldAlert className="h-4 w-4 flex-shrink-0" />
                <span>{error}</span>
              </div>
            )}

            <Button type="submit" disabled={loading} data-testid="login-submit"
              className="w-full rounded-none bg-slate-900 py-6 text-white hover:bg-slate-800">
              {loading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
              {loading ? "Signing in…" : "Sign In"}
            </Button>

            <p className="border-t border-slate-200 pt-4 text-xs text-slate-500">
              Forgot your password? Ask the system admin to reset it.
            </p>
          </form>
        </main>
      </div>
    </div>
  );
}
