// src/components/ui/card.jsx
import React from "react";

export function Card({ className = "", children, ...props }) {
  return (
    <div
      className={`rounded-2xl shadow-sm bg-white p-4 border border-gray-200 ${className}`}
      {...props}
    >
      {children}
    </div>
  );
}

export function CardHeader({ className = "", children }) {
  return <div className={`text-lg font-semibold text-gray-900 mb-2 ${className}`}>{children}</div>;
}

export function CardContent({ className = "", children }) {
  return <div className={`text-sm text-gray-800 ${className}`}>{children}</div>;
}

export function CardFooter({ className = "", children }) {
  return <div className={`mt-2 ${className}`}>{children}</div>;
}
