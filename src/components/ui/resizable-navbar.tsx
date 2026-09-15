"use client";
import { IconMenu2, IconX } from "@tabler/icons-react";
import { AnimatePresence, motion, useMotionValueEvent, useScroll } from "motion/react";
import React, { useRef, useState } from "react";
import { cn } from "@/lib/utils";

interface NavbarProps { children: React.ReactNode; className?: string; }
interface NavBodyProps { children: React.ReactNode; className?: string; visible?: boolean; }
interface NavItemsProps { items: { name: string; link: string }[]; activeLink?: string; className?: string; onItemClick?: (link: string) => void; }
interface MobileNavProps { children: React.ReactNode; className?: string; visible?: boolean; }
interface MobileNavHeaderProps { children: React.ReactNode; className?: string; }
interface MobileNavMenuProps { children: React.ReactNode; className?: string; isOpen: boolean; onClose: () => void; }

export const Navbar = ({ children, className }: NavbarProps) => {
  const { scrollY } = useScroll();
  const [visible, setVisible] = useState(false);
  useMotionValueEvent(scrollY, "change", (latest) => setVisible(latest > 100));
  return <motion.div className={cn("relative w-full", className)}>{React.Children.map(children, (child) => React.isValidElement(child) ? React.cloneElement(child as React.ReactElement<{ visible?: boolean }>, { visible }) : child)}</motion.div>;
};

export const NavBody = ({ children, className, visible }: NavBodyProps) => <motion.div animate={{ boxShadow: visible ? "inset 0 1px 0 rgba(255,255,255,.96), 0 18px 42px rgba(73,91,126,.16)" : "inset 0 1px 0 rgba(255,255,255,.96), 0 10px 26px rgba(73,91,126,.10)", width: visible ? "min(760px, calc(100% - 32px))" : "min(1080px, calc(100% - 48px))", y: visible ? 14 : 0 }} transition={{ type: "spring", stiffness: 200, damping: 50 }} className={cn("relative z-10 mx-auto hidden flex-row items-center justify-between rounded-full border border-[#dce6f4] bg-[#f3f7fd]/95 px-4 py-2 lg:flex", visible && "bg-[#eef4fc]", className)}>{children}</motion.div>;

export const NavItems = ({ items, activeLink, className, onItemClick }: NavItemsProps) => {
  const [hovered, setHovered] = useState<number | null>(null);
  const highlighted = hovered ?? items.findIndex((item) => item.link === activeLink);
  return <motion.div onMouseLeave={() => setHovered(null)} className={cn("relative z-10 flex min-w-0 flex-1 flex-row items-center justify-center gap-5 text-sm font-normal text-[#686868]", className)}>{items.map((item, idx) => <a key={item.name} href={item.link} aria-current={item.link === activeLink ? "page" : undefined} onMouseEnter={() => setHovered(idx)} onClick={(event) => { event.preventDefault(); onItemClick?.(item.link); }} className={cn("relative whitespace-nowrap px-2 py-2 transition-colors hover:text-[#485d7d]", item.link === activeLink && "font-medium text-[#354d70]")}>{highlighted === idx && <motion.div layoutId="lucidream-nav-highlight" className="lucidream-nav-crystal absolute inset-0 rounded-full" transition={{ type: "spring", stiffness: 280, damping: 30 }} />}<span className="relative z-10">{item.name}</span></a>)}</motion.div>;
};

export const MobileNav = ({ children, className, visible }: MobileNavProps) => <motion.div animate={{ backdropFilter: visible ? "blur(12px)" : "blur(0px)", boxShadow: visible ? "0 14px 36px rgba(67,55,90,.09)" : "none", y: visible ? 8 : 0 }} transition={{ type: "spring", stiffness: 200, damping: 50 }} className={cn("relative z-10 mx-auto flex w-full flex-col bg-white/72 px-0 py-3 lg:hidden", visible && "rounded-2xl bg-white/84 px-3", className)}>{children}</motion.div>;
export const MobileNavHeader = ({ children, className }: MobileNavHeaderProps) => <div className={cn("flex w-full flex-row items-center justify-between", className)}>{children}</div>;
export const MobileNavMenu = ({ children, className, isOpen, onClose }: MobileNavMenuProps) => <AnimatePresence>{isOpen && <motion.div initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }} className={cn("absolute inset-x-0 top-14 z-50 flex flex-col gap-3 rounded-2xl bg-white px-5 py-5 shadow-[0_14px_36px_rgba(67,55,90,.12)]", className)} onClick={onClose}>{children}</motion.div>}</AnimatePresence>;
export const MobileNavToggle = ({ isOpen, onClick }: { isOpen: boolean; onClick: () => void }) => isOpen ? <IconX size={22} className="text-[#2b1638]" onClick={onClick} /> : <IconMenu2 size={22} className="text-[#2b1638]" onClick={onClick} />;
