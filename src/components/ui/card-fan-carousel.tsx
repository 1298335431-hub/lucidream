import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import gsap from "gsap";


export interface CardItem {
  imgUrl: string;
  alt?: string;
  linkUrl?: string;
}

interface CardFanCarouselProps {
  cards: CardItem[];
}

const MAX_VISIBLE = 7;
const HALF = 3;

const FAN_POSITIONS = [
  { rot: -21, scale: 0.7756, x: -30, y: 7.3, zIndex: 1 },
  { rot: -14, scale: 0.8498, x: -22, y: 4, zIndex: 2 },
  { rot: -7, scale: 0.9346, x: -11, y: 1.3, zIndex: 3 },
  { rot: 0, scale: 1, x: 0, y: 0, zIndex: 10 },
  { rot: 7, scale: 0.9346, x: 11, y: 1.3, zIndex: 3 },
  { rot: 14, scale: 0.8498, x: 22, y: 4, zIndex: 2 },
  { rot: 21, scale: 0.7756, x: 30, y: 7.3, zIndex: 1 },
];

function getResponsiveMultiplier(width: number) {
  if (width < 480) return 0.28;
  if (width < 640) return 0.38;
  if (width < 768) return 0.5;
  if (width < 1024) return 0.75;
  if (width < 1600) return 0.72;
  return 1;
}

function getHeightMultiplier(width: number) {
  let idealPx: number;
  if (width < 480) idealPx = 352;
  else if (width < 640) idealPx = 416;
  else if (width < 768) idealPx = 448;
  else if (width < 1024) idealPx = 544;
  else idealPx = 608;

  const available = window.innerHeight * 0.7;
  return available >= idealPx ? 1 : available / idealPx;
}

function getSlotConfig(totalCards: number, slot: number) {
  if (totalCards >= MAX_VISIBLE) return FAN_POSITIONS[slot];
  const center = totalCards >> 1;
  const distance = totalCards > 1 ? (slot - center) / center : 0;
  const absDistance = Math.abs(distance);
  return {
    rot: distance * 21,
    scale: 1 - 0.2244 * absDistance * absDistance,
    x: distance * 30,
    y: absDistance * absDistance * 7.3,
    zIndex: 10 - Math.abs(slot - center),
  };
}

