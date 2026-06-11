import { useState, useEffect, useCallback } from "react";
import api from "@/lib/api";
import { PageHeader } from "@/pages/ModulePages";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { toast } from "sonner";
import { Loader2, FileSpreadsheet, FileText, Play } from "lucide-react";

export default function Reports() {
  const [reports, setReports] = useState([]);
  const [vehicles, setVehicles] = useState([]);
  const [drivers, setDrivers] = useState([]);
  const [key, setKey] = useState("trips");
  const [filters, setFilters] = useState({ start_date: "", end_date: "", vehicle_id: "", driver_id: "" });
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [exporting, setExporting] = useState(null);

  useEffect(() => {
    api.get("/reports").then((r) => setReports(r.data)).catch(() => {});
    api.get("/vehicles").then((r) => setVehicles(r.data)).catch(() => {});
    api.get("/drivers").then((r) => setDrivers(r.data)).catch(() => {});
  }, []);

  const params = useCallback(() => {
    const p = {};
    Object.entries(filters).forEach(([k, v]) => { if (v) p[k] = v; });
    return p;
  }, [filters]);

  const run = async () => {
    setLoading(true);
    try {
      const res = await api.get(`/reports/${key}`, { params: params() });
      setResult(res.data);
    } catch {
      toast.error("Failed to generate report");
    } finally {
      setLoading(false);
    }
  };

  const exportFile = async (format) => {
    setExporting(format);
    try {
      const res = await api.get(`/reports/${key}/export`, { params: { ...params(), format }, responseType: "blob" });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${key}_report.${format === "excel" ? "xlsx" : "pdf"}`;
      a.click();
      URL.revokeObjectURL(url);
      toast.success(`${format === "excel" ? "Excel" : "PDF"} downloaded`);
    } catch {
      toast.error("Export failed");
    } finally {
      setExporting(null);
    }
  };

  return (
    <div data-testid="reports-page">
      <PageHeader title="Reports & Analytics" subtitle="Filter by date, vehicle or driver — export to Excel or PDF" />

      <div className="mb-6 grid grid-cols-1 gap-4 border border-slate-200 bg-white p-5 md:grid-cols-3 xl:grid-cols-6">
        <div className="space-y-1.5 md:col-span-2">
          <Label className="text-xs font-semibold uppercase tracking-wide text-slate-500">Report</Label>
          <Select value={key} onValueChange={(v) => { setKey(v); setResult(null); }}>
            <SelectTrigger data-testid="report-select" className="rounded-none"><SelectValue /></SelectTrigger>
            <SelectContent>
              {reports.map((r) => <SelectItem key={r.key} value={r.key} data-testid={`report-option-${r.key}`}>{r.name}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1.5">
          <Label className="text-xs font-semibold uppercase tracking-wide text-slate-500">From</Label>
          <Input data-testid="report-start-date" type="date" value={filters.start_date} onChange={(e) => setFilters((p) => ({ ...p, start_date: e.target.value }))} className="rounded-none" />
        </div>
        <div className="space-y-1.5">
          <Label className="text-xs font-semibold uppercase tracking-wide text-slate-500">To</Label>
          <Input data-testid="report-end-date" type="date" value={filters.end_date} onChange={(e) => setFilters((p) => ({ ...p, end_date: e.target.value }))} className="rounded-none" />
        </div>
        <div className="space-y-1.5">
          <Label className="text-xs font-semibold uppercase tracking-wide text-slate-500">Vehicle</Label>
          <Select value={filters.vehicle_id || "all"} onValueChange={(v) => setFilters((p) => ({ ...p, vehicle_id: v === "all" ? "" : v }))}>
            <SelectTrigger data-testid="report-vehicle-filter" className="rounded-none"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Vehicles</SelectItem>
              {vehicles.map((v) => <SelectItem key={v.id} value={v.id}>{v.vehicle_number}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1.5">
          <Label className="text-xs font-semibold uppercase tracking-wide text-slate-500">Driver</Label>
          <Select value={filters.driver_id || "all"} onValueChange={(v) => setFilters((p) => ({ ...p, driver_id: v === "all" ? "" : v }))}>
            <SelectTrigger data-testid="report-driver-filter" className="rounded-none"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Drivers</SelectItem>
              {drivers.map((d) => <SelectItem key={d.id} value={d.id}>{d.name}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
      </div>

      <div className="mb-6 flex flex-wrap gap-3">
        <Button data-testid="run-report-btn" onClick={run} disabled={loading} className="rounded-none bg-slate-900 text-white hover:bg-slate-800">
          {loading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Play className="mr-2 h-4 w-4" />} Generate Report
        </Button>
        <Button data-testid="export-excel-btn" variant="outline" onClick={() => exportFile("excel")} disabled={!!exporting} className="rounded-none border-green-300 text-green-700 hover:bg-green-50">
          {exporting === "excel" ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <FileSpreadsheet className="mr-2 h-4 w-4" />} Export Excel
        </Button>
        <Button data-testid="export-pdf-btn" variant="outline" onClick={() => exportFile("pdf")} disabled={!!exporting} className="rounded-none border-red-300 text-red-700 hover:bg-red-50">
          {exporting === "pdf" ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <FileText className="mr-2 h-4 w-4" />} Export PDF
        </Button>
      </div>

      {result && (
        <div className="overflow-x-auto border border-slate-200 bg-white" data-testid="report-result-table">
          <div className="border-b border-slate-200 px-5 py-3">
            <p className="font-heading text-base font-bold text-slate-900">{result.name}</p>
            <p className="text-xs text-slate-500">{result.rows.length} rows</p>
          </div>
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-200 bg-slate-50">
                {result.columns.map((c) => <th key={c} className="px-3 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">{c}</th>)}
              </tr>
            </thead>
            <tbody>
              {result.rows.length === 0 ? (
                <tr><td colSpan={result.columns.length} className="px-3 py-10 text-center text-sm text-slate-400">No data for selected filters.</td></tr>
              ) : result.rows.map((row, i) => (
                <tr key={i} className="border-b border-slate-100 hover:bg-slate-50">
                  {row.map((cell, j) => <td key={j} className="px-3 py-2 font-mono text-xs text-slate-700">{cell === null || cell === undefined || cell === "" ? "—" : String(cell)}</td>)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
