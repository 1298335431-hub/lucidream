"use client";

import type { ComponentProps } from "react";
import { ArrowRight } from "lucide-react";
import "./flow-button.css";

type FlowButtonProps = Omit<ComponentProps<"button">, "children"> & {
  text?: string;
  loading?: boolean;
};

export function FlowButton({
  text = "Modern Button",
  loading = false,
  className = "",
  type = "button",
  ...props
}: FlowButtonProps) {
  return (
    <button type={type} className={`flow-button${loading ? " is-loading" : ""} ${className}`} {...props}>
      {loading ? (
        <>
          <span className="flow-button-loading-orbit" aria-hidden="true"><i /></span>
          <span className="flow-button-loading-text" role="status" aria-live="polite">
            {text}<span className="flow-button-loading-dots" aria-hidden="true"><i /><i /><i /></span>
          </span>
          <span className="flow-button-loading-sheen" aria-hidden="true" />
        </>
      ) : (
        <>
          <ArrowRight className="flow-button-arrow flow-button-arrow-in" aria-hidden="true" />
          <span className="flow-button-text">{text}</span>
          <span className="flow-button-fill" aria-hidden="true" />
          <ArrowRight className="flow-button-arrow flow-button-arrow-out" aria-hidden="true" />
        </>
      )}
    </button>
  );
}

export default FlowButton;
