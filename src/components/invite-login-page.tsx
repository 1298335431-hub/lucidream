import { FormEvent, useEffect, useRef, useState } from "react";
import { ArrowLeft, ArrowRight } from "lucide-react";
import { DreamCardLogo } from "@/components/ui/dream-card-logo";
import "./invite-login-page.css";
import KanshanPageGuide from "./kanshan-page-guide";
import { TEMPORARY_DEMO } from "../demo-mode";

type InviteLoginPageProps = {
  onBack: () => void;
  onSuccess: () => void;
  onAuthenticate: (code: string) => Promise<void>;
  onZhihuLogin: () => Promise<void>;
};


function DotRevealBackground() {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const context = canvas.getContext("2d");
    if (!context) return;

    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    type Dot = { x: number; y: number; phase: number };
    let dots: Dot[] = [];
    let frame = 0;
    let start = performance.now();
    let lastFrame = 0;
    let dpr = 1;
    let pointerX = -10000;
    let pointerY = -10000;
    let pointerEnergy = 0;

    const layout = () => {
      dpr = Math.min(window.devicePixelRatio || 1, 1.1);
      const width = Math.max(1, Math.round(canvas.clientWidth * dpr));
      const height = Math.max(1, Math.round(canvas.clientHeight * dpr));
      canvas.width = width;
      canvas.height = height;
      const step = 20 * dpr;
      dots = [];
      for (let y = step / 2; y < height; y += step) {
        for (let x = step / 2; x < width; x += step) {
          dots.push({ x, y, phase: (x * .013 + y * .017) % (Math.PI * 2) });
        }
      }
    };

    const draw = (progress: number, now: number) => {
      const { width, height } = canvas;
      context.clearRect(0, 0, width, height);
      const centerX = width * .5;
      const centerY = height * .47;
      const revealRadius = Math.hypot(width, height) * (.08 + progress * .66);
      const step = 20 * dpr;
      const radius = 1.2 * dpr;
      const time = now * .00042;
      const pointerRadius = 150 * dpr;

      context.fillStyle = "rgb(238, 235, 226)";
      for (const dot of dots) {
        const distance = Math.hypot(dot.x - centerX, dot.y - centerY);
        const edge = Math.max(0, Math.min(1, (revealRadius - distance) / (step * 4)));
        if (edge <= 0) continue;

        const breath = Math.sin(time + dot.phase) * .5 + Math.sin(time * .63 - dot.phase * .7) * .5;
        let offsetX = Math.sin(time * .9 + dot.phase) * .55 * dpr;
        let offsetY = Math.cos(time * .76 + dot.phase * 1.13) * .55 * dpr;
        const pointerDistance = Math.hypot(dot.x - pointerX, dot.y - pointerY);
        if (pointerEnergy > .01 && pointerDistance < pointerRadius) {
          const influence = (1 - pointerDistance / pointerRadius) * pointerEnergy;
          const direction = Math.atan2(dot.y - pointerY, dot.x - pointerX);
          offsetX += Math.cos(direction) * influence * 2.4 * dpr;
          offsetY += Math.sin(direction) * influence * 2.4 * dpr;
        }

        context.globalAlpha = edge * (.13 + breath * .025);
        context.beginPath();
        context.arc(dot.x + offsetX, dot.y + offsetY, radius, 0, Math.PI * 2);
        context.fill();
      }
      context.globalAlpha = 1;
    };

    const render = (now: number) => {
      frame = window.requestAnimationFrame(render);
      if (document.hidden || now - lastFrame < 1000 / 20) return;
      lastFrame = now;
      pointerEnergy *= .94;
      const elapsed = Math.min(1, (now - start) / 2600);
      const eased = 1 - Math.pow(1 - elapsed, 3);
      draw(eased, now);
    };

    const handlePointerMove = (event: PointerEvent) => {
      pointerX = event.clientX * dpr;
      pointerY = event.clientY * dpr;
      pointerEnergy = Math.min(1, pointerEnergy + .34);
    };
    const handleResize = () => {
      layout();
      draw(1, performance.now());
    };
    const handleVisibility = () => {
      if (document.hidden) return;
      lastFrame = performance.now();
    };

    layout();
    if (reducedMotion) {
      draw(1, 0);
    } else {
      window.addEventListener("pointermove", handlePointerMove, { passive: true });
      document.addEventListener("visibilitychange", handleVisibility);
      frame = window.requestAnimationFrame(render);
    }
    window.addEventListener("resize", handleResize, { passive: true });
    return () => {
      window.cancelAnimationFrame(frame);
      window.removeEventListener("resize", handleResize);
      window.removeEventListener("pointermove", handlePointerMove);
      document.removeEventListener("visibilitychange", handleVisibility);
    };
  }, []);

  return <canvas className="invite-dot-field" ref={canvasRef} aria-hidden="true" />;
}

