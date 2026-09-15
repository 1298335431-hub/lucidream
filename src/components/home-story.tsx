import { useEffect, useRef, useState } from "react";
import { useGSAP } from "@gsap/react";
import { ArrowUpRight, ChevronDown } from "lucide-react";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import CardFanCarousel from "./ui/card-fan-carousel";
import { KanshanCardGuide } from "./ui/kanshan-logo";
import KanshanPageGuide from "./kanshan-page-guide";

gsap.registerPlugin(useGSAP, ScrollTrigger);

const CHAPTER_MOTION = {
  small: { y: 24, duration: .6, stagger: .08 },
  medium: { y: 60, duration: .9, stagger: .12 },
  large: { y: 96, duration: 1, stagger: 0 },
} as const;

const DREAM_CARDS = [
  { imgUrl: `${import.meta.env.BASE_URL}assets/showcase/portfolio/silver-deer.png`, alt: "暗空森林与银色鹿" },
  { imgUrl: `${import.meta.env.BASE_URL}assets/showcase/portfolio/endless-corridor.png`, alt: "无尽走廊与未知钥匙" },
  { imgUrl: `${import.meta.env.BASE_URL}assets/showcase/portfolio/fantasy-boundary.png`, alt: "穿越奇幻边界的凝视" },
  { imgUrl: `${import.meta.env.BASE_URL}assets/showcase/portfolio/inverted-library.png`, alt: "倒生图书馆与玻璃钥匙" },
  { imgUrl: `${import.meta.env.BASE_URL}assets/showcase/portfolio/glass-sky.png`, alt: "火山口钟表店与融化的玻璃天空" },
  { imgUrl: `${import.meta.env.BASE_URL}assets/showcase/portfolio/cloud-post-office.png`, alt: "云端邮局与无轮列车" },
  { imgUrl: `${import.meta.env.BASE_URL}assets/showcase/portfolio/luminous-forest.png`, alt: "透明森林中的微光与呼唤" },
];

const PROCESS_STEPS = [
  { number: "01", title: "忠实记录", copy: "先保留梦里真实发生的场景、人物、动作和感受，不急着把它解释成什么。", cue: "原始梦境" },
  { number: "02", title: "提取线索", copy: "把反复出现、情绪最强或明显失常的细节整理出来，作为后续判断的入口。", cue: "场景 · 人物 · 动作 · 情绪" },
  { number: "03", title: "由你确认", copy: "系统给出的线索可以修改、补充或删除，含义由你的真实经历校准。", cue: "确认梦象" },
  { number: "04", title: "得到回望", copy: "将梦境细节、现实语境与可追溯资料放在一起，形成解读和一张专属梦卡。", cue: "解读 · 梦卡" },
];

const SOURCE_GROUPS = [
  {
    id: "cards",
    number: "01",
    title: "自建梦象知识卡",
    status: "75 张 · 原创待终审",
    summary: "把常见梦境线索拆成可核验的解释边界、反例与追问，不直接套用固定答案。",
    details: "知识卡采用文化基础、现代研究与梦卡原创三层结构。当前 75 张均为内部整理稿，尚未作为已获商用批准的资料对外宣称。",
  },
  {
    id: "research",
    number: "02",
    title: "开放研究资料",
    status: "CC BY 4.0 · 待人工终审",
    summary: "参考开放许可的梦境内容编码与连续性研究，为线索分类和现实校准提供方法依据。",
    details: "当前候选包括 Royal Society Open Science 的《Our dreams, our selves》及 Frontiers in Psychology 的梦境连续性研究。它们支持内容分类与观察，不用于个人诊断。",
  },
  {
    id: "history",
    number: "03",
    title: "传统与历史候选资料",
    status: "证据已归档 · 未商用批准",
    summary: "保留历史文本作为文化语境候选，但不把传统象征直接当成对个人处境的结论。",
    details: "《梦林玄解》《梦占逸旨》等中文历史材料仍在版本、OCR 与权利复核中；在完成审核前，不进入正式商用知识库。",
  },
];

