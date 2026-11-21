"use client";

import * as React from "react";
import Link from "next/link";
import Image from "next/image";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  Activity,
  Radio,
  Globe2,
  FileCode2,
  Webhook,
  Settings,
  Shield,
  Building2,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Drawer } from "@/components/ui/drawer";
import { HamburgerToggle } from "@/components/ui/hamburger-toggle";
import { OrganizationSwitcher } from "@/components/organization/OrganizationSwitcher";

const navItems = [
  { href: "/dashboard", label: "Events", icon: LayoutDashboard },
  { href: "/performance", label: "Performance", icon: Activity },
  { href: "/dashboard/ha", label: "Multi-Region", icon: Globe2 },
  { href: "/live", label: "Live Stream", icon: Radio },
  { href: "/contracts", label: "Contracts", icon: FileCode2 },
  { href: "/webhooks", label: "Webhooks", icon: Webhook },
  { href: "/organization", label: "Org", icon: Building2 },
  { href: "/admin", label: "Admin", icon: Shield },
  { href: "/settings", label: "Settings", icon: Settings },
] as const;

interface AppShellProps {
  children: React.ReactNode;
}

/**
 * Resolve which nav entry the current route belongs to.
 *
 * Nested routes (e.g. /dashboard/ha) match more than one entry by prefix, so
 * the longest match wins and only one link is marked as the current page.
 */
function resolveActiveHref(pathname: string): string | undefined {
  return navItems
    .map((item) => item.href as string)
    .filter((href) => pathname === href || pathname.startsWith(`${href}/`))
    .sort((a, b) => b.length - a.length)[0];
}

function NavLink({
  href,
  label,
  icon: Icon,
  isActive,
  onNavigate,
}: {
  href: string;
  label: string;
  icon: React.ComponentType<{ size?: number; className?: string }>;
  isActive: boolean;
  onNavigate?: () => void;
}) {
  return (
    <Link
      href={href}
      onClick={onNavigate}
      aria-current={isActive ? "page" : undefined}
      className={cn(
        "flex items-center gap-3 min-h-[44px] px-4 py-2 text-sm font-terminal-mono transition-colors rounded-sm",
        "border-l-4 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-terminal-green",
        isActive
          ? "border-terminal-green bg-terminal-green/10 text-terminal-green shadow-[0_0_12px_rgba(0,255,65,0.15)] dark:border-terminal-green dark:bg-terminal-green/10 dark:text-terminal-green"
          : "border-transparent text-terminal-gray hover:text-terminal-green hover:bg-terminal-green/5 hover:border-terminal-green/40",
      )}
    >
      <Icon size={18} aria-hidden="true" />
      {label}
    </Link>
  );
}

function SidebarNav({
  pathname,
  onNavigate,
  className,
}: {
  pathname: string;
  onNavigate?: () => void;
  className?: string;
}) {
  const activeHref = resolveActiveHref(pathname);

  return (
    <nav
      className={cn("flex flex-col gap-1", className)}
      aria-label="App navigation"
    >
      {navItems.map((item) => (
        <NavLink
          key={item.href}
          {...item}
          isActive={item.href === activeHref}
          onNavigate={onNavigate}
        />
      ))}
    </nav>
  );
}

export function AppShell({ children }: AppShellProps) {
  const pathname = usePathname();
  const [sidebarOpen, setSidebarOpen] = React.useState(false);

  React.useEffect(() => {
    setSidebarOpen(false);
  }, [pathname]);

  return (
    <div className="min-h-screen bg-terminal-black text-terminal-green font-terminal-mono transition-colors duration-200">
      {/* Top header */}
      <header className="sticky top-0 z-30 flex h-[60px] items-center gap-3 border-b border-terminal-green/20 bg-terminal-black/95 backdrop-blur-md px-4">
        <HamburgerToggle
          isOpen={sidebarOpen}
          onClick={() => setSidebarOpen((open) => !open)}
          ariaControls="app-sidebar"
          className="sm:hidden shrink-0"
        />

        <Link
          href="/dashboard"
          className="flex items-center gap-2 min-h-[44px] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#00e5ff]"
        >
          <Image
            src="/soroscan-logo-dark.png"
            alt="SoroScan Logo"
            width={130}
            height={32}
            className="h-8 w-auto object-contain"
            priority
          />
        </Link>

        <div className="ml-auto flex items-center gap-2">
          <OrganizationSwitcher className="hidden sm:block" />

          <nav className="hidden sm:flex items-center gap-1" aria-label="Header navigation">
            {navItems.map((item) => {
              const isActive =
                pathname === item.href || pathname.startsWith(`${item.href}/`);
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  aria-current={isActive ? "page" : undefined}
                  className={cn(
                    "min-h-[44px] min-w-[44px] inline-flex items-center justify-center px-3 text-xs uppercase tracking-wider transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-terminal-green",
                    isActive
                      ? "text-terminal-green border-b-2 border-terminal-green"
                      : "text-terminal-gray hover:text-terminal-green",
                  )}
                >
                  {item.label}
                </Link>
              );
            })}
          </nav>
        </div>
      </header>

      <div className="flex">
        {/* Desktop sidebar — always visible ≥640px */}
        <aside
          id="app-sidebar"
          className="hidden sm:block w-60 shrink-0 border-r border-terminal-green/20 bg-terminal-black/95 min-h-[calc(100vh-60px)] p-4"
          aria-label="Sidebar navigation"
        >
          <SidebarNav pathname={pathname} />
        </aside>

        {/* Mobile sidebar drawer */}
        <Drawer
          isOpen={sidebarOpen}
          onClose={() => setSidebarOpen(false)}
          position="left"
          title="Navigation"
          className="sm:hidden"
        >
          <SidebarNav
            pathname={pathname}
            onNavigate={() => setSidebarOpen(false)}
          />
        </Drawer>

        <div className="flex-1 min-w-0">
          {children}
        </div>
      </div>
    </div>
  );
}
