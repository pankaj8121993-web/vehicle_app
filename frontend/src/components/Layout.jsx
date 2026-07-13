import { useState } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetTrigger, SheetTitle, SheetDescription } from "@/components/ui/sheet";
import { DropdownMenu, DropdownMenuTrigger, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuLabel } from "@/components/ui/dropdown-menu";
import { ROLE_LABELS, roleTier } from "@/lib/format";
import { GlobalSearch } from "@/components/GlobalSearch";
import {
  LayoutDashboard, Truck, Users, FileText, Route, Fuel, Wrench, Hammer,
  CircleDot, AlertTriangle, Radio, Clock, IndianRupee, BarChart3, LogOut, Menu,
  ChevronDown, KeyRound, ShieldCheck, TestTube, FlaskConical,
  ShieldAlert, Calendar, Activity, Building2, Settings, Eye,
} from "lucide-react";

const BASE_NAV = [
  { group: "OVERVIEW", items: [
    { to: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
    { to: "/fleet-status", label: "Fleet Status", icon: Activity },
    { to: "/compliance", label: "Compliance", icon: ShieldAlert },
    { to: "/calendar", label: "Calendar", icon: Calendar },
    { to: "/reports", label: "Reports", icon: BarChart3 },
  ]},
  { group: "FLEET", items: [
    { to: "/vehicles", label: "Vehicles", icon: Truck },
    { to: "/drivers", label: "Drivers", icon: Users },
    { to: "/documents", label: "Documents", icon: FileText },
    { to: "/vendors", label: "Vendors", icon: Building2 },
  ]},
  { group: "OPERATIONS", items: [
    { to: "/trips", label: "Trips", icon: Route },
    { to: "/fuel", label: "Fuel", icon: Fuel },
    { to: "/maintenance", label: "Maintenance", icon: Wrench },
    { to: "/repairs", label: "Tickets", icon: Hammer },
  ]},
  { group: "ASSETS & COSTS", items: [
    { to: "/tyres", label: "Tyres", icon: CircleDot },
    { to: "/accidents", label: "Accidents", icon: AlertTriangle },
    { to: "/fastag", label: "Fastag", icon: Radio },
    { to: "/downtime", label: "Downtime", icon: Clock },
    { to: "/expenses", label: "Expenses", icon: IndianRupee },
  ]},
];

const ADMIN_GROUP = {
  group: "ADMINISTRATION", items: [
    { to: "/settings/organisation", label: "Organisation", icon: Settings },
    { to: "/users", label: "User Management", icon: ShieldCheck },
    { to: "/compliance/contacts", label: "Compliance Contacts", icon: Radio },
    { to: "/admin/test-data", label: "Test Data", icon: TestTube },
  ],
};

const NAV_MODULE = {
  "/dashboard": "dashboard", "/fleet-status": "fleet-status", "/compliance": "compliance",
  "/calendar": "calendar", "/reports": "reports", "/vehicles": "vehicles", "/drivers": "drivers",
  "/documents": "documents", "/vendors": "vendors", "/trips": "trips", "/fuel": "fuel",
  "/maintenance": "maintenance", "/repairs": "repairs", "/tyres": "tyres", "/accidents": "accidents",
  "/fastag": "fastag", "/downtime": "downtime", "/expenses": "expenses",
  "/settings/organisation": "org-settings", "/users": "users",
  "/compliance/contacts": "compliance", "/admin/test-data": "test-data",
};

const buildNav = (role, modules) => {
  const tier = roleTier(role);
  const out = [...BASE_NAV];
  if (tier === "management") {
    out.push({ group: "ADMINISTRATION", items: [
      { to: "/settings/organisation", label: "Organisation", icon: Settings },
      { to: "/compliance/contacts", label: "Compliance Contacts", icon: Radio },
    ]});
  }
  if (tier === "admin") out.push(ADMIN_GROUP);
  if (!modules) return out;
  return out
    .map((g) => ({ ...g, items: g.items.filter((i) => modules.includes(NAV_MODULE[i.to] || "dashboard")) }))
    .filter((g) => g.items.length > 0);
};

const SidebarContent = ({ onNavigate, role, orgName, modules }) => {
  const nav = buildNav(role, modules);
  return (
    <div className="flex h-full flex-col bg-slate-900 text-slate-300">
      <div className="border-b border-slate-800 px-5 py-5">
        <div className="flex items-center gap-2">
          <span className="grid h-8 w-8 place-items-center bg-amber-400 text-slate-950">
            <Truck className="h-4.5 w-4.5" strokeWidth={2.4} />
          </span>
          <div>
            <p className="font-heading text-lg font-black leading-none tracking-tighter text-white">FleetFlow</p>
            <p className="mt-0.5 text-[10px] font-semibold uppercase tracking-[0.15em] text-slate-500">Fleet Operations</p>
          </div>
        </div>
        {orgName && (
          <p className="mt-3 truncate border-l-2 border-amber-400/60 pl-2 text-[11px] font-semibold text-slate-400" data-testid="sidebar-org-name">{orgName}</p>
        )}
      </div>
      <nav className="flex-1 overflow-y-auto px-3 py-4">
        {nav.map((g) => (
          <div key={g.group} className="mb-5">
            <p className="mb-1.5 px-2 text-[10px] font-bold tracking-[0.18em] text-slate-600">{g.group}</p>
            {g.items.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === "/dashboard"}
                onClick={onNavigate}
                data-testid={`nav-${item.label.toLowerCase().replace(/\s+/g, "-")}`}
                className={({ isActive }) =>
                  `mb-0.5 flex items-center gap-2.5 px-2 py-2 text-sm font-medium transition-colors ${
                    isActive ? "bg-white text-slate-900" : "hover:bg-slate-800 hover:text-white"
                  }`
                }
              >
                <item.icon className="h-4 w-4" strokeWidth={2} />
                {item.label}
              </NavLink>
            ))}
          </div>
        ))}
      </nav>
    </div>
  );
};

