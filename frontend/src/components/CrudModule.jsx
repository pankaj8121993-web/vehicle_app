import { useState, useEffect, useCallback, useMemo, useRef } from "react";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from "@/components/ui/sheet";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { toast } from "sonner";
import { Plus, Pencil, Trash2, Search, Loader2, ChevronLeft, ChevronRight, ArrowDown, ArrowUp } from "lucide-react";
import { Checkbox } from "@/components/ui/checkbox";
import { fmtINR, fmtNum, fmtDate } from "@/lib/format";
import { useAuth } from "@/context/AuthContext";
import { canCreate, canEdit, canDelete } from "@/lib/permissions";
import { StatusBadge, ExpiryBadge } from "@/components/StatusBadge";
import { FileField, FileLink } from "@/components/FileWidgets";
import { explainApiError, recordLabel, validateCrudForm } from "@/lib/formSafety";
import { UNSAVED_MESSAGE, useUnsavedChanges } from "@/hooks/useUnsavedChanges";

const renderCell = (col, row) => {
  const val = row[col.key];
  switch (col.type) {
    case "currency": return <span className="font-mono">{fmtINR(val)}</span>;
    case "number": return <span className="font-mono">{fmtNum(val)}</span>;
    case "date": return fmtDate(val);
    case "badge": return <StatusBadge value={val} />;
    case "expiry": return <ExpiryBadge date={val} />;
    case "file": return <FileLink fileId={val} />;
    case "boolean": return val ? <span className="text-xs font-semibold text-green-700">Yes</span> : <span className="text-xs font-semibold text-slate-400">No</span>;
    case "tags": {
      const arr = Array.isArray(val) ? val : [];
      if (!arr.length) return <span className="text-slate-400">—</span>;
      return (
        <div className="flex flex-wrap gap-1">
          {arr.map((t) => (
            <span key={t} className="border border-slate-200 bg-slate-50 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-slate-600">{t}</span>
          ))}
        </div>
      );
    }
    default: return val === null || val === undefined || val === "" ? <span className="text-slate-400">—</span> : String(val);
  }
};

