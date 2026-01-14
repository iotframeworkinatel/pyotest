// src/components/ui/card.jsx
import React from "react";

export function Card({ className = "", children, ...props }) {
  return (
    <div
      className={`rounded-2xl shadow-md bg-white dark:bg-zinc-900 p-4 border border-zinc-200 dark:border-zinc-800 ${className}`}
      {...props}
    >
      {children}
    </div>
  );
}

export function CardHeader({ className = "", children }) {
  return <div className={`text-lg font-semibold mb-2 ${className}`}>{children}</div>;
}

export function CardContent({ className = "", children }) {
  return <div className={`text-sm text-gray-700 dark:text-gray-300 ${className}`}>{children}</div>;
}

export function CardFooter({ className = "", children }) {
  return <div className={`mt-2 ${className}`}>{children}</div>;
}
