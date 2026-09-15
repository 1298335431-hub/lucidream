import type { LucideIcon } from "lucide-react";
import { motion } from "motion/react";
import "./tubelight-navbar.css";

export type TubelightNavItem = {
  name: string;
  value: string;
  icon: LucideIcon;
};

type TubelightNavBarProps = {
  items: TubelightNavItem[];
  activeValue: string;
  onSelect: (value: string) => void;
  className?: string;
};

export function TubelightNavBar({ items, activeValue, onSelect, className = "" }: TubelightNavBarProps) {
  return (
    <nav className={`tubelight-nav ${className}`.trim()} aria-label="登录后主导航">
      {items.map((item) => {
        const Icon = item.icon;
        const active = activeValue === item.value;
        return (
          <button
            type="button"
            key={item.value}
            className={active ? "is-active" : ""}
            aria-current={active ? "page" : undefined}
            aria-label={item.name}
            onClick={() => onSelect(item.value)}
          >
            <span className="tubelight-nav-label">{item.name}</span>
            <Icon className="tubelight-nav-icon" size={17} strokeWidth={1.8} aria-hidden="true" />
            {active && (
              <motion.span
                layoutId="authenticated-nav-lamp"
                className="tubelight-active"
                transition={{ type: "spring", stiffness: 300, damping: 30 }}
                aria-hidden="true"
              >
                <i className="tubelight-line" />
                <i className="tubelight-glow tubelight-glow-wide" />
                <i className="tubelight-glow tubelight-glow-mid" />
                <i className="tubelight-glow tubelight-glow-core" />
              </motion.span>
            )}
          </button>
        );
      })}
    </nav>
  );
}
