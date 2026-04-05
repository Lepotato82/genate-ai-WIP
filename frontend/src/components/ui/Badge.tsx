import React from "react";

type BadgeVariant = "start" | "complete" | "error" | "pending" | "default";

const VARIANT_CLASSES: Record<BadgeVariant, string> = {
  start: "bg-white border-black text-black animate-pulse",
  complete: "bg-brutal-yellow border-black text-black",
  error: "bg-brutal-orange border-black text-white",
  pending: "bg-white border-gray-400 text-gray-400",
  default: "bg-white border-black text-black",
};

interface BadgeProps {
  label: string;
  variant?: BadgeVariant;
  className?: string;
}

export function Badge({ label, variant = "default", className = "" }: BadgeProps) {
  return (
    <span
      className={`
        inline-block border-3 px-2 py-0.5
        font-heading font-bold text-xs uppercase tracking-wide
        ${VARIANT_CLASSES[variant]}
        ${className}
      `}
    >
      {label}
    </span>
  );
}

export function statusToBadgeVariant(status: string): BadgeVariant {
  if (status === "complete") return "complete";
  if (status === "start") return "start";
  if (status === "error") return "error";
  return "default";
}
