import React from "react";
import "./Machine.css";

export function NeonLoader({ size = 120 }) {
  return (
    <div className="loader-container">
      <svg className="neon-spinner" width={size} height={size} viewBox="0 0 50 50">
        <circle
          className="spinner-bg"
          cx="25"
          cy="25"
          r="20"
          strokeWidth="4"
        />
        <circle
          className="spinner"
          cx="25"
          cy="25"
          r="20"
          strokeWidth="4"
        />
      </svg>
      <p className="loader-text">Connecting...</p>
    </div>
  );
}
