import { useEffect, useState } from "react";
import "./aurora-background.css";

// Reuses the supplied aurora gradients and mask, without its <main> / flex
// wrapper: this is decoration only and must not reflow the existing app.
export function AuroraBackground({ showRadialGradient = true }: { showRadialGradient?: boolean }) {
  const [paused, setPaused] = useState(() => document.hidden);

  useEffect(() => {
    const updateVisibility = () => setPaused(document.hidden);
    updateVisibility();
    document.addEventListener("visibilitychange", updateVisibility);
    return () => document.removeEventListener("visibilitychange", updateVisibility);
  }, []);

  return (
    <div className="aurora-background" aria-hidden="true" data-paused={paused ? "" : undefined}>
      <div className={`aurora-background-field${showRadialGradient ? " aurora-background-masked" : ""}`} />
    </div>
  );
}
