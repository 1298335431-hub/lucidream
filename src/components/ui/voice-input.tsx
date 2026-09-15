"use client";

import { useEffect, useRef, useState } from "react";
import { Mic } from "lucide-react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import type { SpeechStatus } from "@/speech";
import "./voice-input.css";

interface VoiceInputProps {
  status: SpeechStatus;
  onToggle: () => void;
  className?: string;
}

const LEVELS = [0.45, 0.8, 0.6, 1, 0.55, 0.9, 0.7, 0.4, 0.85, 0.65, 1, 0.5];

export function VoiceInput({ status, onToggle, className = "" }: VoiceInputProps) {
  const rootRef = useRef<HTMLButtonElement>(null);
  const startedAt = useRef<number | null>(null);
  const [seconds, setSeconds] = useState(0);
  const [visible, setVisible] = useState(false);
  const reducedMotion = useReducedMotion();
  const listening = status === "listening";
  const expanded = status !== "idle";
  const animate = listening && visible && !reducedMotion;
  const label = status === "starting" ? "取消连接麦克风" : status === "stopping" ? "正在收尾" : listening ? "停止收听" : "语音记录";

  useEffect(() => {
    let inView = false;
    const update = () => setVisible(inView && !document.hidden);
    const observer = new IntersectionObserver(([entry]) => {
      inView = entry.isIntersecting;
      update();
    });
    if (rootRef.current) observer.observe(rootRef.current);
    document.addEventListener("visibilitychange", update);
    return () => {
      observer.disconnect();
      document.removeEventListener("visibilitychange", update);
    };
  }, []);

  useEffect(() => {
    if (status === "listening" && startedAt.current === null) startedAt.current = Date.now();
    if (status === "idle" || status === "starting") {
      startedAt.current = null;
      setSeconds(0);
    }
  }, [status]);

  useEffect(() => {
    if (!listening || !visible) return;
    const tick = () => setSeconds(Math.floor((Date.now() - (startedAt.current ?? Date.now())) / 1000));
    tick();
    const timer = setInterval(tick, 1000);
    return () => clearInterval(timer);
  }, [listening, visible]);

  return (
    <button
      ref={rootRef}
      type="button"
      className={`voice-input ${className}`}
      aria-label={label}
      title={label}
      aria-pressed={expanded}
      aria-busy={status === "starting" || status === "stopping"}
      disabled={status === "stopping"}
      onClick={onToggle}
    >
      <div className="voice-input-icon" aria-hidden="true">
        {expanded ? (
          <motion.div
            className="voice-input-stop"
            animate={{ rotate: animate ? [0, 180, 360] : 0 }}
            transition={{ duration: animate ? 2 : 0, repeat: animate ? Infinity : 0, ease: "easeInOut" }}
          />
        ) : <Mic size={16} strokeWidth={1.7} />}
      </div>
      <AnimatePresence initial={false}>
        {expanded && (
          <motion.div
            className="voice-input-details"
            initial={{ opacity: 0, width: 0, marginLeft: 0 }}
            animate={{ opacity: 1, width: "auto", marginLeft: 7 }}
            exit={{ opacity: 0, width: 0, marginLeft: 0 }}
            transition={{ duration: reducedMotion ? 0 : 0.4 }}
            aria-hidden="true"
          >
            {listening ? (
              <>
                <div className="voice-input-wave">
                  {LEVELS.map((level, index) => (
                    <motion.div
                      key={index}
                      className="voice-input-bar"
                      animate={{ scaleY: animate ? [0.15, level, level * 0.55, 0.15] : 0.15 }}
                      transition={{ duration: animate ? 1 : 0, repeat: animate ? Infinity : 0, delay: animate ? index * 0.05 : 0, ease: "easeInOut" }}
                    />
                  ))}
                </div>
                <div className="voice-input-time">{String(Math.floor(seconds / 60)).padStart(2, "0")}:{String(seconds % 60).padStart(2, "0")}</div>
              </>
            ) : <div className="voice-input-status">{status === "starting" ? "连接中" : "收尾中"}</div>}
          </motion.div>
        )}
      </AnimatePresence>
    </button>
  );
}

export default VoiceInput;
