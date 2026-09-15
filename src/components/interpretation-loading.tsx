import { useEffect, useRef, useState } from "react";
import { useGSAP } from "@gsap/react";
import gsap from "gsap";
import BarLoader from "@/components/ui/bar-loader";
import KanshanPageGuide from "./kanshan-page-guide";

gsap.registerPlugin(useGSAP);

const STAGES = [
  { until: 4, title: "正在整理已确认的梦境片段", detail: "我们会结合你确认的人物、场景与感受，梳理梦里的线索，整理成一份文字解读。" },
  { until: 9, title: "正在梳理意象之间的联系", detail: "从梦中的相遇、行动与情绪出发，联系前后发生的片段，为你提供回望这场梦的角度。" },
  { until: 15, title: "正在寻找情绪与现实线索", detail: "结合梦中的感受与你补充的现实经历，整理可能的联系，也为你的理解保留空间。" },
  { until: Number.POSITIVE_INFINITY, title: "解读仍在生成，请再稍候", detail: "我们正在等待完整的文字解读，完成后会自动为你展示，你可以先留在这里稍作休息。" },
];

type InterpretationLoadingProps = {
  symbols: string[];
  onCancel: () => void;
  onRetry: () => void;
};

export function InterpretationLoading({ onCancel, onRetry }: InterpretationLoadingProps) {
  const rootRef = useRef<HTMLElement>(null);
  const [elapsed, setElapsed] = useState(0);
  const [longWaitDismissed, setLongWaitDismissed] = useState(false);
  const stage = STAGES.find((item) => elapsed < item.until) ?? STAGES[STAGES.length - 1];

  useEffect(() => {
    const timer = window.setInterval(() => setElapsed((value) => value + 1), 1000);
    return () => window.clearInterval(timer);
  }, []);

  useGSAP(() => {
    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const revealTargets = [".parsing-eyebrow", ".parsing-title", ".parsing-copy", ".parsing-loader-stage", ".parsing-waiting-copy"];
    if (reduceMotion) {
      gsap.set(revealTargets, { autoAlpha: 1, y: 0 });
      return;
    }

    const timeline = gsap.timeline({ defaults: { ease: "power2.out" } });
    timeline
      .from(".parsing-eyebrow", { autoAlpha: 0, y: 6, duration: 0.25 })
      .from(".parsing-title", { autoAlpha: 0, y: 11, duration: 0.38 }, "-=0.14")
      .from(".parsing-copy", { autoAlpha: 0, y: 6, duration: 0.3 }, "-=0.22")
      .from(".parsing-loader-stage", { autoAlpha: 0, y: 8, duration: 0.3 }, "-=0.2")
      .from(".parsing-waiting-copy", { autoAlpha: 0, y: 6, duration: 0.28 }, "-=0.1");
  }, { scope: rootRef });

  return (
    <section ref={rootRef} className="interpretation-loading" aria-labelledby="parsing-title" aria-live="polite">
      <p className="eyebrow parsing-eyebrow">梦 境 解 析 中</p>
      <h1 id="parsing-title" className="parsing-title">正在读这场梦<span>线索正在慢慢出现</span></h1>
      <div className="parsing-copy"><KanshanPageGuide scene="loading" message="正在整理你确认过的梦境片段" /></div>

      <div className="parsing-loader-stage" aria-hidden="true">
        <BarLoader bars={12} barWidth={8} barHeight={60} color="#86b5ee" speed={1.5} />
      </div>

      <div className="parsing-waiting-copy" role="status">
        <strong>{stage.title}</strong>
        <p>{stage.detail}</p>
        <span>解读完成后，你可以选择生成梦境画面，将这场梦留作一张梦卡</span>
      </div>

      {elapsed >= 30 && !longWaitDismissed && (
        <aside className="parsing-long-wait" role="status">
          <div><strong>解析时间比平时稍长</strong><span>你的内容已保存，可以继续等待或重新尝试。</span></div>
          <div className="parsing-long-wait-actions">
            <button type="button" onClick={() => setLongWaitDismissed(true)}>继续等待</button>
            <button type="button" onClick={onRetry}>重新尝试</button>
            <button type="button" onClick={onCancel}>返回梦象确认</button>
          </div>
        </aside>
      )}
    </section>
  );
}
