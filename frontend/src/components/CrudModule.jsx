import { useState, useEffect, useCallback, useMemo } from "react";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { toast } from "sonner";
import { Plus, Pencil, Trash2, Search, Loader2, ChevronLeft, ChevronRight } from "lucide-react";
import { fmtINR, fmtNum, fmtDate } from "@/lib/format";
import { useAuth } from "@/context/AuthContext";
import { canCreate, canEdit, canDelete } from "@/lib/permissions";
import { StatusBadge, ExpiryBadge } from "@/components/StatusBadge";
import { FileField, FileLink } from "@/components/FileWidgets";

const renderCell = (col, row) => {
  const val = row[col.key];
  switch (col.type) {
    case "currency": return <span className="font-mono">{fmtINR(val)}</span>;
    case "number": return <span className="font-mono">{fmtNum(val)}</span>;
    case "date": return fmtDate(val);
    case "badge": return <StatusBadge value={val} />;
    case "expiry": return <ExpiryBadge date={val} />;
    case "file": return <FileLink fileId={val} />;
    default: return val === null || val === undefined || val === "" ? <span className="text-slate-400">—</span> : String(val);
  }
};

const FieldInput = ({ field, value, onChange, options }) => {
  const testId = `form-field-${field.name}`;
  if (field.type === "textarea") {
    return <Textarea data-testid={testId} value={value ?? ""} onChange={(e) => onChange(e.target.value)} rows={2} className="rounded-none" />;
  }
  if (field.type === "select" || field.type === "vehicle" || field.type === "driver" || field.type === "tyre") {
    const opts = field.type === "select" ? field.options : options[field.type] || [];
    return (
      <Select value={value ?? ""} onValueChange={onChange}>
        <SelectTrigger data-testid={testId} className="rounded-none">
          <SelectValue placeholder={`Select ${field.label}`} />
        </SelectTrigger>
        <SelectContent>
          {opts.map((o) => (
            <SelectItem key={o.value} value={o.value} data-testid={`option-${field.name}-${o.value}`}>{o.label}</SelectItem>
          ))}
        </SelectContent>
      </Select>
    );
  }
  if (field.type === "file") {
    return <FileField value={value} onChange={onChange} testId={testId} />;
  }
  return (
    <div className="relative">
      <Input
        data-testid={testId}
        type={field.type === "number" ? "number" : field.type === "date" ? "date" : "text"}
        step={field.type === "number" ? "any" : undefined}
        value={value ?? ""}
        onChange={(e) => onChange(e.target.value)}
        className={`rounded-none ${field.suffix || field.prefix ? "pr-10" : ""}`}
        placeholder={field.placeholder}
      />
      {field.suffix && <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs font-semibold text-slate-400">{field.suffix}</span>}
    </div>
  );
};

export const CrudModule = ({
  title, endpoint, columns, fields, fixedFilters = {},
  onRowClick, rowActions, addLabel, testIdPrefix, emptyText, refreshKey,
  readOnly = false,
}) => {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [sheetOpen, setSheetOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState({});
  const [saving, setSaving] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState(null);
  const [options, setOptions] = useState({ vehicle: [], driver: [], tyre: [] });
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const PAGE_SIZE = 25;

  const { user } = useAuth();
  const role = user?.role;
  const prefix = testIdPrefix || endpoint;
  const fixedJson = JSON.stringify(fixedFilters);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.get(`/${endpoint}`, { params: { ...JSON.parse(fixedJson), page, page_size: PAGE_SIZE } });
      if (Array.isArray(res.data)) {
        setItems(res.data);
        setTotal(res.data.length);
      } else {
        setItems(res.data.items);
        setTotal(res.data.total);
      }
    } catch (err) {
      toast.error(`Failed to load ${title}`);
    } finally {
      setLoading(false);
    }
  }, [endpoint, fixedJson, title, page]);

  useEffect(() => { refresh(); }, [refresh, refreshKey]);

  const neededOptionTypes = useMemo(
    () => [...new Set(fields.filter((f) => ["vehicle", "driver", "tyre"].includes(f.type)).map((f) => f.type))],
    [fields]
  );

  useEffect(() => {
    const load = async () => {
      const next = {};
      try {
        if (neededOptionTypes.includes("vehicle")) {
          const r = await api.get("/vehicles", { params: { all: "true" } });
          next.vehicle = r.data.map((v) => ({ value: v.id, label: v.vehicle_number }));
        }
        if (neededOptionTypes.includes("driver")) {
          const r = await api.get("/drivers/active");
          next.driver = r.data.map((d) => ({ value: d.id, label: d.name }));
        }
        if (neededOptionTypes.includes("tyre")) {
          const r = await api.get("/tyres", { params: { ...JSON.parse(fixedJson), all: "true" } });
          next.tyre = r.data.map((t) => ({ value: t.id, label: `${t.tyre_number} (${t.vehicle_number || ""})` }));
        }
        setOptions((prev) => ({ ...prev, ...next }));
      } catch { /* options load failure is non-fatal */ }
    };
    if (neededOptionTypes.length) load();
  }, [neededOptionTypes, fixedJson, sheetOpen]);

  const visibleFields = fields.filter((f) => !(f.name in fixedFilters));

  const openAdd = () => {
    const init = {};
    fields.forEach((f) => { if (f.default !== undefined) init[f.name] = f.default; });
    setEditing(null);
    setForm(init);
    setSheetOpen(true);
  };

  const openEdit = (row) => {
    const init = {};
    fields.forEach((f) => { init[f.name] = row[f.name] ?? null; });
    setEditing(row);
    setForm(init);
    setSheetOpen(true);
  };

  const submit = async () => {
    for (const f of visibleFields) {
      if (f.required && (form[f.name] === undefined || form[f.name] === null || form[f.name] === "")) {
        toast.error(`${f.label} is required`);
        return;
      }
    }
    const payload = { ...JSON.parse(fixedJson) };
    fields.forEach((f) => {
      let v = form[f.name];
      if (v === "" || v === undefined) v = null;
      if (f.type === "number" && v !== null) v = parseFloat(v);
      payload[f.name] = v;
    });
    setSaving(true);
    try {
      if (editing) {
        await api.put(`/${endpoint}/${editing.id}`, payload);
        toast.success(`${title} updated`);
      } else {
        await api.post(`/${endpoint}`, payload);
        toast.success(`${title} added`);
      }
      setSheetOpen(false);
      refresh();
    } catch (err) {
      toast.error(err.response?.data?.detail ? String(err.response.data.detail) : "Save failed");
    } finally {
      setSaving(false);
    }
  };

  const confirmDelete = async () => {
    try {
      await api.delete(`/${endpoint}/${deleteTarget.id}`);
      toast.success("Deleted");
      refresh();
    } catch (err) {
      toast.error(err.response?.data?.detail ? String(err.response.data.detail) : "Delete failed");
    } finally {
      setDeleteTarget(null);
    }
  };

  const filtered = search
    ? items.filter((it) => JSON.stringify(it).toLowerCase().includes(search.toLowerCase()))
    : items;

  return (
    <div data-testid={`${prefix}-module`}>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
          <Input
            data-testid={`${prefix}-search-input`}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder={`Search ${title.toLowerCase()}…`}
            className="w-64 rounded-none pl-9"
          />
        </div>
        {!readOnly && canCreate(role, endpoint) && (
          <Button data-testid={`${prefix}-add-btn`} onClick={openAdd} className="rounded-none bg-slate-900 text-white hover:bg-slate-800">
            <Plus className="mr-1 h-4 w-4" /> {addLabel || `Add ${title}`}
          </Button>
        )}
      </div>

      <div className="overflow-x-auto border border-slate-200 bg-white">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-200 bg-slate-50">
              {columns.map((c) => (
                <th key={c.key} className={`px-3 py-2.5 text-xs font-semibold uppercase tracking-wide text-slate-500 ${["currency", "number"].includes(c.type) ? "text-right" : "text-left"}`}>
                  {c.label}
                </th>
              ))}
              <th className="px-3 py-2.5 text-right text-xs font-semibold uppercase tracking-wide text-slate-500">Actions</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={columns.length + 1} className="px-3 py-10 text-center text-slate-400"><Loader2 className="mx-auto h-5 w-5 animate-spin" /></td></tr>
            ) : filtered.length === 0 ? (
              <tr><td colSpan={columns.length + 1} className="px-3 py-10 text-center text-sm text-slate-400" data-testid={`${prefix}-empty-state`}>{emptyText || `No ${title.toLowerCase()} records yet.`}</td></tr>
            ) : (
              filtered.map((row) => (
                <tr
                  key={row.id}
                  data-testid={`${prefix}-row-${row.id}`}
                  className={`border-b border-slate-100 hover:bg-slate-50 ${onRowClick ? "cursor-pointer" : ""}`}
                  onClick={onRowClick ? () => onRowClick(row) : undefined}
                >
                  {columns.map((c) => (
                    <td key={c.key} className={`px-3 py-2.5 ${["currency", "number"].includes(c.type) ? "text-right" : ""}`}>
                      {renderCell(c, row)}
                    </td>
                  ))}
                  <td className="px-3 py-2.5 text-right" onClick={(e) => e.stopPropagation()}>
                    <div className="flex items-center justify-end gap-1">
                      {rowActions && rowActions(row, refresh)}
                      {!readOnly && canEdit(role) && (
                        <Button data-testid={`${prefix}-edit-${row.id}`} variant="ghost" size="sm" className="h-7 w-7 p-0" onClick={() => openEdit(row)}>
                          <Pencil className="h-3.5 w-3.5 text-slate-500" />
                        </Button>
                      )}
                      {!readOnly && canDelete(role) && (
                        <Button data-testid={`${prefix}-delete-${row.id}`} variant="ghost" size="sm" className="h-7 w-7 p-0" onClick={() => setDeleteTarget(row)}>
                          <Trash2 className="h-3.5 w-3.5 text-red-500" />
                        </Button>
                      )}
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {total > PAGE_SIZE && (
        <div className="flex items-center justify-between border border-t-0 border-slate-200 bg-white px-3 py-2">
          <span className="text-xs text-slate-500" data-testid={`${prefix}-pagination-info`}>
            Showing {(page - 1) * PAGE_SIZE + 1}–{Math.min(page * PAGE_SIZE, total)} of {total}
          </span>
          <div className="flex gap-1">
            <Button data-testid={`${prefix}-prev-page`} variant="outline" size="sm" className="h-7 rounded-none px-2" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
              <ChevronLeft className="h-3.5 w-3.5" />
            </Button>
            <Button data-testid={`${prefix}-next-page`} variant="outline" size="sm" className="h-7 rounded-none px-2" disabled={page * PAGE_SIZE >= total} onClick={() => setPage((p) => p + 1)}>
              <ChevronRight className="h-3.5 w-3.5" />
            </Button>
          </div>
        </div>
      )}

      <Sheet open={sheetOpen} onOpenChange={setSheetOpen}>
        <SheetContent className="w-full overflow-y-auto sm:max-w-md">
          <SheetHeader>
            <SheetTitle className="font-heading text-xl font-bold">{editing ? `Edit ${title}` : addLabel || `Add ${title}`}</SheetTitle>
          </SheetHeader>
          <div className="mt-5 space-y-4">
            {visibleFields.map((f) => (
              <div key={f.name} className="space-y-1.5">
                <Label className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                  {f.label}{f.required && <span className="text-red-600"> *</span>}
                </Label>
                <FieldInput field={f} value={form[f.name]} onChange={(v) => setForm((p) => ({ ...p, [f.name]: v }))} options={options} />
              </div>
            ))}
            <Button data-testid={`${prefix}-submit-btn`} onClick={submit} disabled={saving} className="w-full rounded-none bg-slate-900 text-white hover:bg-slate-800">
              {saving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
              {editing ? "Save Changes" : "Save"}
            </Button>
          </div>
        </SheetContent>
      </Sheet>

      <AlertDialog open={!!deleteTarget} onOpenChange={(o) => !o && setDeleteTarget(null)}>
        <AlertDialogContent className="rounded-none">
          <AlertDialogHeader>
            <AlertDialogTitle>Delete this record?</AlertDialogTitle>
            <AlertDialogDescription>This action cannot be undone.</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel className="rounded-none" data-testid={`${prefix}-delete-cancel`}>Cancel</AlertDialogCancel>
            <AlertDialogAction className="rounded-none bg-red-600 hover:bg-red-700" onClick={confirmDelete} data-testid={`${prefix}-delete-confirm`}>Delete</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
};
