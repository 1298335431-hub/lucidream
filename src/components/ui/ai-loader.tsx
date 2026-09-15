import type { CSSProperties } from "react";
import "./ai-loader.css";

interface LoaderProps {
  size?: number;
  text?: string;
}

// Embedded in the card rather than a fixed overlay covering the workspace.
export default function AiLoader({ size = 180, text = "Generating" }: LoaderProps) {
  return <div className="ai-loader" style={{ width: size, height: size } as CSSProperties}>
    <span className="ai-loader-letters">
      {Array.from(text).map((letter, index) => <span key={index} style={{ animationDelay: `${index * 0.1}s` }}>{letter}</span>)}
    </span>
    <div className="ai-loader-circle" aria-hidden="true" />
  </div>;
}

export { AiLoader as Component };