export function HomeStory({ onStart }: { onStart: () => void }) {
  const root = useRef<HTMLDivElement>(null);
  const [expandedSource, setExpandedSource] = useState("research");

  useGSAP(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;

    // The first screen and card fan keep their own motion.
    // Every other landing-page block enters as one unit without changing its
    // internal line spacing or layout.
    const groups = gsap.utils.toArray<HTMLElement>([
      ".process-heading",
      ".process-list",
      ".showcase-copy",
      ".source-method-heading",
      ".source-groups",
      ".community-heading",
      ".community-example",
      ".community-bottom",
      ".closing-experience-copy",
    ].join(", ")).map((heading) => {
      const { y, duration } = CHAPTER_MOTION.large;
      const entrance = gsap.timeline({ paused: true });
      entrance.fromTo(heading,
        {
          autoAlpha: 0,
          y,
          scale: .88,
          filter: "blur(16px)",
          transformOrigin: "50% 60%",
        },
        {
          autoAlpha: 1,
          y: 0,
          scale: 1,
          filter: "blur(0px)",
          duration,
          ease: "sine.inOut",
        },
        0,
      );
      return { heading, entrance, visible: false };
    });
    let frame = 0;
    const checkVisibility = () => {
      frame = 0;
      // Subtract the animated offset to measure the actual layout position.
      // This also follows sticky headings without animation-trigger feedback.
      const visibility = groups.map(({ heading }) => {
        const rect = heading.getBoundingClientRect();
        const offset = Number(gsap.getProperty(heading, "y")) || 0;
        return rect.bottom - offset > 0 && rect.top - offset < window.innerHeight;
      });
      groups.forEach((group, index) => {
        const visible = visibility[index];
        if (visible === group.visible) return;
        group.visible = visible;
        if (visible) group.entrance.restart();
        else group.entrance.pause(0);
      });
    };
    const scheduleCheck = () => {
      if (!frame) frame = window.requestAnimationFrame(checkVisibility);
    };
    window.addEventListener("scroll", scheduleCheck, { passive: true });
    window.addEventListener("resize", scheduleCheck);
    ScrollTrigger.addEventListener("refresh", scheduleCheck);
    checkVisibility();

    return () => {
      window.cancelAnimationFrame(frame);
      window.removeEventListener("scroll", scheduleCheck);
      window.removeEventListener("resize", scheduleCheck);
      ScrollTrigger.removeEventListener("refresh", scheduleCheck);
    };
  }, { scope: root });

  useEffect(() => {
    const frame = window.requestAnimationFrame(() => ScrollTrigger.refresh());
    return () => window.cancelAnimationFrame(frame);
  }, [expandedSource]);

  return (
    <div className="home-story" ref={root}>
      <section id="process" className="story-section process-section" aria-labelledby="process-title">
        <header className="story-heading process-heading">
          <p className="eyebrow align-left">梦 卡 如 何 生 成</p>
          <h2 id="process-title"><span className="process-title-line">从一段梦</span><span className="process-title-line">走到一张卡</span></h2>
          <p>不是把梦丢给一个黑箱。四个步骤，让你看见信息怎样被保留、确认，再成为一次可以回望的解释。</p>
          <button className="secondary-button process-cta" onClick={onStart}>从记录开始</button>
          <KanshanPageGuide scene="process" />
        </header>
        <div className="process-experience">
          <div className="process-list">
            {PROCESS_STEPS.map((step) => (
              <article className="process-step" key={step.number}>
                <span>{step.number}</span>
                <div><h3>{step.title}</h3><small>{step.cue}</small></div>
                <p>{step.copy}</p>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section id="showcase" className="showcase-section" aria-label="梦卡作品流">
        <div className="showcase-copy">
          <div className="showcase-title-block">
            <p className="eyebrow align-left">梦 卡 作 品 流</p>
            <h2 className="chapter-title"><span>每场梦</span><span>都有自己的光线</span></h2>
          </div>
          <div className="showcase-context">
            <p>画面跟随梦境内容变化，排版与阅读秩序保持一致。选择卡片，看看不同梦境留下的视觉回声。</p>
            <span>07 张梦卡 · 点击切换 · 每次进入重新展开</span>
            <KanshanPageGuide scene="showcase" />
          </div>
        </div>
        <div className="showcase-fan-wrap"><CardFanCarousel cards={DREAM_CARDS} /></div>
      </section>

      <section id="pricing" className="community-section" aria-labelledby="community-title">
        <header className="community-heading">
          <p className="eyebrow">分 享 与 共 鸣</p>
          <h2 id="community-title" className="chapter-title"><span>把梦里的奇遇</span><span className="community-zhihu-line">带到<span className="community-zhihu-mark"><span className="sr-only">知乎</span><img src={`${import.meta.env.BASE_URL}assets/zhihu/wordmark.svg`} alt="" aria-hidden="true" width={89} height={40} /></span>聊聊</span></h2>
          <p className="community-intro"><span>一张梦卡，一个故事</span><span>也许有人做过和你相似的梦</span></p>
        </header>

        <div className="community-example">
          <figure className="community-dreamcard">
            <div className="community-card-stage">
              <KanshanCardGuide />
              <p className="community-guide-speech">你的梦，会遇见谁的共鸣？</p>
              <img className="community-card-image" src={`${import.meta.env.BASE_URL}assets/showcase/fan-03.png`} width={1080} height={1440} loading="lazy" alt="梦卡示例：盐湖与半开的门，天空倒映在湖面，一人走向远处的门" />
            </div>
            <figcaption>把记得的画面，留成一张梦卡</figcaption>
          </figure>
          <article className="community-story" aria-labelledby="share-example-title">
            <div className="community-story-label"><span>分享示例</span><span>一场梦，打开一个话题</span></div>
            <h3 id="share-example-title">你有没有梦见过<br />一扇很想推开的门？</h3>
            <p>昨晚梦见一片像镜子一样的盐湖，天空和脚下连成一片，远处只有一扇半开的门</p>
            <p>我一直想走近它，却走得很慢。醒来后，最清楚的竟然是那种期待又犹豫的感觉</p>
            <p className="community-question">如果是你，会推开那扇门吗？</p>
            <div className="community-story-footer"><span>梦境故事</span><span>感受与联想</span><span>相似的梦</span></div>
            <p className="community-example-note">图文仅为分享示例，未发布至知乎</p>
          </article>
        </div>

        <div className="community-bottom">
          <div className="community-reasons">
            <article><span>01</span><h3>分享奇遇</h3><p>用梦卡讲述你记得的片段</p></article>
            <article><span>02</span><h3>交流感受</h3><p>聊聊情绪与联想，不必寻找唯一答案</p></article>
            <article><span>03</span><h3>发现共鸣</h3><p>从自己的梦，聊到彼此的经历</p></article>
          </div>
          <div className="community-action">
            <button type="button" onClick={onStart}>制作我的梦卡<ArrowUpRight size={17} strokeWidth={1.5} aria-hidden="true" /></button>
            <p>只分享你愿意公开的内容</p>
          </div>
        </div>
      </section>

      <section id="sources" className="story-section source-method-section" aria-labelledby="source-method-title">
        <header className="story-heading source-method-heading">
          <p className="eyebrow align-left">方 法 与 来 源</p>
          <h2 id="source-method-title" className="chapter-title"><span>解读有来处</span><span>判断有边界</span></h2>
          <p>我们不凭空替你定义梦。梦境细节先被结构化，再结合你的现实语境，与经过记录的知识资料交叉判断。</p>
          <div className="judgement-chain" aria-label="判断流程"><span>梦境事实</span><i /><span>现实语境</span><i /><span>资料证据</span><i /><strong>保留不确定</strong></div>
          <KanshanPageGuide scene="sources" />
        </header>
        <div className="source-groups">
          {SOURCE_GROUPS.map((source) => {
            const expanded = expandedSource === source.id;
            return (
              <article className={`source-group story-reveal${expanded ? " is-expanded" : ""}`} key={source.id}>
                <button type="button" aria-expanded={expanded} onClick={() => setExpandedSource(expanded ? "" : source.id)}>
                  <span className="source-number">{source.number}</span>
                  <span className="source-title"><strong>{source.title}</strong><small>{source.status}</small></span>
                  <span className="source-toggle-icon" aria-hidden="true">
                    <ChevronDown size={17} strokeWidth={1.6} />
                  </span>
                </button>
                <p className="source-summary">{source.summary}</p>
                {expanded && <div className="source-details"><p>{source.details}</p></div>}
              </article>
            );
          })}
          <p className="source-disclaimer story-reveal">研究与历史资料用于内容观察和文化解释，不构成医学、心理诊断或现实预测。</p>
        </div>
      </section>

      <section id="experience" className="closing-experience-section" aria-labelledby="experience-title">
        <div className="closing-experience-copy">
          <p className="eyebrow"><button type="button" className="experience-start" aria-label="立即体验" onClick={onStart}>立 即 体 验</button></p>
          <h2 id="experience-title" className="chapter-title"><span>醒来之前</span><span>先留住这一场梦</span></h2>
          <KanshanPageGuide scene="experience" />
        </div>
      </section>
    </div>
  );
}
