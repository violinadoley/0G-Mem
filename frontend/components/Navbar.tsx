"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAccount } from "wagmi";
import WalletButton from "./WalletButton";
import { cn } from "@/lib/utils";

const NAV_LINKS = [
  { href: "/memory", label: "Memory" },
  { href: "/audit", label: "Audit" },
  { href: "/access", label: "Access" },
  { href: "/verify", label: "Verify" },
  { href: "/deploy", label: "Deploy" },
];

export default function Navbar() {
  const pathname = usePathname();
  const { isConnected } = useAccount();

  return (
    <header className="sticky top-0 z-50 border-b border-border bg-background/90 backdrop-blur-sm">
      <nav className="max-w-7xl mx-auto px-4 sm:px-6 flex items-center justify-between h-16">
        {/* Logo */}
        <Link href="/" className="flex items-center gap-2.5 group">
          <div className="w-8 h-8 rounded-lg bg-accent flex items-center justify-center">
            <span className="text-white font-bold text-sm">0g</span>
          </div>
          <span className="font-semibold text-white text-lg tracking-tight">
            Mem
          </span>
        </Link>

        {/* Nav links — only shown when connected */}
        {isConnected && (
          <div className="hidden sm:flex items-center gap-1">
            {NAV_LINKS.map(({ href, label }) => (
              <Link
                key={href}
                href={href}
                className={cn(
                  "px-3 py-1.5 rounded-lg text-sm font-medium transition-colors",
                  pathname === href
                    ? "bg-accent/10 text-accent"
                    : "text-muted hover:text-white hover:bg-surface-raised"
                )}
              >
                {label}
              </Link>
            ))}
          </div>
        )}

        {/* Verify + Deploy always accessible (entry points for new users) */}
        {!isConnected && (
          <div className="hidden sm:flex items-center gap-1">
            <Link
              href="/verify"
              className={cn(
                "px-3 py-1.5 rounded-lg text-sm font-medium transition-colors",
                pathname === "/verify"
                  ? "bg-accent/10 text-accent"
                  : "text-muted hover:text-white hover:bg-surface-raised"
              )}
            >
              Verify Proof
            </Link>
            <Link
              href="/deploy"
              className={cn(
                "px-3 py-1.5 rounded-lg text-sm font-medium transition-colors",
                pathname === "/deploy"
                  ? "bg-accent/10 text-accent"
                  : "text-accent hover:bg-accent/10"
              )}
            >
              Deploy →
            </Link>
          </div>
        )}

        <WalletButton />
      </nav>
    </header>
  );
}