export function InviteLoginPage({ onBack, onSuccess, onAuthenticate, onZhihuLogin }: InviteLoginPageProps) {
  const [inviteCode, setInviteCode] = useState("");
  const [notice, setNotice] = useState("");
  const [status, setStatus] = useState<"idle" | "checking" | "success">("idle");
  const [zhihu, setZhihu] = useState<{ ready: boolean; message: string } | null>(null);
  const [zhihuBusy, setZhihuBusy] = useState(false);
  const [checkAttempt, setCheckAttempt] = useState(0);
  const [zhihuNotice, setZhihuNotice] = useState(() => {
    const result = new URLSearchParams(window.location.search).get("zhihu");
    if (!result) return "";
    if (result === "state_missing") return "授权回调缺少安全校验信息，未建立登录";
    if (result === "authorization_denied") return "本次授权未完成，可以重新登录";
    if (result === "identity_invalid") return "无法确认知乎账号身份，未建立登录";
    return TEMPORARY_DEMO ? "本次知乎登录未完成，请重试" : "本次登录未完成，请重试或使用邀请码";
  });
  useEffect(() => {
    const controller = new AbortController();
    const timer = window.setTimeout(() => controller.abort(), 6000);
    let active = true;
    setZhihu(null);
    fetch(`${import.meta.env.VITE_API_BASE_URL ?? "/api/v1"}/auth/zhihu/status`, { credentials: "include", signal: controller.signal })
      .then(async response => {
        if (!response.ok) throw new Error("status unavailable");
        const data = await response.json();
        if (typeof data.ready !== "boolean" || typeof data.message !== "string") throw new Error("invalid status");
        if (active) setZhihu({ ready: data.ready, message: data.message });
      }).catch(() => {
        if (active) setZhihu({ ready: false, message: TEMPORARY_DEMO ? "知乎登录配置中，暂未开放体验" : "知乎登录服务暂未连接，你仍可使用邀请码登录" });
      }).finally(() => window.clearTimeout(timer));
    return () => { active = false; window.clearTimeout(timer); controller.abort(); };
  }, [checkAttempt]);
  const startZhihu = async () => {
    if (zhihuBusy || status !== "idle") return;
    if (!zhihu?.ready) { setZhihuNotice(zhihu?.message || "正在检查知乎登录状态"); return; }
    setZhihuBusy(true);
    setZhihuNotice("正在前往知乎，请在知乎页面确认授权");
    try { await onZhihuLogin(); }
    catch { setZhihuBusy(false); setZhihuNotice(TEMPORARY_DEMO ? "暂时无法前往知乎，请稍后重试" : "暂时无法前往知乎，请重试或使用邀请码"); }
  };

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (status === "checking" || status === "success" || zhihuBusy) return;
    const normalizedCode = inviteCode.trim().toUpperCase();
    if (!normalizedCode) {
      setStatus("idle");
      setNotice("请输入邀请码");
      return;
    }
    setStatus("checking");
    setNotice("正在验证邀请码…");
    try {
      await onAuthenticate(normalizedCode);
      setStatus("success");
      setNotice("邀请码验证成功，正在进入梦境…");
      onSuccess();
    } catch (error) {
      setStatus("idle");
      setNotice(error instanceof Error ? error.message : "登录暂时失败，请重试");
    }
  };

  return (
    <main className="invite-login-page">
      <DotRevealBackground />
      <header className="invite-nav" aria-label="登录页导航">
        <button className="invite-brand" type="button" onClick={onBack} aria-label="返回 LUCIDREAM 首页">
          <DreamCardLogo animated={false} tone="card" aria-hidden="true" />
          <span>LUCIDREAM</span>
        </button>
        <button className="invite-back" type="button" onClick={onBack}>
          <ArrowLeft aria-hidden="true" size={15} strokeWidth={1.35} />
          <span>返回首页</span>
        </button>
      </header>

      <section className="invite-panel" aria-labelledby="invite-title">
        <p className="invite-eyebrow">LUCIDREAM · 梦境回声</p>
        <h1 id="invite-title">{TEMPORARY_DEMO ? "登录知乎" : "登录之后"}<br />{TEMPORARY_DEMO ? "体验看山说梦" : "让梦有处可寻"}</h1>
        <KanshanPageGuide scene="login" dark />

        <div className="zhihu-login-entry">
          <button className="zhihu-login-button" type="button" onClick={startZhihu}
            aria-disabled={!zhihu?.ready || zhihuBusy || status !== "idle"} aria-describedby="zhihu-login-status">
            <span>{zhihuBusy ? "正在前往知乎…" : "使用知乎账号登录"}</span><ArrowRight size={18} aria-hidden="true" />
          </button>
          <p id="zhihu-login-status" className="zhihu-login-status" role="status">{zhihuNotice || zhihu?.message || "正在检查知乎登录状态"}</p>
          {zhihu && !zhihu.ready && <button className="zhihu-login-recheck" type="button" onClick={() => { setZhihuNotice(""); setCheckAttempt(value => value + 1); }}>重新检查</button>}
        </div>

        <form className="invite-form" onSubmit={handleSubmit}>
          <p className="invite-alternative">{TEMPORARY_DEMO ? "或使用临时体验码" : "或使用已有邀请码"}</p>
          <label className="sr-only" htmlFor="invite-code">邀请码</label>
          <div className="invite-input-shell">
            <input
              id="invite-code"
              type="text"
              value={inviteCode}
              onChange={(event) => {
                setInviteCode(event.target.value);
                if (notice) setNotice("");
                if (status !== "idle") setStatus("idle");
              }}
              placeholder="输入邀请码"
              autoComplete="off"
              spellCheck={false}
            />
            <button type="submit" aria-label="提交邀请码" disabled={status === "checking" || status === "success" || zhihuBusy}>
              <ArrowRight aria-hidden="true" size={18} strokeWidth={1.35} />
            </button>
          </div>
          <p className={`invite-helper${status === "success" ? " is-success" : ""}`} role="status" aria-live="polite">{notice || (TEMPORARY_DEMO ? "同一体验码共用演示记录，请勿输入隐私内容" : "邀请码仅用于内测访问")}</p>
        </form>
      </section>

      <p className="invite-footer">梦境回光 · 仅供自我观察</p>
    </main>
  );
}
