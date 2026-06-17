import { useState } from "react";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { TestTube, Trash2, ShieldAlert, Loader2 } from "lucide-react";
import { toast } from "sonner";

export default function TestDataAdmin() {
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);

  const purge = async () => {
    setLoading(true);
    try {
      const r = await api.post("/admin/purge-test-data");
      setResult(r.data);
      toast.success(`Deleted ${r.data.total} test records`);
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Failed");
    } finally { setLoading(false); setOpen(false); }
  };

  return (
    <div data-testid="test-data-admin-page">
      <div className="mb-6">
        <h1 className="font-heading text-3xl font-black tracking-tighter text-slate-900 md:text-4xl">Test Data Administration</h1>
        <p className="mt-1 text-sm text-slate-500">Purge sandbox records created by the Test User role.</p>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <div className="border border-slate-200 bg-white p-6">
          <div className="mb-3 flex items-center gap-2">
            <div className="border border-slate-200 bg-slate-50 p-2.5"><TestTube className="h-5 w-5 text-slate-700" /></div>
            <p className="font-heading text-lg font-bold tracking-tight text-slate-900">How test mode works</p>
          </div>
          <ul className="space-y-2 text-sm leading-relaxed text-slate-600">
            <li>• Logged-in Test User can browse the app like a real role, but every record they create is tagged <span className="font-mono text-xs">is_test_data: true</span>.</li>
            <li>• Test data is invisible to other users — dashboards, drilldowns, alerts and reports exclude it.</li>
            <li>• Test users can only edit/delete records they themselves marked as test data.</li>
            <li>• Use the button below to wipe the sandbox at any time.</li>
          </ul>
        </div>

        <div className="border border-red-200 bg-red-50/50 p-6">
          <div className="mb-3 flex items-center gap-2">
            <div className="border border-red-200 bg-white p-2.5"><ShieldAlert className="h-5 w-5 text-red-600" /></div>
            <p className="font-heading text-lg font-bold tracking-tight text-slate-900">Purge all test data</p>
          </div>
          <p className="text-sm text-slate-600">
            This will permanently delete every record across vehicles, drivers, trips, fuel, services, repairs, tyres, accidents,
            Fastag, downtimes, expenses, greasings and calendar events where <span className="font-mono text-xs">is_test_data = true</span>. Real data is untouched.
          </p>
          <Button onClick={() => setOpen(true)} className="mt-5 rounded-none bg-red-600 text-white hover:bg-red-700" data-testid="purge-test-data-btn">
            <Trash2 className="mr-2 h-4 w-4" /> Purge Test Data
          </Button>

          {result && (
            <div className="mt-5 border border-slate-200 bg-white p-4" data-testid="purge-result">
              <p className="font-mono text-xs font-bold uppercase tracking-wide text-slate-500">Deleted</p>
              <p className="font-heading text-3xl font-black tracking-tighter text-slate-900">{result.total} <span className="text-sm font-normal text-slate-400">records</span></p>
              <div className="mt-3 grid grid-cols-2 gap-1.5 text-xs">
                {Object.entries(result.deleted).filter(([, n]) => n > 0).map(([k, n]) => (
                  <div key={k} className="flex justify-between border-b border-slate-100 py-1">
                    <span className="font-mono text-slate-500">{k}</span>
                    <span className="font-mono font-semibold text-slate-900">{n}</span>
                  </div>
                ))}
                {Object.values(result.deleted).every((n) => n === 0) && <p className="col-span-2 italic text-slate-400">No test records found.</p>}
              </div>
            </div>
          )}
        </div>
      </div>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="rounded-none" data-testid="purge-confirm-dialog">
          <DialogHeader>
            <DialogTitle className="font-heading text-xl font-black tracking-tighter">Purge all test data?</DialogTitle>
            <DialogDescription>This deletes every record tagged is_test_data=true across all modules. Cannot be undone. Real records are unaffected.</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)} className="rounded-none">Cancel</Button>
            <Button onClick={purge} disabled={loading} className="rounded-none bg-red-600 text-white hover:bg-red-700" data-testid="purge-confirm-btn">
              {loading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Trash2 className="mr-2 h-4 w-4" />}
              Yes, purge
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
