"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const LINKS = [
  { href: "/", label: "Dashboard" },
  { href: "/methodology", label: "Methodology" },
  { href: "/strategy", label: "Auction strategy" },
];

export default function TopBar() {
  const path = usePathname();
  return (
    <div className="topbar">
      <div className="topbar-in">
        <span className="brand">SuperRR Selector · Round 1</span>
        <nav aria-label="Pages">
          {LINKS.map((l) => (
            <Link key={l.href} href={l.href} className={path === l.href ? "on" : ""} aria-current={path === l.href ? "page" : undefined}>
              {l.label}
            </Link>
          ))}
        </nav>
      </div>
    </div>
  );
}
