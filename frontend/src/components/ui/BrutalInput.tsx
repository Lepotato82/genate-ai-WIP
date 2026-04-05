"use client";

import React from "react";

interface BrutalInputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
}

export function BrutalInput({
  label,
  error,
  className = "",
  id,
  ...props
}: BrutalInputProps) {
  const inputId = id ?? label?.toLowerCase().replace(/\s+/g, "-");

  return (
    <div className="flex flex-col gap-1.5 w-full">
      {label && (
        <label
          htmlFor={inputId}
          className="font-heading font-bold text-xs uppercase tracking-widest text-black"
        >
          {label}
        </label>
      )}
      <input
        id={inputId}
        className={`
          border-3 border-black bg-white w-full px-4 py-3
          font-body text-base text-black placeholder-gray-400
          shadow-brutal
          transition-all duration-75
          focus:outline-none focus:-translate-x-0.5 focus:-translate-y-0.5 focus:shadow-brutal-sm
          ${error ? "border-brutal-orange" : ""}
          ${className}
        `}
        {...props}
      />
      {error && (
        <p className="text-brutal-orange text-xs font-heading font-bold uppercase">
          {error}
        </p>
      )}
    </div>
  );
}
