import { motion } from "framer-motion";

interface WhirlpoolLoaderProps {
  segments?: number;
  rotations?: number;
  color?: string;
  size?: number | string;
}

export default function WhirlpoolLoader({
  segments = 60,
  rotations = 6,
  color = "#7394b7",
  size = "100%",
}: WhirlpoolLoaderProps) {
  const computedSize = typeof size === "number" ? `${size}px` : size;

  return <div className="whirlpool-loader flex h-full w-full items-center justify-center">
    <svg width={computedSize} height={computedSize} viewBox="-100 -100 200 200" preserveAspectRatio="xMidYMid meet" className="h-auto w-full max-h-[30vh] max-w-[30vw]">
      <motion.g animate={{ rotate: 360 }} transition={{ duration: 20, repeat: Infinity, ease: "linear" }}>
        {Array.from({ length: segments }).map((_, index) => {
          const angle = (index / segments) * Math.PI * 2 * rotations;
          const radius = 5 + (90 * index) / segments;
          return <motion.circle
            key={index}
            cx={Math.cos(angle) * radius}
            cy={Math.sin(angle) * radius}
            r={2 + (index / segments) * 3}
            fill={color}
            initial={{ scale: 0, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            transition={{ duration: .5, delay: (index / segments) * 2, repeat: Infinity, repeatType: "reverse", repeatDelay: 1 }}
          />;
        })}
      </motion.g>
    </svg>
  </div>;
}

export const Component = () => <div className="flex min-h-screen w-full items-center justify-center bg-black p-4"><div className="w-[60vw] max-w-[400px] sm:max-w-[500px] md:max-w-[600px]"><WhirlpoolLoader color="#22d3ee" /></div></div>;
