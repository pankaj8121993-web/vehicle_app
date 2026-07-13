import { useState, useEffect, useCallback } from "react";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { toast } from "sonner";
import { StatusBadge } from "@/components/StatusBadge";
import { fmtINR, fmtDate } from "@/lib/format";
import {
  CheckCircle2, Send, Wrench, Hammer, ThumbsUp, XCircle, Lock,
  Image as ImageIcon, Trash2, Loader2, X,
} from "lucide-react";

const TICKET_STAGES = [
  { key: "open", label: "Open" },
  { key: "under_review", label: "Under Review" },
  { key: "approved", label: "Approved" },
  { key: "sent_for_repair", label: "Sent for Repair" },
  { key: "in_repair", label: "In Repair" },
  { key: "repaired", label: "Repaired" },
  { key: "closed", label: "Closed" },
];

const STAGE_ORDER = TICKET_STAGES.map((s) => s.key);

const stageMeta = (status) => {
  // Map old → new for legacy records still mid-render
  const normalized = status === "reported" ? "open" : (status === "completed" ? "closed" : status);
  return { current: normalized, index: STAGE_ORDER.indexOf(normalized) };
};

const STAGE_TIMESTAMP_FIELDS = {
  under_review: { ts: "reviewed_at", by: "reviewed_by" },
  approved: { ts: "approved_at", by: "approved_by" },
  sent_for_repair: { ts: "sent_to_vendor_at" },
  in_repair: { ts: "in_repair_at" },
  repaired: { ts: "repaired_at" },
  closed: { ts: "closed_at", by: "closed_by" },
};

const PHOTO_MAX = 8;
const PHOTO_ACCEPT = ["image/jpeg", "image/png", "image/webp"];

