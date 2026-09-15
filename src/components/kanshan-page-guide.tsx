import { useEffect, useRef, useState } from "react";
import { useGSAP } from "@gsap/react";
import gsap from "gsap";
import { KanshanLogo, type KanshanAction } from "./ui/kanshan-logo";
import "./kanshan-page-guide.css";

const scenes = {
  login: ["wave", "先登录，把这场梦留下"],
  review: ["sway", "梦里的你，是这个样子吗？"],
  confirmed: ["wave", "线索确认好了，就准备出发吧"],
  loading: ["computer", "正在把梦里的片段整理成画面"],
  reading: ["sway", "解读已整理好，慢慢看看这场梦"],
  card: ["ball", "留下梦卡，也可以带去知乎聊聊"],
  archive: ["sleep", "回来看看，你曾梦见什么"],
  account: ["idle", "每一次生成，都留下一场梦"],
  privacy: ["idle", "分享之前，记得检查私密信息"],
  process: ["computer", "先记录，再确认，一起把梦留下"],
  showcase: ["ball", "看看这些梦，有没有你的灵感"],
  sources: ["idle", "解读是一个角度，感受由你判断"],
  experience: ["sway", "从还记得的一个片段开始"],
  share: ["wave", "分享哪些内容，由你决定"],
  safety: ["idle", "先照顾好自己，梦可以慢慢说"],
} satisfies Record<string, [KanshanAction, string]>;
export type GuideScene = keyof typeof scenes;

/** Page-level guidance stays outside exported cards; only the static card mark exports. */
export default function KanshanPageGuide({ scene, message, dark = false, disabled = false }: { scene: GuideScene; message?: string; dark?: boolean; disabled?: boolean }) {
  const root = useRef<HTMLDivElement>(null);
  const [entered, setEntered] = useState(false);
  const [visible, setVisible] = useState(false);
  const [playTrigger, setPlayTrigger] = useState(0);
  const [action, defaultMessage] = scenes[scene];
  useEffect(() => {
    const observer = new IntersectionObserver(([entry]) => {
      setVisible(entry.isIntersecting);
      if (entry.isIntersecting) setEntered(true);
    }, { threshold: .15 });
    if (root.current) observer.observe(root.current);
    return () => observer.disconnect();
  }, []);
  useGSAP(() => {
    if (!entered || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    gsap.fromTo(".kanshan-speech", { y: 5, autoAlpha: .4 }, { y: 0, autoAlpha: 1, duration: .35, ease: "power2.out" });
  }, { scope: root, dependencies: [entered], revertOnUpdate: true });
  return <div ref={root} className={`kanshan-page-guide${dark ? " is-dark" : ""}`} data-guide-scene={scene} data-guide-action={action}>
    <button type="button" disabled={disabled} className="kanshan-page-character" aria-label="让小看山再做一次动作" title="点击小看山，播放一次动作" onClick={() => setPlayTrigger(value => value + 1)}>
      <KanshanLogo key={scene} animated={visible} action={action} playTrigger={playTrigger} />
    </button>
    <p className="kanshan-speech">{message ?? defaultMessage}</p>
  </div>;
}
