interface BarLoaderProps {
  bars?: number;
  barWidth?: number;
  barHeight?: number;
  color?: string;
  speed?: number;
  className?: string;
}

export default function BarLoader({
  bars = 8,
  barWidth = 4,
  barHeight = 30,
  color = "#6f9ed8",
  speed = 1.2,
  className = "",
}: BarLoaderProps) {
  const isHexColor = color.startsWith("#");
  return <div className={`bar-loader relative flex items-end justify-center gap-1 ${className}`} aria-hidden="true">
    {Array.from({ length: bars }).map((_, index) => <i
      key={index}
      className={`${isHexColor ? "" : color} animate-barLoader block origin-bottom rounded-t-xl`}
      style={{
        width: `${barWidth}px`,
        height: `${barHeight}px`,
        backgroundColor: isHexColor ? color : undefined,
        animationDelay: `${(index + 1) * .1}s`,
        animationDuration: `${speed}s`,
      }}
    />)}
  </div>;
}
