import { useState, useEffect } from "react";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { canEdit } from "@/lib/permissions";
import { toast } from "sonner";
import { Loader2, ImagePlus, Trash2, Camera } from "lucide-react";

export const VehiclePhotos = ({ vehicleId, photoIds, readOnly = false }) => {
  const { user } = useAuth();
  const editable = !readOnly && canEdit(user?.role);
  const [ids, setIds] = useState(photoIds || []);
  const [urls, setUrls] = useState({});
  const [uploading, setUploading] = useState(false);

  useEffect(() => {
    ids.forEach((fid) => {
      if (urls[fid]) return;
      api.get(`/files/${fid}`, { responseType: "blob" })
        .then((r) => setUrls((p) => ({ ...p, [fid]: URL.createObjectURL(r.data) })))
        .catch(() => {});
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ids]);

  const save = async (newIds) => {
    await api.put(`/vehicles/${vehicleId}`, { photo_file_ids: newIds });
    setIds(newIds);
  };

  const onUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const res = await api.post("/upload", fd, { headers: { "Content-Type": "multipart/form-data" } });
      await save([...ids, res.data.file_id]);
      toast.success("Photo added");
    } catch (err) {
      toast.error("Upload failed: " + (err.response?.data?.detail || err.message));
    } finally {
      setUploading(false);
    }
  };

  const removePhoto = async (fid) => {
    try {
      await save(ids.filter((i) => i !== fid));
      toast.success("Photo removed");
    } catch {
      toast.error("Failed to remove photo");
    }
  };

  return (
    <div data-testid="vehicle-photos">
      {editable && (
        <label className="mb-5 inline-flex cursor-pointer items-center gap-2 border border-slate-300 bg-white px-4 py-2.5 text-sm font-semibold text-slate-700 hover:bg-slate-50">
          {uploading ? <Loader2 className="h-4 w-4 animate-spin" /> : <ImagePlus className="h-4 w-4" />}
          {uploading ? "Uploading…" : "Add Photo"}
          <input type="file" accept="image/*" className="hidden" onChange={onUpload} data-testid="vehicle-photo-input" disabled={uploading} />
        </label>
      )}

      {ids.length === 0 ? (
        <div className="flex flex-col items-center border border-dashed border-slate-300 bg-white py-14 text-slate-400" data-testid="vehicle-photos-empty">
          <Camera className="mb-2 h-7 w-7" />
          <p className="text-sm">No photos yet. {editable ? "Add the first vehicle photo." : ""}</p>
        </div>
      ) : (
        <div className="grid grid-cols-2 gap-4 md:grid-cols-3 xl:grid-cols-4">
          {ids.map((fid) => (
            <div key={fid} className="group relative border border-slate-200 bg-white" data-testid={`vehicle-photo-${fid}`}>
              {urls[fid] ? (
                <img src={urls[fid]} alt="Vehicle" className="aspect-video w-full object-cover" />
              ) : (
                <div className="flex aspect-video items-center justify-center"><Loader2 className="h-5 w-5 animate-spin text-slate-300" /></div>
              )}
              {editable && (
                <button
                  data-testid={`vehicle-photo-delete-${fid}`}
                  onClick={() => removePhoto(fid)}
                  className="absolute right-2 top-2 hidden border border-red-200 bg-white p-1.5 text-red-600 hover:bg-red-50 group-hover:block"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
