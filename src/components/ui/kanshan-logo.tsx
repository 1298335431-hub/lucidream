import { useEffect, useRef, useState } from "react";
import gsap from "gsap";
import { useGSAP } from "@gsap/react";

gsap.registerPlugin(useGSAP);

const assetRoot = `${import.meta.env.BASE_URL}assets/kanshan/`;
const actionDuration = { computer: 6000, wave: 4000, sleep: 5000, sway: 3000, ball: 4000, idle: 5000 };
export type KanshanAction = keyof typeof actionDuration;

/** Native official GIFs; a single drawn frame respects reduced-motion preferences. */
export function KanshanLogo({ animated = false, playTrigger = 0, action = "computer", repeat = true }: { animated?: boolean; playTrigger?: number; action?: KanshanAction; repeat?: boolean }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [reducedMotion, setReducedMotion] = useState(() => window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  const motionEnabled = animated && !reducedMotion;
  const [playbackUrl, setPlaybackUrl] = useState<string | null>(null);
  const playback = useRef({ play: () => {}, loaded: () => {}, failed: () => {} });

  useGSAP(() => {
    if (!motionEnabled) { setPlaybackUrl(null); return; }
    let alive = true;
    let asset: Blob | null = null;
    let url: string | null = null;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let playing = false;
    let loaded = false;
    const abort = new AbortController();
    const clearTimer = () => { clearTimeout(timer); timer = undefined; };
    const release = () => { if (url) URL.revokeObjectURL(url); url = null; };
    const rest = () => {
      clearTimer();
      playing = false;
      loaded = false;
      release();
      if (!alive) return;
      setPlaybackUrl(null);
      if (repeat && !document.hidden && asset) timer = setTimeout(play, 8000);
    };
    function play() {
      if (!alive || document.hidden || playing) return;
      if (!asset) return; // Initial loading already starts one play when the asset is ready.
      clearTimer();
      playing = true;
      loaded = false;
      // A fresh object URL resets the native GIF to frame one without another download.
      url = URL.createObjectURL(asset);
      setPlaybackUrl(url);
    }
    playback.current = {
      play,
      loaded: () => {
        if (!alive || !playing || loaded) return;
        loaded = true;
        // Durations verified from every frame of the official GIFs.
        timer = setTimeout(rest, actionDuration[action]);
      },
      failed: () => { asset = null; rest(); },
    };
    const visibility = () => rest();
    document.addEventListener("visibilitychange", visibility);
    fetch(`${assetRoot}${action}.gif`, { signal: abort.signal })
      .then(response => { if (!response.ok) throw new Error("Mascot unavailable"); return response.blob(); })
      .then(blob => {
        if (!alive) return;
        asset = blob;
        // Greet immediately on entry/refresh; only completed plays get an eight-second rest.
        play();
      })
      .catch(() => { /* Keep the static mascot if the optional animation cannot load. */ });
    return () => {
      alive = false;
      abort.abort();
      clearTimer();
      release();
      document.removeEventListener("visibilitychange", visibility);
      playback.current = { play: () => {}, loaded: () => {}, failed: () => {} };
    };
  }, { dependencies: [motionEnabled, action, repeat], revertOnUpdate: true });

  useEffect(() => {
    if (playTrigger > 0) playback.current.play();
  }, [playTrigger]);

  useEffect(() => {
    const preference = window.matchMedia("(prefers-reduced-motion: reduce)");
    const sync = () => setReducedMotion(preference.matches);
    preference.addEventListener("change", sync);
    return () => preference.removeEventListener("change", sync);
  }, []);

  useEffect(() => {
    if (motionEnabled && playbackUrl) return;
    let active = true;
    const source = new Image();
    source.onload = () => {
      if (!active) return;
      const canvas = canvasRef.current;
      const context = canvas?.getContext("2d");
      if (!canvas || !context) return;
      context.clearRect(0, 0, canvas.width, canvas.height);
      context.drawImage(source, 0, 0, canvas.width, canvas.height);
    };
    source.src = `${assetRoot}idle.gif`;
    return () => { active = false; source.onload = null; };
  }, [motionEnabled, playbackUrl]);

  if (!motionEnabled || !playbackUrl) return <canvas ref={canvasRef} className="kanshan-logo" data-motion-state="idle" width={320} height={320} role="img" aria-label="刘看山" />;

  return <img
    className="kanshan-logo"
    key={playbackUrl}
    src={playbackUrl}
    data-motion-state="playing"
    onLoad={() => playback.current.loaded()}
    onError={() => playback.current.failed()}
    width={320}
    height={320}
    alt="刘看山"
    draggable={false}
  />;
}

export function KanshanGuide({ onActivate }: { onActivate: () => void }) {
  const [playTrigger, setPlayTrigger] = useState(0);
  return <button className="composer-kanshan" type="button" aria-label="和刘看山一起记录梦境" title="写下你记得的梦" onClick={() => { setPlayTrigger(value => value + 1); onActivate(); }}>
    <KanshanLogo animated playTrigger={playTrigger} />
  </button>;
}

export function KanshanCardGuide() {
  const buttonRef = useRef<HTMLButtonElement>(null);
  const [visible, setVisible] = useState(false);
  const [playTrigger, setPlayTrigger] = useState(0);
  useEffect(() => {
    if (!buttonRef.current) return;
    const observer = new IntersectionObserver(([entry]) => setVisible(entry.isIntersecting), { threshold: 0.3 });
    observer.observe(buttonRef.current);
    return () => observer.disconnect();
  }, []);
  return <button ref={buttonRef} className="community-kanshan" type="button" aria-label="让刘看山打个招呼" onClick={() => setPlayTrigger(value => value + 1)}>
    <KanshanLogo animated={visible} action="wave" playTrigger={playTrigger} />
  </button>;
}
