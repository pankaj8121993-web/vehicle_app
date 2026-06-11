import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { Truck, ShieldCheck, BarChart3, FileText } from "lucide-react";

// REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
export default function Login() {
  const { user, loading } = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    if (!loading && user) navigate("/", { replace: true });
  }, [user, loading, navigate]);

  const handleLogin = () => {
    const redirectUrl = window.location.origin + "/";
    window.location.href = `https://auth.emergentagent.com/?redirect=${encodeURIComponent(redirectUrl)}`;
  };

  return (
    <div className="flex min-h-screen" data-testid="login-page-container">
      <div className="relative hidden w-1/2 lg:block">
        <img
          src="https://images.pexels.com/photos/6940962/pexels-photo-6940962.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=1080&w=1920"
          alt="Fleet truck"
          className="h-full w-full object-cover"
        />
        <div className="absolute inset-0 bg-slate-900/60" />
        <div className="absolute bottom-12 left-12 right-12 text-white">
          <h2 className="font-heading text-3xl font-black tracking-tighter">Every vehicle. Every document. Every rupee.</h2>
          <p className="mt-2 max-w-md text-sm text-slate-200">
            One platform for compliance, trips, fuel, maintenance, tyres, accidents, Fastag and complete fleet cost control.
          </p>
        </div>
      </div>

      <div className="flex w-full items-center justify-center bg-white px-6 lg:w-1/2">
        <div className="w-full max-w-md">
          <div className="mb-10">
            <div className="mb-6 inline-flex items-center gap-3 border border-slate-200 bg-slate-50 px-4 py-2">
              <Truck className="h-5 w-5 text-slate-900" strokeWidth={2} />
              <span className="font-heading text-sm font-black uppercase tracking-wide text-slate-900">Rajguru Foods</span>
            </div>
            <h1 className="font-heading text-4xl font-black tracking-tighter text-slate-900 sm:text-5xl">
              Fleet Command Center
            </h1>
            <p className="mt-3 text-base text-slate-500">
              Sign in to access the centralized Fleet & Vehicle Management System.
            </p>
          </div>

          <Button
            data-testid="google-login-btn"
            onClick={handleLogin}
            className="h-12 w-full rounded-none bg-slate-900 text-base font-semibold text-white hover:bg-slate-800"
          >
            <svg className="mr-3 h-5 w-5" viewBox="0 0 24 24">
              <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.27-4.74 3.27-8.1z" />
              <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
              <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18A10.96 10.96 0 0 0 1 12c0 1.77.43 3.45 1.18 4.93l2.85-2.22.81-.62z" />
              <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" />
            </svg>
            Continue with Google
          </Button>

          <div className="mt-12 grid grid-cols-3 gap-4 border-t border-slate-200 pt-8">
            <div className="text-center">
              <ShieldCheck className="mx-auto mb-2 h-5 w-5 text-slate-400" />
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Compliance Alerts</p>
            </div>
            <div className="text-center">
              <FileText className="mx-auto mb-2 h-5 w-5 text-slate-400" />
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Digital Vehicle Files</p>
            </div>
            <div className="text-center">
              <BarChart3 className="mx-auto mb-2 h-5 w-5 text-slate-400" />
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Cost Analytics</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
