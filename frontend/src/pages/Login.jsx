import { useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { BrandMark } from "@/pages/Landing";
import { Loader2, ShieldAlert, Eye, EyeOff, ArrowLeft, PlayCircle } from "lucide-react";

export default function Login() {
  const navigate = useNavigate();
  const location = useLocation();
  const { login } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPw, setShowPw] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const u = await login(username.trim().toLowerCase(), password);
      if (u.must_change_password) navigate("/change-password", { replace: true });
      else {
        const intended = location.state?.from;
        const destination = intended?.pathname?.startsWith("/") && intended.pathname !== "/login"
          ? `${intended.pathname}${intended.search || ""}`
          : "/dashboard";
        navigate(destination, { replace: true });
      }
    } catch (err) {
      const d = err?.response?.data?.detail;
      setError(typeof d === "string" ? d : "Login failed. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-50">
      <div className="grid min-h-screen lg:grid-cols-2">
        <aside className="hidden flex-col justify-between bg-slate-950 p-12 text-white lg:flex">
          <Link to="/" data-testid="login-brand-link"><BrandMark dark /></Link>
          <div className="space-y-6">
            <h1 className="font-heading text-5xl font-black leading-[0.98] tracking-tighter">
              Every Vehicle.<br />Every Journey.<br />
              <span className="text-amber-400">Completely Under Control.</span>
            </h1>
            <p className="max-w-md text-sm leading-relaxed text-slate-400">
              Vehicles, drivers, trips, fuel, maintenance, expenses, compliance, incidents,
              approvals and reporting — one intelligent platform for your entire fleet.
            </p>
          </div>
          <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-slate-400">© 2026 FleetFlow · Complete Fleet Operations Management</p>
        </aside>

        <main className="flex items-center justify-center p-6 sm:p-12">
          <form onSubmit={handleSubmit} className="w-full max-w-sm space-y-6" data-testid="login-form">
            <div className="lg:hidden"><Link to="/"><BrandMark /></Link></div>
            <div>
              <p className="text-xs font-bold uppercase tracking-[0.18em] text-slate-500">Welcome back</p>
              <h2 className="font-heading text-3xl font-black tracking-tighter text-slate-900">Sign in to FleetFlow</h2>
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
                <div className="relative">
                  <Input
                    id="password" type={showPw ? "text" : "password"} autoComplete="current-password" required
                    data-testid="login-password"
                    value={password} onChange={(e) => setPassword(e.target.value)}
                    className="rounded-none pr-10"
                  />
                  <button type="button" data-testid="login-toggle-password" onClick={() => setShowPw(!showPw)}
                    className="absolute right-1.5 top-1/2 grid h-7 w-7 -translate-y-1/2 place-items-center text-slate-500 hover:text-slate-700" aria-label="Toggle password visibility">
                    {showPw ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  </button>
                </div>
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

            <div className="space-y-3 border-t border-slate-200 pt-4 text-sm">
              <p className="text-slate-500">
                New to FleetFlow?{" "}
                <Link to="/get-started" data-testid="login-get-started-link" className="font-semibold text-slate-900 underline underline-offset-4 hover:text-amber-600">Create your workspace</Link>
              </p>
              <p className="flex items-center gap-1.5 text-slate-500">
                <PlayCircle className="h-4 w-4" /> Want a look around first?{" "}
                <Link to="/demo" data-testid="login-demo-link" className="font-semibold text-slate-900 underline underline-offset-4 hover:text-amber-600">Try the demo</Link>
              </p>
              <p className="text-xs text-slate-600">Forgot your password? Ask your organisation admin to reset it.</p>
              <Link to="/" className="inline-flex min-h-6 items-center gap-1.5 text-xs font-semibold text-slate-600 hover:text-slate-800" data-testid="login-home-link">
                <ArrowLeft className="h-3.5 w-3.5" /> Back to fleetflow home
              </Link>
            </div>
          </form>
        </main>
      </div>
    </div>
  );
}
