import { NavLink, Outlet } from "react-router-dom";
import {
  BarChart3,
  Inbox as InboxIcon,
  Upload as UploadIcon,
  History,
  Users,
} from "lucide-react";
import { cn } from "@/lib/utils";

const NAV = [
  { to: "/", label: "Overview", icon: BarChart3, end: true },
  { to: "/inbox", label: "Inbox", icon: InboxIcon },
  { to: "/leads", label: "Leads", icon: Users },
  { to: "/runs", label: "Runs", icon: History },
  { to: "/upload", label: "Upload", icon: UploadIcon },
];

export function Layout() {
  return (
    <div className="flex h-full">
      <aside className="w-56 bg-white border-r border-slate-200 flex flex-col">
        <div className="px-5 py-5 border-b border-slate-200">
          <div className="font-semibold text-slate-900">EliseAI</div>
          <div className="text-xs text-slate-500">Lead Pipeline</div>
        </div>
        <nav className="p-3 flex flex-col gap-1">
          {NAV.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-3 px-3 py-2 rounded-md text-sm",
                  isActive
                    ? "bg-blue-50 text-blue-700 font-medium"
                    : "text-slate-600 hover:bg-slate-50"
                )
              }
            >
              <Icon className="w-4 h-4" />
              <span>{label}</span>
            </NavLink>
          ))}
        </nav>
        <div className="mt-auto p-3 text-[11px] text-slate-400">
          v0.1.0 · {import.meta.env.MODE}
        </div>
      </aside>
      <main className="flex-1 overflow-y-auto">
        <Outlet />
      </main>
    </div>
  );
}