const FieldInput = ({ field, value, onChange, options, form, setForm, error }) => {
  const testId = `form-field-${field.name}`;
  const inputId = `crud-field-${field.name}`;
  if (field.type === "textarea") {
    return <Textarea id={inputId} data-testid={testId} aria-invalid={!!error} aria-describedby={error ? `${inputId}-error` : undefined} value={value ?? ""} onChange={(e) => onChange(e.target.value)} rows={2} className="rounded-none" />;
  }
  if (field.type === "boolean") {
    return (
      <Switch
        data-testid={testId}
        id={inputId}
        checked={!!value}
        onCheckedChange={onChange}
      />
    );
  }
  if (field.type === "vendor_picker") {
    const vendors = options.vendor || [];
    const filtered = field.vendorType
      ? vendors.filter((v) => v.vendor_type === field.vendorType || v.vendor_type === "Other")
      : vendors;
    const fillField = field.autoFillField || "vendor";
    const onPick = (vid) => {
      const v = vendors.find((x) => x.id === vid);
      if (v && setForm) {
        setForm((p) => ({ ...p, [fillField]: v.name, vendor_id: v.id }));
      }
    };
    return (
      <Select value="" onValueChange={onPick}>
        <SelectTrigger id={inputId} data-testid={testId} aria-invalid={!!error} aria-describedby={error ? `${inputId}-error` : undefined} className="rounded-none">
          <SelectValue placeholder={filtered.length ? "Select a saved vendor…" : "No saved vendors — type below"} />
        </SelectTrigger>
        <SelectContent>
          {filtered.map((v) => (
            <SelectItem key={v.id} value={v.id} data-testid={`vendor-option-${v.id}`}>
              {v.name}
              {v.vendor_type !== field.vendorType && <span className="ml-1 text-xs text-slate-400">({v.vendor_type})</span>}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    );
  }
  if (field.type === "multiselect") {
    const selected = Array.isArray(value) ? value : [];
    return (
      <div className="flex flex-col gap-1.5 border border-slate-200 bg-white p-2" data-testid={testId}>
        {(field.options || []).map((o) => (
          <label key={o.value} className="flex cursor-pointer items-center gap-2 text-sm">
            <Checkbox
              checked={selected.includes(o.value)}
              onCheckedChange={(checked) =>
                onChange(checked ? [...selected, o.value] : selected.filter((x) => x !== o.value))
              }
              data-testid={`${testId}-option-${o.value.replace(/[^a-z0-9]+/gi, "-").toLowerCase()}`}
            />
            <span>{o.label}</span>
          </label>
        ))}
      </div>
    );
  }
  if (field.type === "select" || field.type === "vehicle" || field.type === "driver" || field.type === "tyre") {
    const opts = field.type === "select" ? field.options : options[field.type] || [];
    return (
      <Select value={value ?? ""} onValueChange={onChange}>
        <SelectTrigger id={inputId} data-testid={testId} aria-invalid={!!error} aria-describedby={error ? `${inputId}-error` : undefined} className="rounded-none">
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
        id={inputId}
        aria-invalid={!!error}
        aria-describedby={error ? `${inputId}-error` : undefined}
        type={field.type === "number" ? "number" : field.type === "date" ? "date" : "text"}
        step={field.type === "number" ? "any" : undefined}
        min={field.type === "number" ? (["quantity", "litres"].includes(field.name) ? "0.01" : "0") : undefined}
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
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [sheetOpen, setSheetOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState({});
  const [saving, setSaving] = useState(false);
  const [formErrors, setFormErrors] = useState({});
  const savingRef = useRef(false);
  const [deleteTarget, setDeleteTarget] = useState(null);
  const [options, setOptions] = useState({ vehicle: [], driver: [], tyre: [], vendor: [] });
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [pageSize, setPageSize] = useState(25);
  const [sortBy, setSortBy] = useState("");
  const [sortDir, setSortDir] = useState("asc");
  const requestSequence = useRef(0);

  const { user } = useAuth();
  const role = user?.role;
  const prefix = testIdPrefix || endpoint;
  const fixedJson = JSON.stringify(fixedFilters);
  const initialFormRef = useRef("{}");
  const isDirty = sheetOpen && JSON.stringify(form) !== initialFormRef.current;
  useUnsavedChanges(isDirty && !saving);

  const refresh = useCallback(async () => {
    const requestId = ++requestSequence.current;
    setLoading(true);
    try {
      const res = await api.get(`/${endpoint}`, { params: {
        ...JSON.parse(fixedJson), page, page_size: pageSize,
        search: debouncedSearch || undefined,
        sort_by: sortBy || undefined, sort_dir: sortBy ? sortDir : undefined,
      } });
      if (requestId !== requestSequence.current) return;
      if (Array.isArray(res.data)) {
        setItems(res.data);
        setTotal(res.data.length);
      } else {
        setItems(res.data.items);
        setTotal(res.data.total);
      }
    } catch (err) {
      if (requestId === requestSequence.current) toast.error(`Failed to load ${title}`);
    } finally {
      if (requestId === requestSequence.current) setLoading(false);
    }
  }, [endpoint, fixedJson, title, page, pageSize, debouncedSearch, sortBy, sortDir]);

  useEffect(() => { refresh(); }, [refresh, refreshKey]);
  useEffect(() => {
    const timer = window.setTimeout(() => {
      setPage(1);
      setDebouncedSearch(search.trim());
    }, 300);
    return () => window.clearTimeout(timer);
  }, [search]);

  const neededOptionTypes = useMemo(
    () => [...new Set(fields.filter((f) => ["vehicle", "driver", "tyre", "vendor_picker"].includes(f.type)).map((f) => f.type))],
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
        if (neededOptionTypes.includes("vendor_picker")) {
          const r = await api.get("/vendors", { params: { all: "true", active_only: "true" } });
          next.vendor = r.data;
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
    setFormErrors({});
    initialFormRef.current = JSON.stringify(init);
    setSheetOpen(true);
  };

  const openEdit = (row) => {
    const init = {};
    fields.forEach((f) => { init[f.name] = row[f.name] ?? null; });
    setEditing(row);
    setForm(init);
    setFormErrors({});
    initialFormRef.current = JSON.stringify(init);
    setSheetOpen(true);
  };

  const submit = async () => {
    if (savingRef.current) return;
    const errors = validateCrudForm(visibleFields, form);
    setFormErrors(errors);
    if (Object.keys(errors).length) return;
    const payload = { ...JSON.parse(fixedJson) };
    fields.forEach((f) => {
      if (f.type === "vendor_picker") return;  // pseudo-field; not submitted
      let v = form[f.name];
      if (v === "" || v === undefined) v = null;
      if (f.type === "number" && v !== null) v = parseFloat(v);
      payload[f.name] = v;
    });
    if (form.vendor_id) payload.vendor_id = form.vendor_id;
    savingRef.current = true;
    setSaving(true);
    try {
      if (editing) {
        await api.put(`/${endpoint}/${editing.id}`, payload);
        toast.success(`${title} updated`);
      } else {
        await api.post(`/${endpoint}`, payload);
        toast.success(`${title} added`);
      }
      initialFormRef.current = JSON.stringify(form);
      setSheetOpen(false);
      refresh();
    } catch (err) {
      toast.error(explainApiError(err, "Save failed. Your entries have been kept."));
    } finally {
      savingRef.current = false;
      setSaving(false);
    }
  };

  const confirmDelete = async () => {
    if (!deleteTarget || savingRef.current) return;
    savingRef.current = true;
    setSaving(true);
    try {
      await api.delete(`/${endpoint}/${deleteTarget.id}`);
      toast.success("Deleted");
      refresh();
    } catch (err) {
      toast.error(explainApiError(err, "Delete failed."));
      return;
    } finally {
      savingRef.current = false;
      setSaving(false);
    }
    setDeleteTarget(null);
  };

  const changeSort = (field) => {
    setPage(1);
    if (sortBy === field) setSortDir((direction) => direction === "asc" ? "desc" : "asc");
    else {
      setSortBy(field);
      setSortDir("asc");
    }
  };

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
                <th key={c.key} aria-sort={sortBy === c.key ? (sortDir === "asc" ? "ascending" : "descending") : "none"} className={`px-3 py-2.5 text-xs font-semibold uppercase tracking-wide text-slate-500 ${["currency", "number"].includes(c.type) ? "text-right" : "text-left"}`}>
                  <button type="button" className="inline-flex min-h-7 items-center gap-1 hover:text-slate-900" onClick={() => changeSort(c.key)} data-testid={`${prefix}-sort-${c.key}`}>
                    {c.label}
                    {sortBy === c.key && (sortDir === "asc" ? <ArrowUp className="h-3 w-3" /> : <ArrowDown className="h-3 w-3" />)}
                  </button>
                </th>
              ))}
              <th className="px-3 py-2.5 text-right text-xs font-semibold uppercase tracking-wide text-slate-500">Actions</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={columns.length + 1} className="px-3 py-10 text-center text-slate-400"><Loader2 className="mx-auto h-5 w-5 animate-spin" /></td></tr>
            ) : items.length === 0 ? (
              <tr><td colSpan={columns.length + 1} className="px-3 py-10 text-center text-sm text-slate-400" data-testid={`${prefix}-empty-state`}>
                {debouncedSearch ? `No ${title.toLowerCase()} match “${debouncedSearch}”.` : emptyText || `No ${title.toLowerCase()} records yet.`}
              </td></tr>
            ) : (
              items.map((row) => (
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

      {(total > pageSize || pageSize !== 25) && (
        <div className="flex items-center justify-between border border-t-0 border-slate-200 bg-white px-3 py-2">
          <span className="text-xs text-slate-500" data-testid={`${prefix}-pagination-info`}>
            Showing {total ? (page - 1) * pageSize + 1 : 0}–{Math.min(page * pageSize, total)} of {total}
          </span>
          <div className="flex items-center gap-2">
            <Label htmlFor={`${prefix}-page-size`} className="sr-only">Rows per page</Label>
            <select id={`${prefix}-page-size`} value={pageSize} onChange={(event) => { setPageSize(Number(event.target.value)); setPage(1); }} className="h-7 border border-slate-200 bg-white px-2 text-xs" data-testid={`${prefix}-page-size`}>
              {[25, 50, 100].map((size) => <option key={size} value={size}>{size} rows</option>)}
            </select>
            <Button data-testid={`${prefix}-prev-page`} variant="outline" size="sm" className="h-7 rounded-none px-2" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
              <ChevronLeft className="h-3.5 w-3.5" />
            </Button>
            <Button data-testid={`${prefix}-next-page`} variant="outline" size="sm" className="h-7 rounded-none px-2" disabled={page * pageSize >= total} onClick={() => setPage((p) => p + 1)}>
              <ChevronRight className="h-3.5 w-3.5" />
            </Button>
          </div>
        </div>
      )}

      <Sheet open={sheetOpen} onOpenChange={(open) => {
        if (!open && isDirty && !window.confirm(UNSAVED_MESSAGE)) return;
        setSheetOpen(open);
      }}>
        <SheetContent className="w-full overflow-y-auto sm:max-w-md">
          <SheetHeader>
            <SheetTitle className="font-heading text-xl font-bold">{editing ? `Edit ${title}` : addLabel || `Add ${title}`}</SheetTitle>
            <SheetDescription className="sr-only">{editing ? `Edit ${title} form` : `Add ${title} form`}</SheetDescription>
          </SheetHeader>
          <form className="mt-5 space-y-4" onSubmit={(event) => { event.preventDefault(); submit(); }} noValidate>
            {Object.keys(formErrors).length > 0 && (
              <p className="border-l-2 border-red-500 bg-red-50 px-3 py-2 text-sm text-red-700" role="alert">
                Review the highlighted fields before saving.
              </p>
            )}
            {visibleFields.map((f) => (
              <div key={f.name} className="space-y-1.5">
                <Label htmlFor={`crud-field-${f.name}`} className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                  {f.label}{f.required && <span className="text-red-600"> *</span>}
                </Label>
                <FieldInput field={f} value={form[f.name]} error={formErrors[f.name]} onChange={(v) => {
                  setForm((p) => ({ ...p, [f.name]: v }));
                  setFormErrors((previous) => ({ ...previous, [f.name]: undefined }));
                }} options={options} form={form} setForm={setForm} />
                {formErrors[f.name] && <p id={`crud-field-${f.name}-error`} className="text-xs text-red-700">{formErrors[f.name]}</p>}
              </div>
            ))}
            <Button type="submit" data-testid={`${prefix}-submit-btn`} disabled={saving} className="w-full rounded-none bg-slate-900 text-white hover:bg-slate-800">
              {saving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
              {editing ? "Save Changes" : "Save"}
            </Button>
          </form>
        </SheetContent>
      </Sheet>

      <AlertDialog open={!!deleteTarget} onOpenChange={(o) => !o && setDeleteTarget(null)}>
        <AlertDialogContent className="rounded-none">
          <AlertDialogHeader>
            <AlertDialogTitle>Delete {recordLabel(deleteTarget)}?</AlertDialogTitle>
            <AlertDialogDescription>This permanently removes {recordLabel(deleteTarget)}. This action cannot be undone.</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel className="rounded-none" data-testid={`${prefix}-delete-cancel`}>Cancel</AlertDialogCancel>
            <AlertDialogAction disabled={saving} className="rounded-none bg-red-600 hover:bg-red-700" onClick={confirmDelete} data-testid={`${prefix}-delete-confirm`}>Delete</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
};
