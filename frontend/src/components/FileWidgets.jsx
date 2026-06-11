import { useState } from "react";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import { Paperclip, Loader2, FileDown, CheckCircle2 } from "lucide-react";

export const FileField = ({ value, onChange, testId }) => {
  const [uploading, setUploading] = useState(false);
  const [fileName, setFileName] = useState("");

  const handleFile = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const res = await api.post("/upload", fd, { headers: { "Content-Type": "multipart/form-data" } });
      onChange(res.data.file_id);
      setFileName(res.data.original_filename);
      toast.success("File uploaded");
    } catch (err) {
      toast.error("Upload failed: " + (err.response?.data?.detail || err.message));
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="flex items-center gap-2">
      <label className="flex cursor-pointer items-center gap-2 border border-slate-300 bg-white px-3 py-2 text-sm text-slate-700 hover:bg-slate-50">
        {uploading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Paperclip className="h-4 w-4" />}
        <span>{uploading ? "Uploading…" : value ? "Replace file" : "Choose file"}</span>
        <input type="file" className="hidden" onChange={handleFile} data-testid={testId} />
      </label>
      {value && !uploading && (
        <span className="flex items-center gap-1 text-xs text-green-700">
          <CheckCircle2 className="h-3.5 w-3.5" /> {fileName || "Attached"}
        </span>
      )}
    </div>
  );
};

export const FileLink = ({ fileId }) => {
  const [loading, setLoading] = useState(false);
  if (!fileId) return <span className="text-slate-400">—</span>;

  const openFile = async (e) => {
    e.stopPropagation();
    setLoading(true);
    try {
      const res = await api.get(`/files/${fileId}`, { responseType: "blob" });
      const url = URL.createObjectURL(res.data);
      window.open(url, "_blank");
      setTimeout(() => URL.revokeObjectURL(url), 60000);
    } catch {
      toast.error("Could not open file");
    } finally {
      setLoading(false);
    }
  };

  return (
    <Button variant="ghost" size="sm" className="h-7 px-2 text-blue-700 hover:text-blue-900" onClick={openFile} data-testid={`file-link-${fileId}`}>
      {loading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <FileDown className="h-3.5 w-3.5" />}
      <span className="ml-1 text-xs">View</span>
    </Button>
  );
};
