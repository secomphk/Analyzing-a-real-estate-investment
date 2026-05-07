import { Suspense, lazy } from "react";
import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import { Building2, Map, MapPinned, Sparkles, Store } from "lucide-react";

import { FullPageLoader } from "@/components/states/Loading";
import { cn } from "@/lib/cn";

const OverviewPage = lazy(() => import("@/pages/OverviewPage"));
const ScenarioAPage = lazy(() => import("@/pages/ScenarioAPage"));
const ScenarioBPage = lazy(() => import("@/pages/ScenarioBPage"));
const ScenarioCPage = lazy(() => import("@/pages/ScenarioCPage"));
const RecommendPage = lazy(() => import("@/pages/RecommendPage"));

const NAV_ITEMS = [
  { to: "/", label: "개요", Icon: Map, end: true },
  { to: "/scenario-a", label: "시나리오 A", Icon: Building2, end: false },
  { to: "/scenario-b", label: "시나리오 B", Icon: MapPinned, end: false },
  { to: "/scenario-c", label: "시나리오 C", Icon: Store, end: false },
  { to: "/recommend", label: "추천", Icon: Sparkles, end: false },
] as const;

export default function App() {
  return (
    <div className="min-h-screen bg-slate-50">
      <Header />
      <main className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8">
        <Suspense fallback={<FullPageLoader />}>
          <Routes>
            <Route path="/" element={<OverviewPage />} />
            <Route path="/scenario-a" element={<ScenarioAPage />} />
            <Route path="/scenario-b" element={<ScenarioBPage />} />
            <Route path="/scenario-c" element={<ScenarioCPage />} />
            <Route path="/recommend" element={<RecommendPage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </Suspense>
      </main>
    </div>
  );
}

function Header() {
  return (
    <header className="sticky top-0 z-30 border-b border-slate-200 bg-white/80 backdrop-blur">
      <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-3 sm:px-6 lg:px-8">
        <NavLink to="/" className="flex items-center gap-2">
          <div className="grid h-9 w-9 place-items-center rounded-lg bg-gradient-to-br from-emerald-500 to-teal-500 text-white">
            <Building2 className="h-5 w-5" />
          </div>
          <div className="leading-tight">
            <p className="text-sm font-semibold text-slate-900">RealEstate Analyzer</p>
            <p className="text-xs text-slate-500">시나리오 A·B·C 통합 분석</p>
          </div>
        </NavLink>
        <nav className="hidden items-center gap-1 md:flex" aria-label="Primary">
          {NAV_ITEMS.map(({ to, label, Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                cn(
                  "inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium",
                  isActive
                    ? "bg-slate-900 text-white"
                    : "text-slate-600 hover:bg-slate-100",
                )
              }
            >
              <Icon className="h-4 w-4" />
              {label}
            </NavLink>
          ))}
        </nav>
      </div>
      <nav
        className="flex items-center gap-1 overflow-x-auto border-t border-slate-100 px-3 py-2 md:hidden"
        aria-label="Primary mobile"
      >
        {NAV_ITEMS.map(({ to, label, Icon, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            className={({ isActive }) =>
              cn(
                "inline-flex items-center gap-1.5 whitespace-nowrap rounded-full px-3 py-1.5 text-xs font-medium",
                isActive
                  ? "bg-slate-900 text-white"
                  : "bg-slate-100 text-slate-600",
              )
            }
          >
            <Icon className="h-3.5 w-3.5" />
            {label}
          </NavLink>
        ))}
      </nav>
    </header>
  );
}
