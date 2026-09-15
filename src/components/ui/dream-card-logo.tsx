import type { ComponentProps } from "react";
import "./dream-card-logo.css";

type DreamCardLogoProps = ComponentProps<"svg"> & {
  animated?: boolean;
  tone?: "web" | "card";
};

/**
 * 梦卡的唯一图形标记：星光、月亮卡和后置卡。
 * 网页端可播放一次轻量入场动画；导出卡固定使用静态版本。
 */
export function DreamCardLogo({
  animated = false,
  tone = "web",
  className = "",
  ...props
}: DreamCardLogoProps) {
  const isWeb = tone === "web";
  const palette = tone === "card"
    ? { back: "#9c968d", front: "#e4dfd6", accent: "#c8c1b5", line: "#b4aea5" }
    : { back: "#a0b8e0", front: "#ffffff", accent: "#8094cc", line: "#c0ccec" };

  return (
    <svg
      className={`dream-card-logo dream-card-logo--${tone} ${animated ? "is-animated" : ""} ${className}`}
      viewBox="0 0 320 360"
      role="img"
      aria-label="梦卡图形标记"
      {...props}
    >
      <defs>
        <mask id={`dream-card-logo-moon-${tone}`}>
          <circle cx="0" cy="0" r="22" fill="white" />
          <circle cx="10" cy="-6" r="17" fill="black" />
        </mask>
        <filter id={`dream-card-logo-shadow-${tone}`} x="-25%" y="-18%" width="150%" height="140%">
          <feDropShadow dx="0" dy="10" stdDeviation="16" floodColor="#8878c0" floodOpacity="0.22" />
          <feDropShadow dx="0" dy="2" stdDeviation="4" floodColor="#000" floodOpacity="0.05" />
        </filter>
        <linearGradient id={`dream-card-logo-back-${tone}`} x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#a0b8e0" />
          <stop offset="100%" stopColor="#b8a8d8" />
        </linearGradient>
        <linearGradient id={`dream-card-logo-front-${tone}`} x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#ffffff" />
          <stop offset="100%" stopColor="#eee8fa" />
        </linearGradient>
        <linearGradient id={`dream-card-logo-moon-gradient-${tone}`} x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#8094cc" />
          <stop offset="100%" stopColor="#a888cc" />
        </linearGradient>
        <linearGradient id={`dream-card-logo-star-${tone}`} x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#b0c0e0" />
          <stop offset="100%" stopColor="#c0a8e0" />
        </linearGradient>
      </defs>
      <g transform="translate(180 195)">
        <g className="dream-card-logo__back">
          <rect x="-66" y="-96" width="132" height="192" rx="18" className="dream-card-logo__back-fill" style={{ fill: isWeb ? `url(#dream-card-logo-back-${tone})` : palette.back }} />
        </g>
      </g>
      <g transform="translate(152 190)">
        <g className="dream-card-logo__front" filter={tone === "card" ? undefined : `url(#dream-card-logo-shadow-${tone})`}>
          <rect x="-66" y="-96" width="132" height="192" rx="18" className="dream-card-logo__front-fill" style={{ fill: isWeb ? `url(#dream-card-logo-front-${tone})` : palette.front }} />
          <g transform="translate(0 -58)">
            <circle cx="0" cy="0" r="22" className="dream-card-logo__moon" style={{ fill: isWeb ? `url(#dream-card-logo-moon-gradient-${tone})` : palette.accent }} mask={`url(#dream-card-logo-moon-${tone})`} />
          </g>
          <rect x="-40" y="-22" width="80" height="7" rx="3.5" className="dream-card-logo__line dream-card-logo__line--primary" style={{ fill: palette.line }} />
          <rect x="-40" y="-8" width="54" height="5" rx="2.5" className="dream-card-logo__line dream-card-logo__line--secondary" style={{ fill: palette.line }} />
        </g>
      </g>
      <g transform="translate(80 82)">
        <g className="dream-card-logo__star">
          <path d="M0,-24 L5.4,-5.4 L24,0 L5.4,5.4 L0,24 L-5.4,5.4 L-24,0 L-5.4,-5.4 Z" className="dream-card-logo__star-fill" style={{ fill: isWeb ? `url(#dream-card-logo-star-${tone})` : palette.accent }} />
        </g>
      </g>
    </svg>
  );
}

export default DreamCardLogo;
