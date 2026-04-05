"use client";

import React from "react";

interface BrutalButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "ghost";
  size?: "sm" | "md" | "lg";
}

export function BrutalButton({
  variant = "primary",
  size = "md",
  className = "",
  children,
  disabled,
  ...props
}: BrutalButtonProps) {
  const base =
    "font-heading font-bold uppercase tracking-wide border-3 border-black transition-all duration-75 active:translate-x-0.5 active:translate-y-0.5 active:shadow-none inline-flex items-center justify-center gap-2 cursor-pointer";

  const variants = {
    primary: "bg-brutal-yellow text-black shadow-brutal hover:-translate-x-0.5 hover:-translate-y-0.5 hover:shadow-brutal-sm",
    secondary: "bg-white text-black shadow-brutal hover:-translate-x-0.5 hover:-translate-y-0.5 hover:shadow-brutal-sm",
    ghost: "bg-transparent text-black border-black shadow-none hover:bg-brutal-yellow",
  };

  const sizes = {
    sm: "px-3 py-1.5 text-xs",
    md: "px-5 py-2.5 text-sm",
    lg: "px-7 py-3.5 text-base",
  };

  const disabledClasses = disabled
    ? "opacity-40 cursor-not-allowed translate-x-0 translate-y-0 shadow-brutal-sm pointer-events-none"
    : "";

  return (
    <button
      {...props}
      disabled={disabled}
      className={`${base} ${variants[variant]} ${sizes[size]} ${disabledClasses} ${className}`}
    >
      {children}
    </button>
  );
}