export const Layout = ({ children }) => {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [mobileOpen, setMobileOpen] = useState(false);

  const handleLogout = async () => {
    await logout();
    navigate("/login");
  };

  const role = user?.role;
  const initials = (user?.full_name || user?.username || "?").trim().split(/\s+/).map((w) => w[0]).slice(0, 2).join("").toUpperCase();

  const handleExitDemo = async () => {
    await logout();
    window.location.href = "/";
  };

  return (
    <div className="flex min-h-screen bg-slate-50">
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-56 lg:block">
        <SidebarContent role={role} orgName={user?.org_name} modules={user?.modules} />
      </aside>

      <div className="flex min-h-screen flex-1 flex-col lg:pl-56">
        {user?.is_demo && (
          <div className="flex items-center justify-center gap-3 border-b border-amber-300 bg-amber-400 px-4 py-2 text-center text-xs font-bold uppercase tracking-[0.12em] text-slate-950" data-testid="demo-banner">
            <Eye className="h-3.5 w-3.5" />
            Demo Environment — changes do not affect live data
            <button onClick={handleExitDemo} data-testid="exit-demo-btn"
              className="ml-2 border border-slate-950/40 px-2.5 py-0.5 text-[10px] font-black uppercase tracking-wider transition-colors hover:bg-slate-950 hover:text-amber-400">
              Exit Demo
            </button>
          </div>
        )}
        {role === "test" && (
          <div className="border-b border-amber-300 bg-amber-100 px-4 py-2 text-center text-xs font-bold uppercase tracking-[0.12em] text-amber-900" data-testid="test-mode-banner">
            <FlaskConical className="-mt-0.5 mr-1.5 inline h-3.5 w-3.5" />
            Test Mode — every record you create is tagged is_test_data and won&apos;t affect real reports
          </div>
        )}
        <header className="sticky top-0 z-20 flex h-14 items-center justify-between border-b border-slate-200 bg-white px-4 md:px-6">
          <div className="flex items-center gap-3">
            <Sheet open={mobileOpen} onOpenChange={setMobileOpen}>
              <SheetTrigger asChild>
                <Button variant="ghost" size="sm" className="lg:hidden" data-testid="mobile-menu-btn">
                  <Menu className="h-5 w-5" />
                </Button>
              </SheetTrigger>
              <SheetContent side="left" className="w-56 border-0 p-0">
                <SheetTitle className="sr-only">Navigation</SheetTitle>
                <SheetDescription className="sr-only">Main navigation menu</SheetDescription>
                <SidebarContent role={role} orgName={user?.org_name} modules={user?.modules} onNavigate={() => setMobileOpen(false)} />
              </SheetContent>
            </Sheet>
            <p className="font-heading text-sm font-bold tracking-tight text-slate-900 lg:hidden">FleetFlow</p>
          </div>
          <div className="hidden flex-1 px-6 lg:block">
            {user?.modules?.includes("search") && <GlobalSearch />}
          </div>
          <div className="flex items-center gap-3">
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <button className="flex items-center gap-2.5 border border-slate-200 bg-white px-2.5 py-1.5 hover:bg-slate-50" data-testid="user-menu-trigger">
                  <span className="grid h-7 w-7 place-items-center bg-slate-900 text-[10px] font-bold tracking-wider text-white">{initials}</span>
                  <span className="hidden text-right sm:block">
                    <span className="block text-sm font-semibold leading-tight text-slate-900" data-testid="user-fullname">{user?.full_name}</span>
                    <span className="block text-[10px] font-semibold uppercase tracking-wide text-slate-500" data-testid="user-role">{ROLE_LABELS[role] || role}</span>
                  </span>
                  <ChevronDown className="h-3.5 w-3.5 text-slate-400" />
                </button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-56 rounded-none">
                <DropdownMenuLabel className="font-mono text-xs font-bold uppercase tracking-wide text-slate-500">{user?.username}</DropdownMenuLabel>
                <DropdownMenuSeparator />
                <DropdownMenuItem onClick={() => navigate("/change-password")} data-testid="menu-change-password" className="cursor-pointer">
                  <KeyRound className="mr-2 h-4 w-4" /> Change Password
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem onClick={handleLogout} data-testid="menu-logout" className="cursor-pointer text-red-600 focus:bg-red-50 focus:text-red-700">
                  <LogOut className="mr-2 h-4 w-4" /> Sign Out
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </header>
        <main className="flex-1 p-4 md:p-6">{children}</main>
      </div>
    </div>
  );
};