export const TicketDetail = ({ ticket, open, onClose, onUpdated }) => {
  const { user } = useAuth();
  const [working, setWorking] = useState(false);
  const [rejectOpen, setRejectOpen] = useState(false);
  const [rejectReason, setRejectReason] = useState("");
  const [vendorPrompt, setVendorPrompt] = useState({ open: false, vendor: "" });
  const [closingPrompt, setClosingPrompt] = useState({ open: false, cost: "" });
  const [uploading, setUploading] = useState(false);
  const [vendors, setVendors] = useState([]);
  const [pickerVendorId, setPickerVendorId] = useState("");

  const loadVendors = useCallback(async () => {
    try {
      const r = await api.get("/vendors", { params: { all: "true", active_only: "true", vendor_type: "Repair" } });
      setVendors(r.data || []);
    } catch { /* non-fatal */ }
  }, []);

  useEffect(() => { if (open) loadVendors(); }, [open, loadVendors]);

  if (!ticket) return null;
  const { current, index } = stageMeta(ticket.status);
  const role = user?.role;
  const canApprove = role === "management" || role === "admin";
  const canEdit = ["data_entry", "management", "admin"].includes(role);

  const advance = async (newStatus, extras = {}) => {
    setWorking(true);
    try {
      const r = await api.patch(`/repairs/${ticket.id}/status`, { status: newStatus, ...extras });
      toast.success(`Ticket → ${newStatus.replace(/_/g, " ")}`);
      onUpdated?.(r.data);
    } catch (err) {
      toast.error(err.response?.data?.detail ? String(err.response.data.detail) : "Action failed");
    } finally {
      setWorking(false);
    }
  };

  const handleReject = async () => {
    if (!rejectReason.trim()) {
      toast.error("Rejection reason is required");
      return;
    }
    await advance("open", { rejection_reason: rejectReason.trim() });
    setRejectOpen(false);
    setRejectReason("");
  };

  const handleSendVendor = async () => {
    const picked = vendors.find((v) => v.id === pickerVendorId);
    const vendorName = picked?.name || vendorPrompt.vendor.trim();
    if (!vendorName) {
      toast.error("Vendor name is required");
      return;
    }
    const extras = { vendor: vendorName };
    if (picked) extras.vendor_id = picked.id;
    await advance("sent_for_repair", extras);
    setVendorPrompt({ open: false, vendor: "" });
    setPickerVendorId("");
  };

  const handleClose = async () => {
    const extras = {};
    if (closingPrompt.cost !== "" && !isNaN(parseFloat(closingPrompt.cost))) {
      extras.cost = parseFloat(closingPrompt.cost);
    }
    await advance("closed", extras);
    setClosingPrompt({ open: false, cost: "" });
  };

  const uploadPhoto = async (e) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    if (!PHOTO_ACCEPT.includes(file.type)) {
      toast.error("Only JPG, PNG, or WebP images allowed");
      return;
    }
    if (file.size > 10 * 1024 * 1024) {
      toast.error("Photo must be under 10 MB");
      return;
    }
    if ((ticket.photo_file_ids || []).length >= PHOTO_MAX) {
      toast.error(`Maximum ${PHOTO_MAX} photos per ticket`);
      return;
    }
    setUploading(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const up = await api.post("/upload", fd, { headers: { "Content-Type": "multipart/form-data" } });
      const newIds = [...(ticket.photo_file_ids || []), up.data.file_id];
      const r = await api.put(`/repairs/${ticket.id}`, { photo_file_ids: newIds });
      toast.success("Photo added");
      onUpdated?.(r.data);
    } catch (err) {
      toast.error(err.response?.data?.detail || "Upload failed");
    } finally {
      setUploading(false);
    }
  };

  const removePhoto = async (fileId) => {
    const newIds = (ticket.photo_file_ids || []).filter((id) => id !== fileId);
    try {
      const r = await api.put(`/repairs/${ticket.id}`, { photo_file_ids: newIds });
      toast.success("Photo removed");
      onUpdated?.(r.data);
    } catch (err) {
      toast.error(err.response?.data?.detail || "Failed to remove");
    }
  };

  return (
    <Sheet open={open} onOpenChange={(o) => !o && onClose?.()}>
      <SheetContent className="w-full overflow-y-auto sm:max-w-2xl" data-testid="ticket-detail-drawer">
        <SheetHeader>
          <SheetTitle className="flex flex-wrap items-center gap-2 font-heading text-xl font-bold">
            <span data-testid="ticket-number">{ticket.ticket_number || "(no #)"}</span>
            <StatusBadge value={current} />
            {ticket.ticket_category && (
              <span className="border border-slate-200 bg-slate-50 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-slate-600">
                {ticket.ticket_category}
              </span>
            )}
            {ticket.repair_type === "minor" && (
              <span className="border border-slate-200 bg-slate-100 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-slate-600">Minor</span>
            )}
          </SheetTitle>
          <SheetDescription className="text-sm text-slate-500">
            {fmtDate(ticket.date)} · {ticket.vehicle_number || ticket.vehicle_id}
          </SheetDescription>
        </SheetHeader>

        <div className="mt-5 space-y-6">
          {/* Issue + cost */}
          <section className="border border-slate-200 bg-white p-4">
            <p className="text-[10px] font-bold uppercase tracking-wide text-slate-500">Issue</p>
            <p className="mt-1 text-sm text-slate-800" data-testid="ticket-issue">{ticket.issue || "—"}</p>
            <div className="mt-3 grid grid-cols-2 gap-3 text-sm">
              <Stat label="Cost" value={fmtINR(ticket.cost)} />
              <Stat label="Vendor" value={ticket.vendor || "—"} />
              <Stat label="Downtime (days)" value={ticket.downtime_days ?? 0} />
              <Stat label="Root Cause" value={ticket.root_cause || "—"} />
            </div>
            {ticket.rejection_reason && (
              <div className="mt-3 border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700" data-testid="ticket-rejection-reason">
                <span className="font-bold uppercase tracking-wide">Rejected:</span> {ticket.rejection_reason}
              </div>
            )}
          </section>

          {/* Stage timeline */}
          <section data-testid="ticket-timeline">
            <p className="mb-2 text-[10px] font-bold uppercase tracking-wide text-slate-500">Stage Timeline</p>
            <ol className="space-y-2 border-l-2 border-slate-200 pl-4">
              {TICKET_STAGES.map((stage, i) => {
                const reached = i <= index;
                const meta = STAGE_TIMESTAMP_FIELDS[stage.key] || {};
                const ts = ticket[meta.ts];
                const by = meta.by ? ticket[meta.by] : null;
                return (
                  <li key={stage.key} className={`relative pl-2 ${reached ? "" : "opacity-40"}`}>
                    <span className={`absolute -left-[22px] top-1 h-3 w-3 ${reached ? "bg-slate-900" : "border-2 border-slate-300 bg-white"}`} />
                    <p className={`text-sm font-semibold ${i === index ? "text-slate-900" : "text-slate-600"}`}>{stage.label}</p>
                    {ts && <p className="text-[11px] text-slate-500">{new Date(ts).toLocaleString("en-IN")}{by ? ` · ${by}` : ""}</p>}
                  </li>
                );
              })}
            </ol>
          </section>

          {/* Photos */}
          <section data-testid="ticket-photos">
            <div className="mb-2 flex items-center justify-between">
              <p className="text-[10px] font-bold uppercase tracking-wide text-slate-500">Photos ({(ticket.photo_file_ids || []).length}/{PHOTO_MAX})</p>
              {canEdit && (ticket.photo_file_ids || []).length < PHOTO_MAX && (
                <label className="flex cursor-pointer items-center gap-1 border border-slate-300 bg-white px-2 py-1 text-xs text-slate-700 hover:bg-slate-50">
                  {uploading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <ImageIcon className="h-3.5 w-3.5" />}
                  <span>{uploading ? "Uploading…" : "Add Photo"}</span>
                  <input type="file" accept="image/jpeg,image/png,image/webp" className="hidden" onChange={uploadPhoto} data-testid="ticket-photo-input" />
                </label>
              )}
            </div>
            <div className="grid grid-cols-3 gap-2 sm:grid-cols-4">
              {(ticket.photo_file_ids || []).map((id) => (
                <PhotoTile key={id} fileId={id} onRemove={canEdit ? () => removePhoto(id) : null} />
              ))}
              {!(ticket.photo_file_ids || []).length && <p className="col-span-full text-xs text-slate-400">No photos yet</p>}
            </div>
          </section>

          {/* Actions */}
          {current !== "closed" && (
            <section className="flex flex-wrap gap-2 border-t border-slate-200 pt-4" data-testid="ticket-actions">
              {current === "open" && canEdit && (
                <Button onClick={() => advance("under_review")} disabled={working} className="rounded-none bg-slate-900 text-white hover:bg-slate-800" data-testid="ticket-send-review">
                  <Send className="mr-2 h-4 w-4" /> Send for Review
                </Button>
              )}
              {current === "under_review" && canApprove && (
                <>
                  <Button onClick={() => advance("approved")} disabled={working} className="rounded-none bg-indigo-600 text-white hover:bg-indigo-700" data-testid="ticket-approve">
                    <ThumbsUp className="mr-2 h-4 w-4" /> Approve
                  </Button>
                  <Button onClick={() => setRejectOpen(true)} disabled={working} variant="outline" className="rounded-none border-red-300 text-red-700 hover:bg-red-50" data-testid="ticket-reject">
                    <XCircle className="mr-2 h-4 w-4" /> Reject
                  </Button>
                </>
              )}
              {current === "under_review" && !canApprove && (
                <p className="text-xs text-slate-500"><Lock className="-mt-0.5 mr-1 inline h-3.5 w-3.5" /> Awaiting Management or Admin approval</p>
              )}
              {current === "approved" && canEdit && (
                <Button onClick={() => setVendorPrompt({ open: true, vendor: ticket.vendor || "" })} disabled={working} className="rounded-none bg-purple-600 text-white hover:bg-purple-700" data-testid="ticket-send-vendor">
                  <Send className="mr-2 h-4 w-4" /> Send to Vendor
                </Button>
              )}
              {current === "sent_for_repair" && canEdit && (
                <Button onClick={() => advance("in_repair")} disabled={working} className="rounded-none bg-orange-600 text-white hover:bg-orange-700" data-testid="ticket-vendor-received">
                  <Wrench className="mr-2 h-4 w-4" /> Vendor Received
                </Button>
              )}
              {current === "in_repair" && canEdit && (
                <Button onClick={() => advance("repaired")} disabled={working} className="rounded-none bg-teal-600 text-white hover:bg-teal-700" data-testid="ticket-mark-repaired">
                  <Hammer className="mr-2 h-4 w-4" /> Mark Repaired
                </Button>
              )}
              {current === "repaired" && canApprove && (
                <Button onClick={() => setClosingPrompt({ open: true, cost: ticket.cost || "" })} disabled={working} className="rounded-none bg-green-700 text-white hover:bg-green-800" data-testid="ticket-close">
                  <CheckCircle2 className="mr-2 h-4 w-4" /> Close Ticket
                </Button>
              )}
              {current === "repaired" && !canApprove && (
                <p className="text-xs text-slate-500"><Lock className="-mt-0.5 mr-1 inline h-3.5 w-3.5" /> Awaiting Management or Admin closure</p>
              )}
            </section>
          )}
        </div>

        {/* Reject reason dialog (lightweight inline) */}
        {rejectOpen && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={() => setRejectOpen(false)}>
            <div className="w-full max-w-md border border-slate-200 bg-white p-5" onClick={(e) => e.stopPropagation()}>
              <p className="font-heading text-lg font-bold">Reject ticket</p>
              <Label className="mt-3 block text-xs font-semibold uppercase tracking-wide text-slate-500">Rejection Reason</Label>
              <Textarea data-testid="ticket-reject-reason" value={rejectReason} onChange={(e) => setRejectReason(e.target.value)} rows={3} className="mt-1 rounded-none" />
              <div className="mt-4 flex justify-end gap-2">
                <Button variant="outline" className="rounded-none" onClick={() => setRejectOpen(false)}>Cancel</Button>
                <Button onClick={handleReject} disabled={working} className="rounded-none bg-red-600 text-white hover:bg-red-700" data-testid="ticket-reject-confirm">Reject</Button>
              </div>
            </div>
          </div>
        )}

        {/* Vendor prompt dialog */}
        {vendorPrompt.open && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={() => setVendorPrompt({ open: false, vendor: "" })}>
            <div className="w-full max-w-md border border-slate-200 bg-white p-5" onClick={(e) => e.stopPropagation()}>
              <p className="font-heading text-lg font-bold">Send to vendor</p>
              {vendors.length > 0 && (
                <>
                  <Label className="mt-3 block text-[10px] font-bold uppercase tracking-wide text-slate-500">Pick saved vendor (optional)</Label>
                  <select
                    data-testid="ticket-vendor-picker"
                    value={pickerVendorId}
                    onChange={(e) => {
                      setPickerVendorId(e.target.value);
                      const v = vendors.find((x) => x.id === e.target.value);
                      if (v) setVendorPrompt((p) => ({ ...p, vendor: v.name }));
                    }}
                    className="mt-1 w-full border border-slate-200 bg-white px-2 py-2 text-sm"
                  >
                    <option value="">— None (free text below) —</option>
                    {vendors.map((v) => <option key={v.id} value={v.id}>{v.name}</option>)}
                  </select>
                </>
              )}
              <Label className="mt-3 block text-[10px] font-bold uppercase tracking-wide text-slate-500">Vendor / Workshop Name</Label>
              <Input data-testid="ticket-vendor-input" value={vendorPrompt.vendor} onChange={(e) => setVendorPrompt((p) => ({ ...p, vendor: e.target.value }))} className="mt-1 rounded-none" />
              <div className="mt-4 flex justify-end gap-2">
                <Button variant="outline" className="rounded-none" onClick={() => setVendorPrompt({ open: false, vendor: "" })}>Cancel</Button>
                <Button onClick={handleSendVendor} disabled={working} className="rounded-none bg-purple-600 text-white hover:bg-purple-700" data-testid="ticket-vendor-confirm">Send</Button>
              </div>
            </div>
          </div>
        )}

        {/* Closing cost dialog */}
        {closingPrompt.open && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={() => setClosingPrompt({ open: false, cost: "" })}>
            <div className="w-full max-w-md border border-slate-200 bg-white p-5" onClick={(e) => e.stopPropagation()}>
              <p className="font-heading text-lg font-bold">Close ticket</p>
              <Label className="mt-3 block text-[10px] font-bold uppercase tracking-wide text-slate-500">Final Cost (₹) — optional</Label>
              <Input data-testid="ticket-close-cost" type="number" value={closingPrompt.cost} onChange={(e) => setClosingPrompt((p) => ({ ...p, cost: e.target.value }))} className="mt-1 rounded-none" />
              <div className="mt-4 flex justify-end gap-2">
                <Button variant="outline" className="rounded-none" onClick={() => setClosingPrompt({ open: false, cost: "" })}>Cancel</Button>
                <Button onClick={handleClose} disabled={working} className="rounded-none bg-green-700 text-white hover:bg-green-800" data-testid="ticket-close-confirm">Close Ticket</Button>
              </div>
            </div>
          </div>
        )}
      </SheetContent>
    </Sheet>
  );
};

