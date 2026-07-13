import { useState, useEffect, useRef, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import api from "@/lib/api";
import { Search, Loader2, X } from "lucide-react";

const RECENT_KEY = "fleet_recent_searches";
const RECENT_MAX = 5;

const loadRecent = () => {
  try {
    return JSON.parse(localStorage.getItem(RECENT_KEY) || "[]");
  } catch {
    return [];
  }
};

const saveRecent = (term) => {
  if (!term || term.length < 2) return;
  const arr = loadRecent().filter((t) => t.toLowerCase() !== term.toLowerCase());
  arr.unshift(term);
  localStorage.setItem(RECENT_KEY, JSON.stringify(arr.slice(0, RECENT_MAX)));
};

export const GlobalSearch = () => {
  const navigate = useNavigate();
  const [q, setQ] = useState("");
  const [results, setResults] = useState(null);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);
  const [recent, setRecent] = useState(loadRecent());
  const containerRef = useRef(null);
  const inputRef = useRef(null);

  // Debounced search
  useEffect(() => {
    if (q.trim().length < 2) {
      setResults(null);
      return;
    }
    setLoading(true);
    const handle = setTimeout(async () => {
      try {
        const r = await api.get("/search", { params: { q: q.trim() } });
        setResults(r.data);
        setActiveIndex(-1);
      } catch {
        setResults({ vehicles: [], drivers: [], tickets: [], documents: [] });
      } finally {
        setLoading(false);
      }
    }, 300);
    return () => clearTimeout(handle);
  }, [q]);

  // Close on outside click
  useEffect(() => {
    const onDocClick = (e) => {
      if (!containerRef.current?.contains(e.target)) setOpen(false);
    };
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, []);

  const flatItems = useCallback(() => {
    if (!results) return [];
    return [
      ...results.vehicles.map((v) => ({ kind: "vehicle", id: v.id, label: v.vehicle_number, sub: `${v.make || ""} ${v.model || ""}`.trim() })),
      ...results.drivers.map((d) => ({ kind: "driver", id: d.id, label: d.name, sub: d.employee_number || d.mobile || "" })),
      ...results.tickets.map((t) => ({ kind: "ticket", id: t.id, label: t.ticket_number || "Ticket", sub: `${t.vehicle_number || ""} · ${t.issue || ""}` })),
      ...results.documents.map((d) => ({ kind: "document", id: d.id, label: `${d.doc_type} ${d.doc_number || ""}`.trim(), sub: d.vehicle_number || "" })),
    ];
  }, [results]);

  const navigateTo = (item) => {
    saveRecent(q.trim());
    setRecent(loadRecent());
    setOpen(false);
    setQ("");
    setResults(null);
    if (item.kind === "vehicle") navigate(`/vehicles/${item.id}`);
    else if (item.kind === "driver") navigate(`/drivers/${item.id}`);
    else if (item.kind === "ticket") navigate("/repairs");
    else if (item.kind === "document") navigate("/documents");
  };

  const onKeyDown = (e) => {
    const items = flatItems();
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActiveIndex((i) => Math.min(i + 1, items.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActiveIndex((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter" && activeIndex >= 0 && items[activeIndex]) {
      e.preventDefault();
      navigateTo(items[activeIndex]);
    } else if (e.key === "Escape") {
      setOpen(false);
      inputRef.current?.blur();
    }
  };

  const empty = results && !flatItems().length && !loading;
  const total = flatItems().length;
  let cursor = 0;

  return (
    <div ref={containerRef} className="relative mx-auto max-w-2xl" data-testid="global-search">
      <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
      <input
        ref={inputRef}
        type="text"
        value={q}
        placeholder="Search vehicles, drivers, tickets, documents…"
        onChange={(e) => setQ(e.target.value)}
        onFocus={() => setOpen(true)}
        onKeyDown={onKeyDown}
        data-testid="global-search-input"
        className="w-full rounded-none border border-slate-200 bg-slate-50 py-2 pl-9 pr-9 text-sm focus:border-slate-400 focus:bg-white focus:outline-none"
      />
      {q && (
        <button
          onClick={() => { setQ(""); setResults(null); inputRef.current?.focus(); }}
          className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-slate-400 hover:text-slate-700"
          data-testid="global-search-clear"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      )}

      {open && (
        <div className="absolute left-0 right-0 top-full z-50 mt-1 max-h-[28rem] overflow-y-auto border border-slate-200 bg-white shadow-lg" data-testid="global-search-dropdown">
          {loading && (
            <div className="flex items-center justify-center py-6 text-slate-400">
              <Loader2 className="h-4 w-4 animate-spin" />
            </div>
          )}

          {!loading && q.trim().length >= 1 && q.trim().length < 2 && (
            <p className="px-4 py-6 text-center text-xs text-slate-400" data-testid="global-search-min-hint">Type at least 2 characters</p>
          )}

          {!loading && q.trim().length < 2 && recent.length > 0 && (
            <div className="p-2">
              <p className="px-2 py-1 text-[10px] font-bold uppercase tracking-wide text-slate-400">Recent searches</p>
              {recent.map((term) => (
                <button
                  key={term}
                  onClick={() => setQ(term)}
                  className="block w-full px-3 py-1.5 text-left text-sm text-slate-600 hover:bg-slate-50"
                  data-testid={`global-search-recent-${term.replace(/\s+/g, "-").toLowerCase()}`}
                >
                  {term}
                </button>
              ))}
            </div>
          )}

          {!loading && empty && (
            <p className="px-4 py-6 text-center text-sm text-slate-500" data-testid="global-search-empty">No matches for &quot;{q}&quot;</p>
          )}

          {!loading && results && total > 0 && (
            <div className="py-1">
              {["vehicles", "drivers", "tickets", "documents"].map((key) => {
                const arr = results[key] || [];
                if (!arr.length) return null;
                return (
                  <div key={key} className="border-t border-slate-100 first:border-t-0">
                    <p className="px-3 pt-2 text-[10px] font-bold uppercase tracking-wide text-slate-400">{key}</p>
                    {arr.map((item) => {
                      const flat = flatItems();
                      const idx = cursor++;
                      const active = idx === activeIndex;
                      const display = flat[idx];
                      return (
                        <button
                          key={`${key}-${item.id}`}
                          onMouseEnter={() => setActiveIndex(idx)}
                          onClick={() => navigateTo(display)}
                          className={`block w-full px-3 py-2 text-left text-sm ${active ? "bg-slate-100" : "hover:bg-slate-50"}`}
                          data-testid={`global-search-result-${key}-${item.id}`}
                        >
                          <p className="font-semibold text-slate-900">{display.label}</p>
                          {display.sub && <p className="text-xs text-slate-500">{display.sub}</p>}
                        </button>
                      );
                    })}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
};
