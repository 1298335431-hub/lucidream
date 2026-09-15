import { useEffect, useRef, useState } from "react";
import { CalendarDays, ChevronLeft, ChevronRight } from "lucide-react";

export default function DreamDatePicker({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  const [open, setOpen] = useState(false);
  const [month, setMonth] = useState(() => new Date(`${value}T12:00:00`));
  const root = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (!open) return;
    const close = (event: PointerEvent) => { if (!root.current?.contains(event.target as Node)) setOpen(false); };
    document.addEventListener("pointerdown", close);
    return () => document.removeEventListener("pointerdown", close);
  }, [open]);
  const year = month.getFullYear();
  const today = new Date();
  today.setHours(23, 59, 59, 999);
  const index = month.getMonth();
  const first = new Date(year, index, 1).getDay();
  const select = (date: Date) => {
    if (date > today) return;
    onChange(`${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`);
    setOpen(false);
    trigger.current?.focus();
  };
  return <div className="dream-date-picker" ref={root} onKeyDown={(event) => {
    if (event.key === "Escape" && open) { event.stopPropagation(); setOpen(false); trigger.current?.focus(); }
  }}>
    <button ref={trigger} type="button" className="dream-date-trigger" aria-label="选择梦境日期" aria-expanded={open} onClick={() => { setMonth(new Date(`${value}T12:00:00`)); setOpen(!open); }}>{value.replace(/-/g, "/")}<CalendarDays size={16} /></button>
    {open && <div className="dream-date-popover" role="group" aria-label="日期选择">
      <div className="dream-date-heading">
        <button type="button" aria-label="上个月" onClick={() => setMonth(new Date(year, index - 1, 1))}><ChevronLeft size={16} /></button>
        <strong>{year}年{index + 1}月</strong>
        <button type="button" aria-label="下个月" disabled={new Date(year, index + 1, 1) > today} onClick={() => setMonth(new Date(year, index + 1, 1))}><ChevronRight size={16} /></button>
      </div>
      <div className="dream-date-grid">
        {Array.from("日一二三四五六").map((day) => <span key={day}>{day}</span>)}
        {Array.from({ length: 42 }, (_, i) => {
          const date = new Date(year, index, i - first + 1);
          const key = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
          return <button key={key} type="button" aria-label={key} disabled={date > today} aria-pressed={key === value} className={date.getMonth() !== index ? "is-outside" : ""} onClick={() => select(date)}>{date.getDate()}</button>;
        })}
      </div>
      <button className="dream-date-today" type="button" onClick={() => select(new Date())}>今天</button>
    </div>}
  </div>;
}