const Stat = ({ label, value }) => (
  <div>
    <p className="text-[10px] font-bold uppercase tracking-wide text-slate-500">{label}</p>
    <p className="font-mono text-sm text-slate-800">{value}</p>
  </div>
);

const PhotoTile = ({ fileId, onRemove }) => {
  const [src, setSrc] = useState(null);
  useEffect(() => {
    let cancelled = false;
    let blobUrl = null;
    api.get(`/files/${fileId}`, { responseType: "blob" })
      .then((r) => {
        blobUrl = URL.createObjectURL(r.data);
        if (!cancelled) setSrc(blobUrl);
      })
      .catch(() => { /* ignore */ });
    return () => {
      cancelled = true;
      if (blobUrl) URL.revokeObjectURL(blobUrl);
    };
  }, [fileId]);
  return (
    <div className="relative aspect-square border border-slate-200 bg-slate-100" data-testid={`ticket-photo-${fileId}`}>
      {src
        ? <img src={src} alt="" className="h-full w-full object-cover" />
        : <div className="flex h-full items-center justify-center"><Loader2 className="h-4 w-4 animate-spin text-slate-400" /></div>}
      {onRemove && (
        <button onClick={onRemove} className="absolute right-1 top-1 bg-slate-900/80 p-1 text-white hover:bg-red-700" data-testid={`ticket-photo-remove-${fileId}`}>
          <X className="h-3 w-3" />
        </button>
      )}
    </div>
  );
};