export default function CardFanCarousel({ cards }: CardFanCarouselProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const isAnimating = useRef(false);
  const hasEntered = useRef(false);
  const handledEntranceNonce = useRef(0);
  const directionRef = useRef<"left" | "right" | null>(null);
  const prevVisible = useRef<Set<number>>(new Set());
  const [entranceNonce, setEntranceNonce] = useState(0);
  const [isReady, setIsReady] = useState(false);
  const totalCards = cards.length;
  const visibleCount = Math.min(MAX_VISIBLE, totalCards);
  const needsPagination = totalCards > 1;
  const [centerIndex, setCenterIndex] = useState(totalCards > MAX_VISIBLE ? HALF : totalCards >> 1);

  const getVisibleMap = useCallback((center: number) => {
    const map = new Map<number, number>();
    if (totalCards <= 1) {
      cards.forEach((_, index) => map.set(index, index));
      return map;
    }
    const halfVisible = visibleCount >> 1;
    for (let slot = 0; slot < visibleCount; slot += 1) {
      map.set(((center + slot - halfVisible) % totalCards + totalCards) % totalCards, slot);
    }
    return map;
  }, [cards, totalCards, visibleCount]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    let wasVisible = false;
    const observer = new IntersectionObserver(([entry]) => {
      const isVisible = entry.isIntersecting && entry.intersectionRatio >= .18;
      if (isVisible && !wasVisible && hasEntered.current) {
        setEntranceNonce((value) => value + 1);
      }
      wasVisible = isVisible;
    }, { threshold: [.18, .5] });
    observer.observe(container);
    return () => observer.disconnect();
  }, []);

  const cycle = useCallback((direction: "left" | "right") => {
    if (isAnimating.current || !needsPagination) return;
    isAnimating.current = true;
    directionRef.current = direction;
    setCenterIndex((previous) => direction === "right"
      ? (previous + 1) % totalCards
      : (previous - 1 + totalCards) % totalCards);
  }, [needsPagination, totalCards]);

  useLayoutEffect(() => {
    const container = containerRef.current;
    if (!container || !totalCards) return;

    const cardElements = Array.from(container.querySelectorAll<HTMLElement>(".fan-card"));
    if (!cardElements.length) return;
    if (!isReady) setIsReady(true);

    const visibleMap = getVisibleMap(centerIndex);
    const previouslyVisible = prevVisible.current;
    const direction = directionRef.current;
    const isEntrance = !hasEntered.current || entranceNonce !== handledEntranceNonce.current;
    if (isEntrance) handledEntranceNonce.current = entranceNonce;
    const multiplier = getResponsiveMultiplier(window.innerWidth);
    const heightMultiplier = getHeightMultiplier(window.innerWidth);
    const slotCount = visibleCount;
    const config = (slot: number) => getSlotConfig(slotCount, slot);

    isAnimating.current = true;

    // A safety release keeps controls responsive if an interrupted/reverted
    // tween does not reach its completion callback.
    const unlockTimer = window.setTimeout(() => {
      isAnimating.current = false;
      if (isEntrance) hasEntered.current = true;
    }, isEntrance ? 2000 : 760);

    let completedCount = 0;
    const onCardDone = () => {
      completedCount += 1;
      if (completedCount >= visibleMap.size) {
        isAnimating.current = false;
        if (isEntrance) hasEntered.current = true;
      }
    };

    cardElements.forEach((card, cardIndex) => {
      const slot = visibleMap.get(cardIndex);
      const wasVisible = previouslyVisible.has(cardIndex);

      if (slot !== undefined) {
        const { x, y, rot, scale, zIndex } = config(slot);
        const target = {
          xPercent: -50,
          x: `${x * multiplier}rem`,
          y: `${y * heightMultiplier}rem`,
          rotation: rot,
          scale,
          opacity: 1,
          zIndex,
        };

        if (isEntrance) {
          gsap.set(card, { xPercent: -50, x: 0, y: `${12 * heightMultiplier}rem`, rotation: 0, scale: 0.5, opacity: 0 });
          gsap.to(card, { ...target, duration: 1.2, ease: "elastic.out(1.05,.78)", delay: 0.2 + slot * 0.06, onComplete: onCardDone });
        } else if (!wasVisible) {
          const enterX = direction === "right" ? 40 : -40;
          gsap.set(card, { xPercent: -50, x: `${enterX}rem`, y: `${y * heightMultiplier}rem`, rotation: direction === "right" ? 30 : -30, scale: 0.5, opacity: 0 });
          gsap.to(card, { ...target, duration: 0.6, ease: "power2.out", onComplete: onCardDone });
        } else {
          gsap.to(card, { ...target, duration: 0.5, ease: "power2.out", onComplete: onCardDone });
        }
      } else if (wasVisible) {
        const exitX = direction === "right" ? -40 : 40;
        gsap.to(card, { x: `${exitX}rem`, opacity: 0, scale: 0.5, rotation: direction === "right" ? -30 : 30, duration: 0.4, ease: "power2.in", zIndex: 0 });
      } else if (isEntrance) {
        gsap.set(card, { xPercent: -50, opacity: 0, scale: 0.3, x: 0, y: 0, zIndex: 0 });
      }
    });

    prevVisible.current = new Set(visibleMap.keys());

    const visibleEntries: Array<{ el: HTMLElement; slot: number }> = [];
    cardElements.forEach((element, index) => {
      const slot = visibleMap.get(index);
      if (slot !== undefined) visibleEntries.push({ el: element, slot });
    });
    visibleEntries.sort((a, b) => a.slot - b.slot);

    let activeSlot: number | null = null;
    let leaveTimer: ReturnType<typeof setTimeout> | null = null;
    const centerSlot = visibleEntries.length >> 1;

    const updateHoverLayout = (hoveredSlot: number | null) => {
      const responsiveMultiplier = getResponsiveMultiplier(window.innerWidth);
      const responsiveHeight = getHeightMultiplier(window.innerWidth);

      visibleEntries.forEach(({ el, slot }) => {
        const base = config(slot);
        let targetX = base.x * responsiveMultiplier;
        let targetY = base.y * responsiveHeight;
        let targetRotation = base.rot;
        let targetScale = base.scale;
        let delay = 0;

        if (hoveredSlot !== null) {
          const distance = Math.abs(slot - hoveredSlot);
          delay = distance * 0.02;
          if (slot === hoveredSlot) {
            targetY -= 2.5 * responsiveHeight;
            targetScale *= 1.08;
          } else {
            const normalized = centerSlot > 0 ? (slot - centerSlot) / centerSlot : 0;
            const pushStrength = 8 * (1 - Math.abs(normalized)) * (1 + 0.2 * Math.max(0, 3 - distance));
            if (slot < hoveredSlot) {
              targetX -= pushStrength * responsiveMultiplier;
              targetRotation -= 3 / (distance + 1);
            } else {
              targetX += pushStrength * responsiveMultiplier;
              targetRotation += 3 / (distance + 1);
            }
          }
        } else {
          delay = Math.abs(slot - centerSlot) * 0.02;
        }

        gsap.to(el, {
          x: `${targetX}rem`,
          y: `${targetY}rem`,
          rotation: targetRotation,
          scale: targetScale,
          duration: 0.5,
          delay,
          ease: "elastic.out(1,.75)",
          overwrite: "auto",
        });
        gsap.set(el, { zIndex: base.zIndex });
      });
    };

    const enterHandlers = visibleEntries.map(({ el, slot }) => {
      const handler = () => {
        if (isAnimating.current) return;
        if (leaveTimer) clearTimeout(leaveTimer);
        if (activeSlot !== slot) {
          activeSlot = slot;
          updateHoverLayout(slot);
        }
      };
      el.addEventListener("mouseenter", handler);
      return { el, handler };
    });

    const handleMouseLeave = () => {
      if (isAnimating.current) return;
      if (leaveTimer) clearTimeout(leaveTimer);
      leaveTimer = setTimeout(() => {
        activeSlot = null;
        updateHoverLayout(null);
      }, 50);
    };
    container.addEventListener("mouseleave", handleMouseLeave);

    const handleResize = () => {
      if (!isAnimating.current) updateHoverLayout(activeSlot);
    };
    window.addEventListener("resize", handleResize);

    return () => {
      enterHandlers.forEach(({ el, handler }) => el.removeEventListener("mouseenter", handler));
      container.removeEventListener("mouseleave", handleMouseLeave);
      window.removeEventListener("resize", handleResize);
      if (leaveTimer) clearTimeout(leaveTimer);
      window.clearTimeout(unlockTimer);
      // Stop the old motion without reverting the cards to their hidden CSS
      // state. Pagination must tween from the currently displayed fan.
      gsap.killTweensOf(cardElements);
      isAnimating.current = false;
    };
  }, [centerIndex, entranceNonce, getVisibleMap, needsPagination, totalCards, visibleCount]);

  if (!totalCards) return null;

  return (
    <section className={`card-fan-carousel${isReady ? " is-ready" : ""}`} aria-label="梦卡展示">
      <div ref={containerRef} className="fan-layout">
        {cards.map((card, index) => {
          const image = <img src={card.imgUrl} loading="lazy" alt={card.alt || `梦卡 ${index + 1}`} />;
          return card.linkUrl ? (
            <a key={`${card.imgUrl}-${index}`} href={card.linkUrl} className="fan-card">{image}</a>
          ) : (
            <div key={`${card.imgUrl}-${index}`} className="fan-card">{image}</div>
          );
        })}
      </div>

      {needsPagination && (
        <div className="fan-pagination" aria-label="切换梦卡">
          <button onClick={() => cycle("left")} aria-label="上一张"><ChevronLeft size={19} strokeWidth={1.5} /></button>
          <div className="fan-dots" aria-hidden="true">
            {cards.map((_, index) => <span key={index} className={index === centerIndex ? "is-active" : ""} />)}
          </div>
          <button onClick={() => cycle("right")} aria-label="下一张"><ChevronRight size={19} strokeWidth={1.5} /></button>
        </div>
      )}
    </section>
  );
}
