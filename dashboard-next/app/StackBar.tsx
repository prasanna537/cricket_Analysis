"use client";

import { useRef, useState } from "react";

export type Part = { label: string; value: number; color: string };

// Diverging stacked bar: positive parts stack right of zero, negative parts left. Scale is shared across rows.
export default function StackBar({ parts, lo, hi, aria }: { parts: Part[]; lo: number; hi: number; aria: string }) {
  const W = 400, H = 14;
  const x = (v: number) => ((v - lo) / (hi - lo)) * (W - 2) + 1;
  const box = useRef<HTMLDivElement>(null);
  const [tip, setTip] = useState<{ text: string; left: number } | null>(null);
  let p = 0, n = 0;
  const rects = parts.map((q, i) => {
    const v = q.value || 0;
    const a0 = v >= 0 ? p : n + v, a1 = v >= 0 ? p + v : n;
    if (v >= 0) p += v; else n += v;
    return (
      <rect
        key={i}
        x={x(a0)}
        y={0}
        width={Math.max(1, x(a1) - x(a0))}
        height={H}
        fill={q.color}
        onPointerMove={(e) => {
          const r = box.current!.getBoundingClientRect();
          setTip({ text: `${q.label} ${v >= 0 ? "+" : ""}${v.toFixed(2)}`, left: Math.max(0, Math.min(r.width - 170, e.clientX - r.left - 40)) });
        }}
        onPointerLeave={() => setTip(null)}
      />
    );
  });
  return (
    <div className="bar" ref={box}>
      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" role="img" aria-label={aria}>
        {rects}
        <line x1={x(0)} x2={x(0)} y1={0} y2={H} stroke="var(--axis)" strokeWidth={1} vectorEffect="non-scaling-stroke" />
      </svg>
      {tip && <div className="tip" style={{ left: tip.left }}>{tip.text}</div>}
    </div>
  );
}
