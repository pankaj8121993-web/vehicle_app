export const StatusTabs = ({ tabs, value, onChange, testIdPrefix = "status" }) => (
  <div className="mb-4 flex flex-wrap gap-1 border border-slate-200 bg-white p-1" data-testid={`${testIdPrefix}-tabs`}>
    {tabs.map((t) => (
      <button
        key={t.value}
        onClick={() => onChange(t.value)}
        data-testid={`${testIdPrefix}-tab-${t.value || "all"}`}
        className={`px-4 py-2 text-xs font-bold uppercase tracking-wide transition-colors ${
          value === t.value ? "bg-slate-900 text-white" : "text-slate-500 hover:bg-slate-100 hover:text-slate-900"
        }`}
      >
        {t.label}
      </button>
    ))}
  </div>
);
