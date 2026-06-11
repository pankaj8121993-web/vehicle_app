import { useState } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetTrigger } from "@/components/ui/sheet";
import { ROLE_LABELS } from "@/lib/format";
import {
  LayoutDashboard, Truck, Users, FileText, Route, Fuel, Wrench, Hammer,
  CircleDot, AlertTriangle, Radio, Clock, IndianRupee, BarChart3, UserCog, LogOut, Menu,
} from "lucide-react";

const NAV = [
  { group: "OVERVIEW", items: [
    { to: "/", label: "Dashboard", icon: LayoutDashboard },
    { to: "/reports", label: "Reports", icon: BarChart3 },
  ]},
  { group: "FLEET", items: [
    { to: "/vehicles", label: "Vehicles", icon: Truck },
    { to: "/drivers", label: "Drivers", icon: Users },
    { to: "/documents", label: "Documents", icon: FileText },
  ]},
  { group: "OPERATIONS", items: [
    { to: "/trips", label: "Trips", icon: Route },
    { to: "/fuel", label: "Fuel", icon: Fuel },
    { to: "/maintenance", label: "Maintenance", icon: Wrench },
    { to: "/repairs", label: "Repairs", icon: Hammer },
  ]},
  { group: "ASSETS & COSTS", items: [
    { to: "/tyres", label: "Tyres", icon: CircleDot },
    { to: "/accidents", label: "Accidents", icon: AlertTriangle },
    { to: "/fastag", label: "Fastag", icon: Radio },
    { to: "/downtime", label: "Downtime", icon: Clock },
    { to: "/expenses", label: "Expenses", icon: IndianRupee },
  ]},
];

const SidebarContent = ({ onNavigate }) => {
  const { user } = useAuth();
  const showUsers = ["management", "fleet_manager"].includes(user?.role);
  return (
    <div className="flex h-full flex-col bg-slate-900 text-slate-300">
      <div className="border-b border-slate-800 px-5 py-5">
        <p className="font-heading text-lg font-black uppercase tracking-tight text-white">Rajguru Foods</p>
        <p className="text-[11px] font-semibold uppercase tracking-[0.15em] text-slate-500">Fleet Command</p>
      </div>
      <nav className="flex-1 overflow-y-auto px-3 py-4">
        {NAV.map((g) => (
          <div key={g.group} className="mb-5">
            <p className="mb-1.5 px-2 text-[10px] font-bold tracking-[0.18em] text-slate-600">{g.group}</p>
            {g.items.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === "/"}
                onClick={onNavigate}
                data-testid={`nav-${item.label.toLowerCase()}`}
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
        {showUsers && (
          <div className="mb-5">
            <p className="mb-1.5 px-2 text-[10px] font-bold tracking-[0.18em] text-slate-600">ADMIN</p>
            <NavLink to="/users" onClick={onNavigate} data-testid="nav-users"
              className={({ isActive }) =>
                `mb-0.5 flex items-center gap-2.5 px-2 py-2 text-sm font-medium transition-colors ${
                  isActive ? "bg-white text-slate-900" : "hover:bg-slate-800 hover:text-white"
                }`
              }>
              <UserCog className="h-4 w-4" strokeWidth={2} />
              Users & Roles
            </NavLink>
          </div>
        )}
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

  return (
    <div className="flex min-h-screen bg-slate-50">
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-56 lg:block">
        <SidebarContent />
      </aside>

      <div className="flex min-h-screen flex-1 flex-col lg:pl-56">
        <header className="sticky top-0 z-20 flex h-14 items-center justify-between border-b border-slate-200 bg-white px-4 md:px-6">
          <div className="flex items-center gap-3">
            <Sheet open={mobileOpen} onOpenChange={setMobileOpen}>
              <SheetTrigger asChild>
                <Button variant="ghost" size="sm" className="lg:hidden" data-testid="mobile-menu-btn">
                  <Menu className="h-5 w-5" />
                </Button>
              </SheetTrigger>
              <SheetContent side="left" className="w-56 border-0 p-0">
                <SidebarContent onNavigate={() => setMobileOpen(false)} />
              </SheetContent>
            </Sheet>
            <p className="font-heading text-sm font-bold uppercase tracking-wide text-slate-500 lg:hidden">Rajguru Fleet</p>
          </div>
          <div className="flex items-center gap-3">
            <div className="hidden text-right sm:block">
              <p className="text-sm font-semibold text-slate-900" data-testid="user-name">{user?.name}</p>
              <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500" data-testid="user-role">{ROLE_LABELS[user?.role] || user?.role}</p>
            </div>
            {user?.picture && <img src={user.picture} alt="" className="h-8 w-8 border border-slate-200" referrerPolicy="no-referrer" />}
            <Button variant="ghost" size="sm" onClick={handleLogout} data-testid="logout-btn" className="text-slate-500 hover:text-slate-900">
              <LogOut className="h-4 w-4" />
            </Button>
          </div>
        </header>
        <main className="flex-1 p-4 md:p-6">{children}</main>
      </div>
    </div>
  );
};
