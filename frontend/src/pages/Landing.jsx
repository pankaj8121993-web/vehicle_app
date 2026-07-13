import { Link } from "react-router-dom";
import { Navigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { motion } from "framer-motion";
import {
  Truck, Route, Fuel, Wrench, ShieldAlert, IndianRupee, BarChart3, Users,
  CheckCircle2, ArrowRight, Building2, Lock, FileSearch, Radio, PlayCircle, Menu,
} from "lucide-react";
import { useState } from "react";

const FEATURES = [
  { icon: Truck, title: "Vehicle Master", text: "A complete digital file per vehicle — documents, FASTag, odometer, disposal history and lifetime statistics." },
  { icon: Route, title: "Trips & Operations", text: "Open and close trips with odometer capture, route details, toll and trip expenses — from desktop or mobile." },
  { icon: Fuel, title: "Fuel & Mileage", text: "Every fill-up auto-computes mileage and fuel cost per kilometre so poor performers surface immediately." },
  { icon: Wrench, title: "Maintenance & Tickets", text: "A 7-stage service-ticket workflow — open, review, approve, send for repair, repair, verify, close — with full audit trail." },
  { icon: ShieldAlert, title: "Compliance Alerts", text: "RC, insurance, permit, fitness, PUC and licence expiries tracked with configurable reminder windows." },
  { icon: IndianRupee, title: "Expense Intelligence", text: "A consolidated ledger from every module plus budgets, insights, duplicate detection and cost-per-km analytics." },
  { icon: BarChart3, title: "Dashboards & Reports", text: "Role-specific dashboards with drill-downs, printable reports and CSV exports for every register." },
  { icon: Users, title: "Roles & Approvals", text: "Eight roles from Organisation Super Admin to Auditor, enforced on the server — not just hidden buttons." },
];

const STEPS = [
  { n: "01", title: "Create your workspace", text: "Register your company, LLP, proprietorship or individual fleet in a guided setup wizard." },
  { n: "02", title: "Add your fleet", text: "Add vehicles, drivers, vendors and compliance documents — manually or at your own pace." },
  { n: "03", title: "Run daily operations", text: "Trips, fuel, maintenance, tickets, expenses and approvals flow through one connected system." },
  { n: "04", title: "See everything clearly", text: "Dashboards, alerts and reports keep owners, managers and auditors on the same page." },
];

const AUDIENCES = [
  "Transport operators", "Logistics businesses", "Distribution fleets", "Employee transport",
  "Construction & projects", "Institutions & trusts", "Individual fleet owners", "Owned, leased or attached fleets",
];

const fade = {
  initial: { opacity: 0, y: 24 },
  whileInView: { opacity: 1, y: 0 },
  viewport: { once: true, margin: "-60px" },
  transition: { duration: 0.55, ease: "easeOut" },
};

export const BrandMark = ({ dark = false }) => (
  <div className="flex items-center gap-2.5">
    <span className={`grid h-9 w-9 place-items-center ${dark ? "bg-amber-400 text-slate-950" : "bg-slate-900 text-amber-400"}`}>
      <Truck className="h-5 w-5" strokeWidth={2.4} />
    </span>
    <span>
      <span className={`block font-heading text-lg font-black leading-none tracking-tighter ${dark ? "text-white" : "text-slate-900"}`}>FleetFlow</span>
      <span className={`block text-[9px] font-bold uppercase tracking-[0.22em] ${dark ? "text-slate-400" : "text-slate-500"}`}>Fleet Operations</span>
    </span>
  </div>
);

export default function Landing() {
  const { user, loading } = useAuth();
  const [menuOpen, setMenuOpen] = useState(false);
  if (!loading && user) return <Navigate to="/dashboard" replace />;

  return (
    <div className="min-h-screen bg-slate-950 text-slate-300" data-testid="landing-page">
      {/* Nav */}
      <header className="sticky top-0 z-40 border-b border-white/10 bg-slate-950/80 backdrop-blur-xl">
        <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-5 lg:px-8">
          <BrandMark dark />
          <nav className="hidden items-center gap-8 text-sm font-medium md:flex">
            <a href="#features" className="transition-colors hover:text-white">Features</a>
            <a href="#how" className="transition-colors hover:text-white">How it works</a>
            <a href="#who" className="transition-colors hover:text-white">Who it's for</a>
            <a href="#security" className="transition-colors hover:text-white">Security</a>
          </nav>
          <div className="hidden items-center gap-3 md:flex">
            <Link to="/login" data-testid="nav-login-btn" className="px-3 py-2 text-sm font-semibold text-white transition-colors hover:text-amber-400">Login</Link>
            <Link to="/get-started" data-testid="nav-get-started-btn">
              <Button className="rounded-none bg-amber-400 px-5 font-bold text-slate-950 hover:bg-amber-300">Get Started</Button>
            </Link>
          </div>
          <button className="md:hidden" onClick={() => setMenuOpen(!menuOpen)} data-testid="landing-mobile-menu" aria-label="Menu">
            <Menu className="h-6 w-6 text-white" />
          </button>
        </div>
        {menuOpen && (
          <div className="border-t border-white/10 bg-slate-950 px-5 py-4 md:hidden">
            <div className="flex flex-col gap-3 text-sm">
              <a href="#features" onClick={() => setMenuOpen(false)}>Features</a>
              <a href="#how" onClick={() => setMenuOpen(false)}>How it works</a>
              <Link to="/demo" className="font-semibold text-amber-400">Try FleetFlow Demo</Link>
              <Link to="/login" className="font-semibold text-white">Login</Link>
              <Link to="/get-started" className="font-semibold text-white">Get Started</Link>
            </div>
          </div>
        )}
      </header>

      {/* Hero */}
      <section className="relative overflow-hidden">
        <div className="pointer-events-none absolute -right-40 -top-40 h-[480px] w-[480px] rounded-full bg-amber-400/10 blur-3xl" />
        <div className="pointer-events-none absolute inset-0 opacity-[0.04]" style={{ backgroundImage: "linear-gradient(#fff 1px, transparent 1px), linear-gradient(90deg, #fff 1px, transparent 1px)", backgroundSize: "56px 56px" }} />
        <div className="relative mx-auto max-w-7xl px-5 pb-24 pt-20 lg:px-8 lg:pt-28">
          <motion.p {...fade} className="mb-5 inline-block border border-amber-400/40 bg-amber-400/10 px-3 py-1 text-[11px] font-bold uppercase tracking-[0.2em] text-amber-400">
            Complete Fleet Operations Management
          </motion.p>
          <motion.h1 {...fade} transition={{ ...fade.transition, delay: 0.08 }}
            className="max-w-4xl font-heading text-4xl font-black leading-[1.02] tracking-tighter text-white sm:text-5xl lg:text-6xl">
            Every Vehicle. Every Journey.<br />
            <span className="text-amber-400">Completely Under Control.</span>
          </motion.h1>
          <motion.p {...fade} transition={{ ...fade.transition, delay: 0.16 }} className="mt-6 max-w-2xl text-base leading-relaxed text-slate-400">
            FleetFlow brings your complete fleet operation into one connected platform — vehicles, drivers,
            trips, fuel, maintenance, expenses, compliance, incidents, approvals and management reporting.
          </motion.p>
          <motion.div {...fade} transition={{ ...fade.transition, delay: 0.24 }} className="mt-9 flex flex-wrap items-center gap-4">
            <Link to="/get-started" data-testid="hero-get-started-btn">
              <Button className="group rounded-none bg-amber-400 px-7 py-6 text-sm font-bold text-slate-950 hover:bg-amber-300">
                Get Started <ArrowRight className="ml-2 h-4 w-4 transition-transform group-hover:translate-x-1" />
              </Button>
            </Link>
            <Link to="/demo" data-testid="hero-demo-btn">
              <Button variant="outline" className="rounded-none border-white/25 bg-transparent px-7 py-6 text-sm font-bold text-white hover:bg-white/10 hover:text-white">
                <PlayCircle className="mr-2 h-4 w-4" /> Try FleetFlow Demo
              </Button>
            </Link>
            <a href="#features" className="text-sm font-semibold text-slate-400 underline-offset-4 transition-colors hover:text-white hover:underline" data-testid="hero-explore-link">
              Explore Features
            </a>
          </motion.div>
          <motion.div {...fade} transition={{ ...fade.transition, delay: 0.32 }} className="mt-16 grid max-w-3xl grid-cols-2 gap-px border border-white/10 bg-white/10 sm:grid-cols-4">
            {[["Multi-company", "Isolated workspaces"], ["8 roles", "Server-enforced"], ["7-stage", "Ticket workflow"], ["PWA", "Installable on mobile"]].map(([a, b]) => (
              <div key={a} className="bg-slate-950 px-4 py-4">
                <p className="font-heading text-lg font-black tracking-tight text-white">{a}</p>
                <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">{b}</p>
              </div>
            ))}
          </motion.div>
        </div>
      </section>

      {/* Features */}
      <section id="features" className="border-t border-white/10 bg-slate-900/40">
        <div className="mx-auto max-w-7xl px-5 py-20 lg:px-8">
          <motion.div {...fade}>
            <p className="text-[11px] font-bold uppercase tracking-[0.22em] text-amber-400">Product</p>
            <h2 className="mt-2 max-w-xl font-heading text-3xl font-black tracking-tighter text-white sm:text-4xl">One platform for the entire fleet operation</h2>
          </motion.div>
          <div className="mt-12 grid gap-px border border-white/10 bg-white/10 sm:grid-cols-2 lg:grid-cols-4">
            {FEATURES.map((f, i) => (
              <motion.div key={f.title} {...fade} transition={{ ...fade.transition, delay: (i % 4) * 0.06 }}
                className="group bg-slate-950 p-6 transition-colors hover:bg-slate-900">
                <f.icon className="h-6 w-6 text-amber-400" strokeWidth={1.8} />
                <h3 className="mt-4 text-base font-bold text-white">{f.title}</h3>
                <p className="mt-2 text-sm leading-relaxed text-slate-400">{f.text}</p>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* How it works */}
      <section id="how" className="border-t border-white/10">
        <div className="mx-auto max-w-7xl px-5 py-20 lg:px-8">
          <motion.div {...fade}>
            <p className="text-[11px] font-bold uppercase tracking-[0.22em] text-amber-400">How FleetFlow works</p>
            <h2 className="mt-2 max-w-xl font-heading text-3xl font-black tracking-tighter text-white sm:text-4xl">From sign-up to a fully running fleet office</h2>
          </motion.div>
          <div className="mt-12 grid gap-8 md:grid-cols-2 lg:grid-cols-4">
            {STEPS.map((s, i) => (
              <motion.div key={s.n} {...fade} transition={{ ...fade.transition, delay: i * 0.08 }} className="border-l-2 border-amber-400/50 pl-5">
                <p className="font-mono text-xs font-bold text-amber-400">{s.n}</p>
                <h3 className="mt-2 text-base font-bold text-white">{s.title}</h3>
                <p className="mt-2 text-sm leading-relaxed text-slate-400">{s.text}</p>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* Who it's for + Security */}
      <section id="who" className="border-t border-white/10 bg-slate-900/40">
        <div className="mx-auto grid max-w-7xl gap-14 px-5 py-20 lg:grid-cols-2 lg:px-8">
          <motion.div {...fade}>
            <p className="text-[11px] font-bold uppercase tracking-[0.22em] text-amber-400">Who it's for</p>
            <h2 className="mt-2 font-heading text-3xl font-black tracking-tighter text-white">Built for every kind of fleet</h2>
            <p className="mt-4 max-w-md text-sm leading-relaxed text-slate-400">
              Each organisation gets its own private workspace — users, vehicles, records, reports and settings are completely separate.
            </p>
            <ul className="mt-6 grid grid-cols-1 gap-2.5 sm:grid-cols-2">
              {AUDIENCES.map((a) => (
                <li key={a} className="flex items-center gap-2 text-sm text-slate-300">
                  <CheckCircle2 className="h-4 w-4 flex-shrink-0 text-amber-400" /> {a}
                </li>
              ))}
            </ul>
          </motion.div>
          <motion.div {...fade} transition={{ ...fade.transition, delay: 0.12 }} id="security" className="border border-white/10 bg-slate-950 p-8">
            <p className="text-[11px] font-bold uppercase tracking-[0.22em] text-amber-400">Security & accountability</p>
            <h2 className="mt-2 font-heading text-2xl font-black tracking-tighter text-white">Isolation enforced on the server</h2>
            <div className="mt-6 space-y-5">
              {[
                [Lock, "Organisation-level data isolation", "Every query is scoped to your workspace at the database layer — not just hidden in the interface."],
                [Building2, "Role-based permissions", "Create, edit, approve, close and delete rights are checked on the backend for all eight roles."],
                [FileSearch, "Audit-friendly records", "Ticket approvals, disposals, exits and status changes record who acted and when."],
                [Radio, "Session security", "Hashed passwords, expiring sessions and forced first-login password changes."],
              ].map(([Icon, t, d]) => (
                <div key={t} className="flex gap-4">
                  <span className="mt-0.5 grid h-9 w-9 flex-shrink-0 place-items-center border border-amber-400/30 bg-amber-400/10">
                    <Icon className="h-4 w-4 text-amber-400" />
                  </span>
                  <div>
                    <p className="text-sm font-bold text-white">{t}</p>
                    <p className="mt-1 text-sm leading-relaxed text-slate-400">{d}</p>
                  </div>
                </div>
              ))}
            </div>
          </motion.div>
        </div>
      </section>

      {/* Final CTA */}
      <section className="border-t border-white/10">
        <div className="mx-auto max-w-7xl px-5 py-20 lg:px-8">
          <motion.div {...fade} className="border border-amber-400/30 bg-gradient-to-r from-amber-400/10 to-transparent p-10 lg:p-14">
            <h2 className="max-w-2xl font-heading text-3xl font-black tracking-tighter text-white sm:text-4xl">
              Bring your fleet completely under control.
            </h2>
            <p className="mt-3 max-w-xl text-sm leading-relaxed text-slate-400">
              Set up your organisation's workspace in minutes, or explore the demo environment with realistic sample data first.
            </p>
            <div className="mt-7 flex flex-wrap gap-4">
              <Link to="/get-started" data-testid="cta-get-started-btn">
                <Button className="rounded-none bg-amber-400 px-7 py-6 text-sm font-bold text-slate-950 hover:bg-amber-300">
                  Get Started <ArrowRight className="ml-2 h-4 w-4" />
                </Button>
              </Link>
              <Link to="/demo" data-testid="cta-demo-btn">
                <Button variant="outline" className="rounded-none border-white/25 bg-transparent px-7 py-6 text-sm font-bold text-white hover:bg-white/10 hover:text-white">
                  Try FleetFlow Demo
                </Button>
              </Link>
            </div>
          </motion.div>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-white/10">
        <div className="mx-auto flex max-w-7xl flex-col gap-6 px-5 py-10 sm:flex-row sm:items-center sm:justify-between lg:px-8">
          <BrandMark dark />
          <div className="flex flex-wrap gap-x-8 gap-y-2 text-sm text-slate-400">
            <a href="#features" className="hover:text-white">Features</a>
            <a href="#how" className="hover:text-white">How it works</a>
            <Link to="/demo" className="hover:text-white">Demo</Link>
            <Link to="/login" className="hover:text-white">Login</Link>
            <Link to="/get-started" className="hover:text-white">Get Started</Link>
          </div>
          <p className="text-xs text-slate-500">© 2026 FleetFlow · Complete Fleet Operations Management</p>
        </div>
      </footer>
    </div>
  );
}
