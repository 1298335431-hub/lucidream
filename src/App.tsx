import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { toPng } from "html-to-image";
import DreamDatePicker from "@/components/ui/dream-date-picker";
import { gsap } from "gsap";
import { useGSAP } from "@gsap/react";
import { FlowButton } from "@/components/ui/flow-button";
import { VoiceInput } from "@/components/ui/voice-input";
import { DreamCardLogo } from "@/components/ui/dream-card-logo";
import { KanshanGuide } from "@/components/ui/kanshan-logo";
import { LiquidLoginButton } from "@/components/ui/liquid-login-button";
import { TubelightNavBar, type TubelightNavItem } from "@/components/ui/tubelight-navbar";
import { Navbar, NavBody, NavItems, MobileNav, MobileNavHeader, MobileNavMenu, MobileNavToggle } from "@/components/ui/resizable-navbar";
import { InviteLoginPage } from "@/components/invite-login-page";
import AccountMenu, { type AccountProfile } from "@/components/account-menu";
import DreamShare from "@/components/dream-share";
import KanshanPageGuide from "@/components/kanshan-page-guide";
import { ProductModuleView, type ProductModule } from "@/components/product-modules";
import { HomeStory } from "@/components/home-story";
import { InterpretationLoading } from "@/components/interpretation-loading";
import WhirlpoolLoader from "@/components/ui/loading-animation";
import { ArrowLeft, ArrowRight, BookOpen, ChevronDown, CircleUserRound, Download, Frame, PanelLeftClose, PanelLeftOpen, PenLine, Plus, Settings2, Sparkles, X } from "lucide-react";
import { appendSpeech, MAX_DREAM_CHARS, speechIssue, startSpeechSession, type RecognitionConstructor, type SpeechIssue, type SpeechStatus } from "./speech";
import { clearResultView, readResultView, saveResultView } from "./result-view";
import { TEMPORARY_DEMO } from "./demo-mode";

type SymbolKey = "dreamer" | "scenes" | "characters" | "objects" | "actions" | "emotions" | "relationships" | "reality_context" | "uncertain_fields";
type DreamSymbols = Record<SymbolKey, string[]>;
type Clarification = { question: string; options: string[] };
type DreamSession = {
  id: string;
  dream_text: string;
  status: "draft" | "reviewing_symbols" | "awaiting_clarification" | "ready_to_generate" | "failed" | "safety_interrupted";
  symbols: DreamSymbols;
  clarification: Clarification | null;
  clarification_answer: string | null;
  character_appearance?: "unspecified" | "male" | "female" | "none" | "other";
  character_form?: string;
  dreamer_suggestion?: { appearance: "male" | "female" | "other" | "unspecified"; form: string } | null;
  safety_message: string | null;
  revision: number;
  created_at: string;
  model_mode: string;
};
type PersonalizedInterpretation = {
  title: string;
  opening: string;
  dream_summary: string;
  reflections: string[];
  card_summary?: string;
  reflection_question: string;
  gentle_action: string;
  image_scene: string;
  image_style: string;
  style_reason: string;
};
type SourceBackedInterpretation = {
  title: string;
  readings: Array<{ source_id: string; quote: string; reading: string }>;
  card_summary?: string;
  reflection_question: string;
  image_scene: string;
  image_style: string;
  style_reason: string;
};
type InterpretationResponse = {
  session_id: string;
  revision: number;
  generation_mode: "source_backed" | "personalized";
  interpretation: PersonalizedInterpretation | SourceBackedInterpretation;
};
type LandingSection = "record" | "process" | "showcase" | "sources" | "pricing";
type DreamCardFrame = "moonline" | "mistglass" | "starlight" | "finegold" | "dotted" | "gallery";
const DREAM_CARD_FRAMES: { id: DreamCardFrame; name: string; description: string }[] = [
  { id: "gallery", name: "无边框", description: "纯净画面" },
  { id: "moonline", name: "月弧留白", description: "对角轻绕" },
  { id: "mistglass", name: "雾蓝双框", description: "柔和层叠" },
  { id: "starlight", name: "流光侧框", description: "纵向渐隐" },
  { id: "finegold", name: "香槟细线", description: "暖金勾勒" },
  { id: "dotted", name: "银角留白", description: "四角轻描" },
];
type DreamImage = {
  variants?: string[];
  selected_variant?: string | null;
  session_id: string;
  revision: number;
  status: "pending" | "processing" | "completed" | "failed";
  image_url: string | null;
  retry_after_seconds: number | null;
  recovery_action?: "retry_generation" | "retry_review" | "check_task" | "contact_support" | null;
  supplementary_attempts?: number;
  failure_reason?: "contains_text" | "contains_band" | "contains_panels" | "generation_failed" | "subject_mismatch" | "subject_review_unavailable" | "image_review_unavailable" | "generation_timeout" | "submission_unknown" | "prompt_too_long" | null;
};

declare global {
  interface Window {
    SpeechRecognition?: RecognitionConstructor;
    webkitSpeechRecognition?: RecognitionConstructor;
  }
}

// The local Dream Card API runs on 8001. An explicit VITE_API_BASE_URL still
// takes precedence for deployed environments.
const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "/api/v1";
const API_ORIGIN = API_BASE.replace(/\/api\/v1$/, "");
const SESSION_KEY = "dreamcard.recentSession";
const DRAFT_KEY = "dreamcard.draft";
const AUTH_KEY = "lucidream.inviteAuthenticated";
const DREAMCARD_FRAME_KEY = "lucidream.dreamcardFrame";
// Real image generation is enabled; demo mode is only for isolated UI previews.
const IMAGE_GENERATION_DEMO = false;
const IMAGE_GENERATION_STAGES = ["正在搭建梦境构图", "正在调和光线与色彩", "正在整理梦中的细节"];
const AUTH_NAV_ITEMS: TubelightNavItem[] = [
  { name: "记录梦境", value: "record", icon: PenLine },
  { name: "梦境册", value: "archive", icon: BookOpen },
  { name: "账户额度", value: "account", icon: CircleUserRound },
  { name: "设置隐私", value: "settings", icon: Settings2 },
];
const CATEGORIES: Array<{ key: SymbolKey; label: string; hint: string }> = [
  { key: "scenes", label: "场景", hint: "梦发生在哪里" },
  { key: "dreamer", label: "梦中的你", hint: "只确认你在梦中的形象，不是现实性别，也不是遇见的其他角色" },
  { key: "characters", label: "遇到的人物与生物", hint: "除你之外的其他角色，包括独立出现的未来的你" },
  { key: "objects", label: "物件", hint: "被注意到的东西" },
  { key: "actions", label: "动作", hint: "梦里发生了什么" },
  { key: "emotions", label: "情绪", hint: "当时的感受" },
  { key: "relationships", label: "关系", hint: "人物与物件的联系" },
  { key: "reality_context", label: "近期现实经历", hint: "清醒生活中的具体背景，仅用于文字解读" },
  { key: "uncertain_fields", label: "还不确定", hint: "需要由你确认的细节" },
];
const EXAMPLES = [
  { label: "银色鹿群", text: "我在一片很安静的森林里奔跑，前面有一只银色的鹿。天空很暗，但我并不害怕。" },
  { label: "无尽走廊", text: "我回到小时候的学校，走廊一直没有尽头，手里拿着一把不知道能打开哪里的钥匙。" },
  { label: "玻璃森林", text: "我走进一片透明的森林，树枝像玻璃一样发出微弱的光，远处有人在叫我的名字。" },
];
const ROTATING_PROMPTS = [
  "梦发生在哪里？你看见了谁，又有什么感受……",
  "哪怕只记得一个画面，也可以从这里开始……",
  "比如，走进一片玻璃森林，听见有人叫你的名字……",
];
const REALITY_QUESTION_MARKERS = ["最近", "这段时间", "现实生活", "生活中", "工作中", "清醒时"];

gsap.registerPlugin(useGSAP);

function DreamCardGenerationWaiting({ stage, revealing = false, onRevealed }: { stage: string; revealing?: boolean; onRevealed?: () => void }) {
  const overlayRef = useRef<HTMLDivElement>(null);
  useGSAP(() => {
    const media = gsap.matchMedia();
    media.add("(prefers-reduced-motion: no-preference)", () => {
      gsap.timeline({ defaults: { ease: "power2.out" } })
        .from(".dreamcard-waiting-visual", { opacity: 0, scale: .92, duration: .4 }, .4)
        .from(".dreamcard-waiting-caption", { opacity: 0, y: 6, duration: .35, stagger: .12 }, .9);
    });
    return () => media.revert();
  }, { scope: overlayRef });
  useLayoutEffect(() => {
    if (!revealing || !overlayRef.current) return;
    const overlay = overlayRef.current;
    const bounds = overlay.getBoundingClientRect();
    const node = overlay.querySelector(".whirlpool-loader")?.getBoundingClientRect();
    if (node) {
      overlay.style.setProperty("--reveal-x", `${((node.left + node.width / 2 - bounds.left) / bounds.width) * 100}%`);
      overlay.style.setProperty("--reveal-y", `${((node.top + node.height / 2 - bounds.top) / bounds.height) * 100}%`);
    }
  }, [revealing]);
  return <div ref={overlayRef} className={`dreamcard-generation-waiting${revealing ? " is-revealing" : ""}`} role="status" aria-live="polite" onAnimationEnd={(event) => { if (event.target === event.currentTarget && event.animationName === "dreamcard-image-reveal") onRevealed?.(); }}>
    <div className="dreamcard-waiting-visual" aria-hidden="true">
      <WhirlpoolLoader size={210} />
    </div>
    <strong className="dreamcard-waiting-caption">{stage}</strong>
    <p className="dreamcard-waiting-caption">梦境正在显影，这里会自动更新</p>
    <div className="dreamcard-waiting-dots dreamcard-waiting-caption" aria-hidden="true"><i /><i /><i /></div>
  </div>;
}

function recordDate(createdAt?: string): string {
  const date = createdAt ? new Date(createdAt) : new Date();
  return Number.isNaN(date.valueOf()) ? new Date().toLocaleDateString("sv-SE") : date.toLocaleDateString("sv-SE");
}

function displayDreamNumber(session: DreamSession): string {
  const datePart = recordDate(session.created_at).replace(/-/g, "");
  const shortId = session.id.replace(/-/g, "").slice(0, 4).toUpperCase();
  return `MK-${datePart}-${shortId}`;
}

function cardCoreReading(draft: PersonalizedInterpretation | SourceBackedInterpretation): string {
  const text = (draft.card_summary || ("reflections" in draft
    ? draft.reflections.join("")
    : draft.readings.map((reading) => reading.reading).join("")))
    .replace(/\s+/g, " ")
    .trim();
  if (text.length <= 180) return text;

  const sentences = text.match(/[^。！？!?]+[。！？!?]?/g) ?? [];
  let complete = "";
  for (const sentence of sentences) {
    if ((complete + sentence).length > 180) break;
    complete += sentence;
  }
  if (complete.length >= 130) return complete;
  return `${text.slice(0, 179).replace(/[，、；：\s]+$/u, "")}。`;
}

function cardTitleClass(title: string): string {
  if (title.length >= 16) return "is-very-long";
  if (title.length >= 11) return "is-long";
  return "";
}

function calibratedQuestion(question: string): string {
  if (REALITY_QUESTION_MARKERS.some((marker) => question.includes(marker)) && question.length <= 80) return question;
  return "最近的生活里，梦中最突出的感受更接近某件正在承受的事，还是一段需要重新确认的关系？";
}

function interpretationAsText(response: InterpretationResponse): string {
  const draft = response.interpretation;
  if (response.generation_mode === "personalized") {
    const personalized = draft as PersonalizedInterpretation;
    return [
      personalized.title,
      `梦境片段\n${personalized.dream_summary}`,
      `逐层解读\n${personalized.reflections.map((reflection, index) => `${index + 1}. ${reflection}`).join("\n")}`,
      `现实校准\n${calibratedQuestion(personalized.reflection_question)}`,
      `温和行动\n${personalized.gentle_action}`,
    ].join("\n\n");
  }
  const sourced = draft as SourceBackedInterpretation;
  return [
    sourced.title,
    ...sourced.readings.map((reading) => `梦境回望\n${reading.reading}`),
    `值得留意\n${calibratedQuestion(sourced.reflection_question)}`,
  ].join("\n\n");
}

function emptySymbols(): DreamSymbols {
  return { dreamer: [], scenes: [], characters: [], objects: [], actions: [], emotions: [], relationships: [], reality_context: [], uncertain_fields: [] };
}

async function apiRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    credentials: "include",
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    if (response.status === 401 && !path.startsWith("/auth/")) window.dispatchEvent(new Event("dreamcard-auth-expired"));
    if (payload?.error?.code === "image_quota_exhausted") {
      throw Object.assign(new Error("额度不足"), { status: response.status, code: "image_quota_exhausted" });
    }
    const message = payload && typeof payload === "object" && "error" in payload
      ? (payload.error as { message?: unknown })?.message
      : null;
    throw Object.assign(new Error(typeof message === "string" ? message : "服务暂时不可用，请稍后重试"), { status: response.status, code: payload?.error?.code });
  }
  return payload as T;
}

async function requestForRestore<T>(path: string, signal: AbortSignal): Promise<T> {
  const controller = new AbortController();
  const cancel = () => controller.abort();
  signal.addEventListener("abort", cancel, { once: true });
  if (signal.aborted) cancel();
  const timer = window.setTimeout(cancel, 20000);
  try {
    return await apiRequest<T>(path, { signal: controller.signal });
  } finally {
    window.clearTimeout(timer);
    signal.removeEventListener("abort", cancel);
  }
}

export default function App() {
  const [showInviteLogin, setShowInviteLogin] = useState(() => window.location.hash === "#invite");
  const [showSignOutConfirm, setShowSignOutConfirm] = useState(false);
  const [showSupplementConfirm, setShowSupplementConfirm] = useState(false);
  const [restoringArticle, setRestoringArticle] = useState(false);
  const [showGenerationOptions, setShowGenerationOptions] = useState(false);
  const [showImageRegenerateConfirm, setShowImageRegenerateConfirm] = useState(false);
  const [characterAppearance, setCharacterAppearance] = useState<"unspecified" | "male" | "female" | "none" | "other" | null>(null);
  const [characterForm, setCharacterForm] = useState("");
  const [showAppearanceReminder, setShowAppearanceReminder] = useState(false);
  const [editingAppearance, setEditingAppearance] = useState(false);
  const [showSubjectConfirm, setShowSubjectConfirm] = useState(false);
  const confirmingSymbolsRef = useRef(false);
  const appearanceLabel = characterAppearance === "other" ? characterForm.trim() : characterAppearance === "male" ? "男性形象" : characterAppearance === "female" ? "女性形象" : "没有明确形象";
  const loadAppearance = (value: DreamSession) => {
    const saved = value.status === "ready_to_generate";
    const appearance = saved ? value.character_appearance ?? null : value.dreamer_suggestion?.appearance ?? null;
    setCharacterAppearance(appearance);
    setCharacterForm(saved ? value.character_form ?? "" : value.dreamer_suggestion?.form ?? "");
    setEditingAppearance(!appearance);
  };
  const appearanceRef = useRef<HTMLDivElement>(null);
  const [adjustmentTop, setAdjustmentTop] = useState(100);
  const openImageAdjustment = () => {
    setAdjustmentTop(window.scrollY + Math.max(120, window.innerHeight * 0.24));
    setShowImageRegenerateConfirm(true);
  };
  const [cardSettings, setCardSettings] = useState<Record<string, { date: string; showLabel: boolean; showDate?: boolean }>>(() => {
    try { return JSON.parse(localStorage.getItem("dreamcard.textSettings") ?? "{}"); } catch { return {}; }
  });
  const updateCardSettings = (id: string, date: string, showLabel: boolean, showDate?: boolean) => {
    setCardSettings((current) => {
      const next = { ...current, [id]: { date, showLabel, showDate: showDate ?? current[id]?.showDate ?? true } };
      localStorage.setItem("dreamcard.textSettings", JSON.stringify(next));
      return next;
    });
  };
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [accountProfile, setAccountProfile] = useState<AccountProfile | undefined>();
  const [checkingAuth, setCheckingAuth] = useState(true);
  const [restoreError, setRestoreError] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    requestForRestore<{ account_id: string; profile?: AccountProfile }>("/auth/me", controller.signal).then(({ account_id, profile }) => {
      if (controller.signal.aborted) return;
      setAccountProfile(profile);
      if (localStorage.getItem("dreamcard.account") !== account_id) {
        localStorage.removeItem(SESSION_KEY);
        clearResultView(localStorage);
      }
      localStorage.setItem("dreamcard.account", account_id);
      setRestoring(true);
      setIsAuthenticated(true);
      if (new URLSearchParams(window.location.search).get("zhihu") === "success") {
        const url = new URL(window.location.href);
        url.searchParams.delete("zhihu");
        url.hash = "";
        window.history.replaceState(null, "", url.pathname + url.search);
        setShowInviteLogin(false);
      }
    }).catch((error) => {
      if (controller.signal.aborted) return;
      if (error.status === 401 || error.status === 403) localStorage.removeItem(AUTH_KEY);
      else setRestoreError(true);
    })
      .finally(() => { if (!controller.signal.aborted) setCheckingAuth(false); });
    const expired = () => {
      interpretationAbortController.current?.abort();
      setIsAuthenticated(false);
      setSession(null);
      setInterpretation(null);
      setDreamImage(null);
      setShowInviteLogin(true);
      localStorage.removeItem(SESSION_KEY);
      localStorage.removeItem(AUTH_KEY);
      clearResultView(localStorage);
    };
    window.addEventListener("dreamcard-auth-expired", expired);
    const accountChanged = (event: StorageEvent) => {
      if (event.key !== "dreamcard.account" || event.oldValue === event.newValue) return;
      interpretationAbortController.current?.abort();
      setIsAuthenticated(false);
      setSession(null);
      setInterpretation(null);
      setDreamImage(null);
      setShowDreamCardPage(false);
      setShowDreamCardPreview(false);
      setActiveModule("record");
      setShowInviteLogin(true);
      if (event.oldValue) setDreamText("");
    };
    window.addEventListener("storage", accountChanged);
    return () => { controller.abort(); window.removeEventListener("dreamcard-auth-expired", expired); window.removeEventListener("storage", accountChanged); };
  }, []);
  const [activeModule, setActiveModule] = useState<ProductModule>("record");
  const [activeLandingSection, setActiveLandingSection] = useState<LandingSection>("record");
  const [dreamText, setDreamText] = useState(() => localStorage.getItem(DRAFT_KEY) ?? "");
  const [session, setSession] = useState<DreamSession | null>(null);
  const [symbols, setSymbols] = useState<DreamSymbols>(emptySymbols());
  const [clarificationAnswer, setClarificationAnswer] = useState("");
  const [clarificationAttention, setClarificationAttention] = useState(false);
  const [loading, setLoading] = useState(false);
  const [restoring, setRestoring] = useState(true);
  const [error, setError] = useState("");
  const [inputNotice, setInputNotice] = useState<{ message: string } | null>(null);
  const [loginGateSignal, setLoginGateSignal] = useState(0);
  const [speechStatus, setSpeechStatus] = useState<SpeechStatus>("idle");
  const [interimText, setInterimText] = useState("");
  const [voiceIssue, setVoiceIssue] = useState<SpeechIssue | null>(null);
  const [interpretation, setInterpretation] = useState<InterpretationResponse | null>(null);
  const [showInterpretationResult, setShowInterpretationResult] = useState(true);
  const [dreamImage, setDreamImage] = useState<DreamImage | null>(null);
  const [imageVersion, setImageVersion] = useState(() => Date.now());
  const [imageDisplayFailed, setImageDisplayFailed] = useState(false);
  const [imageLoadTimedOut, setImageLoadTimedOut] = useState(false);
  const [imageReveal, setImageReveal] = useState<"idle" | "waiting" | "revealing">("idle");
  const [showDreamCardPreview, setShowDreamCardPreview] = useState(false);
  const [showDreamCardPage, setShowDreamCardPage] = useState(false);
  const [toolbarCollapsed, setToolbarCollapsed] = useState(true);
  const [framePanelOpen, setFramePanelOpen] = useState(false);
  const [enteringStudio, setEnteringStudio] = useState(false);
  const [dreamCardFrame, setDreamCardFrame] = useState<DreamCardFrame>(() => {
    const savedFrame = localStorage.getItem(DREAMCARD_FRAME_KEY);
    return DREAM_CARD_FRAMES.find((frame) => frame.id === savedFrame)?.id ?? "moonline";
  });
  const [downloading, setDownloading] = useState(false);
  const [imageGenerating, setImageGenerating] = useState(false);
  const [loadedImageSource, setLoadedImageSource] = useState<string | null>(null);
  const [imageLoadingStage, setImageLoadingStage] = useState(0);
  const [generationChoice, setGenerationChoice] = useState<"interpretation" | "together" | null>(null);
  const [generationNotice, setGenerationNotice] = useState("");
  const speechSession = useRef<ReturnType<typeof startSpeechSession> | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const dreamCardRef = useRef<HTMLElement>(null);
  const clarificationRef = useRef<HTMLElement>(null);
  const clarificationAttentionTimer = useRef<number | null>(null);
  const interpretationAbortController = useRef<AbortController | null>(null);
  const [promptIndex, setPromptIndex] = useState(0);
  const [composerFocused, setComposerFocused] = useState(false);
  const [dreamLoadingStage, setDreamLoadingStage] = useState(0);

  const phase = session?.status === "safety_interrupted" ? "safety" : showDreamCardPage && (interpretation || (loading && generationChoice === "together")) ? "dreamcard" : interpretation && showInterpretationResult ? "interpretation" : session?.status === "ready_to_generate" ? "confirmed" : session ? "review" : "input";
  const imageSource = dreamImage?.image_url ? `${IMAGE_GENERATION_DEMO ? "" : API_ORIGIN}${dreamImage.image_url}${dreamImage.image_url.includes("?") ? "&" : "?"}v=${imageVersion}` : null;
  useEffect(() => {
    setImageDisplayFailed(false);
    setImageLoadTimedOut(false);
  }, [imageSource]);
  useEffect(() => {
    // This deadline only concerns downloading an existing image, never model generation.
    if (phase !== "dreamcard" || activeModule !== "record" || dreamImage?.status !== "completed" || !imageSource || imageDisplayFailed || loadedImageSource === imageSource) return;
    const timer = window.setTimeout(() => {
      setImageLoadTimedOut(true);
      setImageDisplayFailed(true);
      setImageReveal("idle");
    }, 20000);
    return () => window.clearTimeout(timer);
  }, [phase, activeModule, dreamImage?.status, imageSource, loadedImageSource, imageDisplayFailed]);
  const listening = speechStatus !== "idle";
  const displayedText = appendSpeech(dreamText, interimText);
  const showPrompt = !displayedText && !composerFocused && !listening;
  const totalSymbols = useMemo(() => Object.values(symbols).reduce((sum, values) => sum + values.length, 0), [symbols]);
  const isDreamSubmitting = loading && phase === "input";

  useEffect(() => {
    if (!enteringStudio) return;
    if (phase !== "interpretation" || activeModule !== "record") {
      setEnteringStudio(false);
      return;
    }
    const timer = window.setTimeout(() => {
      window.scrollTo({ top: 0, behavior: "instant" });
      setShowDreamCardPage(true);
      setEnteringStudio(false);
    }, window.matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : 300);
    return () => window.clearTimeout(timer);
  }, [enteringStudio, phase, activeModule]);
  const isInterpretationLoading = loading && generationChoice === "interpretation";
  const isImageWaiting = (loading && generationChoice === "together") || imageGenerating || dreamImage?.status === "pending" || dreamImage?.status === "processing";
  const dreamCardProgress = !showDreamCardPreview
    ? { label: "文字解读完成", title: "继续制作梦卡", detail: "生成画面制作梦卡" }
    : dreamImage?.status === "completed"
      ? { label: "梦卡制作完成", title: "梦卡已生成", detail: "前往预览并下载" }
      : dreamImage?.status === "failed"
        ? { label: "梦卡制作未完成", title: "画面生成失败", detail: "前往页面重新生成" }
        : { label: "梦卡制作中", title: "画面正在生成", detail: "前往查看生成进度" };
  const interpretationSymbols = useMemo(() => {
    const visibleKeys: SymbolKey[] = ["scenes", "characters", "objects", "actions", "emotions", "relationships"];
    const items = visibleKeys.flatMap((key) => symbols[key]).map((item) => item.trim()).filter(Boolean);
    return Array.from(new Set(items)).slice(0, 6).length
      ? Array.from(new Set(items)).slice(0, 6)
      : ["梦境片段", "情绪线索", "现实回望"];
  }, [symbols]);
  const dreamLoadingLabel = ["正在整理梦境", "正在提取线索", "内容较长，继续整理"][dreamLoadingStage];

  useLayoutEffect(() => {
    const previousScrollRestoration = window.history.scrollRestoration;
    window.history.scrollRestoration = "manual";
    const resetLandingPosition = () => {
      if (window.location.hash && window.location.hash !== "#invite") {
        window.history.replaceState(null, "", `${window.location.pathname}${window.location.search}`);
      }
      if (window.location.hash !== "#invite") {
        setActiveLandingSection("record");
        window.scrollTo(0, 0);
      }
    };
    resetLandingPosition();
    const frame = window.requestAnimationFrame(resetLandingPosition);
    window.addEventListener("pageshow", resetLandingPosition);
    return () => {
      window.cancelAnimationFrame(frame);
      window.removeEventListener("pageshow", resetLandingPosition);
      window.history.scrollRestoration = previousScrollRestoration;
    };
  }, []);

  useEffect(() => {
    const syncInviteRoute = () => setShowInviteLogin(window.location.hash === "#invite");
    window.addEventListener("popstate", syncInviteRoute);
    window.addEventListener("hashchange", syncInviteRoute);
    return () => {
      window.removeEventListener("popstate", syncInviteRoute);
      window.removeEventListener("hashchange", syncInviteRoute);
    };
  }, []);

  useEffect(() => {
    if (!showSignOutConfirm) return;
    const previousOverflow = document.body.style.overflow;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setShowSignOutConfirm(false);
    };
    document.body.style.overflow = "hidden";
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.body.style.overflow = previousOverflow;
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [showSignOutConfirm]);

  useEffect(() => {
    if (!showGenerationOptions) return;
    const previousOverflow = document.body.style.overflow;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setShowGenerationOptions(false);
    };
    document.body.style.overflow = "hidden";
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.body.style.overflow = previousOverflow;
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [showGenerationOptions]);

  useEffect(() => {
    window.scrollTo({ top: 0, behavior: "smooth" });
  }, [phase, activeModule]);

  useEffect(() => {
    const controller = new AbortController();
    if (!isAuthenticated) {
      setRestoring(false);
      return () => controller.abort();
    }
    const sessionId = localStorage.getItem(SESSION_KEY);
    if (!sessionId) {
      setRestoring(false);
      return () => controller.abort();
    }
    setRestoring(true);
    const restoreRequest = <T,>(path: string) => requestForRestore<T>(path, controller.signal);
    const restoreSession = async () => {
      try {
        const restored = await restoreRequest<DreamSession>(`/dreams/${sessionId}`);
        if (controller.signal.aborted) return;
        setSession(restored);
        setSymbols(restored.symbols);
        setDreamText(restored.dream_text);
        setClarificationAnswer(restored.clarification_answer ?? "");
        loadAppearance(restored);
        // Incomplete/failed archive entries open their saved facts without
        // treating an absent or failed interpretation as a network outage.
        if (readResultView(localStorage, restored.id, restored.revision) === "record") return;
        try {
          const restoredInterpretation = await restoreRequest<InterpretationResponse>(`/dreams/${restored.id}/interpretation`);
          if (controller.signal.aborted) return;
          setInterpretation(restoredInterpretation);
          const savedView = readResultView(localStorage, restored.id, restoredInterpretation.revision);
          setShowDreamCardPage(savedView === "dreamcard");
          if (!IMAGE_GENERATION_DEMO) {
            try {
              const restoredImage = await restoreRequest<DreamImage>(`/dreams/${restored.id}/image`);
              if (controller.signal.aborted) return;
              setDreamImage(restoredImage);
              setShowDreamCardPreview(true);
              // Older sessions have no view preference; an existing image
              // means the user has already entered the studio at least once.
              if (savedView === null) setShowDreamCardPage(true);
            } catch (error) {
              // Only a confirmed missing image is an ordinary incomplete step.
              if ((error as { status?: number }).status !== 404) throw error;
            }
          }
        } catch (error) {
          if ((error as { code?: string }).code === "generation_interrupted") {
            setError("上次解读已中断，梦境内容已保留。请点击生成按钮重新开始解析。");
            return;
          }
          // Network/server failures must not masquerade as a missing article.
          if ((error as { status?: number }).status !== 404) throw error;
        }
      } catch (error) {
        if (!controller.signal.aborted) {
          const status = (error as { status?: number }).status;
          if (status === 404 || status === 403) {
            localStorage.removeItem(SESSION_KEY);
            clearResultView(localStorage);
            setSession(null);
            setInterpretation(null);
            setDreamImage(null);
            setShowDreamCardPage(false);
            setShowDreamCardPreview(false);
            setError("这条记录已不存在或无法访问，请重新记录梦境。");
          } else if (status !== 401) {
            setRestoreError(true);
          }
        }
      } finally {
        if (!controller.signal.aborted) setRestoring(false);
      }
    };
    void restoreSession();
    return () => controller.abort();
  }, [isAuthenticated]);

  useEffect(() => {
    // Do not overwrite the saved view with the initial state during restoration.
    if (restoring || restoreError || !isAuthenticated || !session || !interpretation) return;
    saveResultView(localStorage, session.id, interpretation.revision, showDreamCardPage ? "dreamcard" : "interpretation");
  }, [restoring, restoreError, isAuthenticated, session?.id, interpretation?.revision, showDreamCardPage]);

  useEffect(() => {
    if (dreamText) localStorage.setItem(DRAFT_KEY, dreamText);
    else localStorage.removeItem(DRAFT_KEY);
  }, [dreamText]);

  useEffect(() => {
    if (!isDreamSubmitting) {
      setDreamLoadingStage(0);
      return;
    }
    const extractingTimer = window.setTimeout(() => setDreamLoadingStage(1), 5000);
    const longTimer = window.setTimeout(() => setDreamLoadingStage(2), 12000);
    return () => {
      window.clearTimeout(extractingTimer);
      window.clearTimeout(longTimer);
    };
  }, [isDreamSubmitting]);

  useEffect(() => {
    if (!inputNotice) return;
    const dismiss = () => setInputNotice(null);
    const timer = window.setTimeout(dismiss, 3000);
    // Use pointerdown, not click: the click that opens the notice must not close it.
    const events = ["pointerdown", "keydown", "input", "wheel", "touchmove", "scroll"] as const;
    events.forEach((event) => document.addEventListener(event, dismiss, { capture: true, passive: true }));
    return () => {
      window.clearTimeout(timer);
      events.forEach((event) => document.removeEventListener(event, dismiss, true));
    };
  }, [inputNotice]);

  useEffect(() => {
    if (!error) return;
    const timer = window.setTimeout(() => setError(""), 4500);
    return () => window.clearTimeout(timer);
  }, [error]);

  useEffect(() => {
    if (!loginGateSignal) return;
    const timer = window.setTimeout(() => setLoginGateSignal(0), 5000);
    return () => window.clearTimeout(timer);
  }, [loginGateSignal]);

  useEffect(() => {
    if (activeModule !== "record" || phase !== "input") return;
    const sectionIds: LandingSection[] = ["record", "process", "showcase", "pricing", "sources"];
    let frame = 0;
    const syncActiveSection = () => {
      frame = 0;
      const marker = window.innerHeight * 0.3;
      let current: LandingSection = "record";
      for (const id of sectionIds) {
        const section = document.getElementById(id);
        if (section && section.getBoundingClientRect().top <= marker) current = id;
      }
      setActiveLandingSection((previous) => previous === current ? previous : current);
    };
    const scheduleSync = () => {
      if (!frame) frame = window.requestAnimationFrame(syncActiveSection);
    };
    syncActiveSection();
    window.addEventListener("scroll", scheduleSync, { passive: true });
    window.addEventListener("resize", scheduleSync);
    return () => {
      window.removeEventListener("scroll", scheduleSync);
      window.removeEventListener("resize", scheduleSync);
      if (frame) window.cancelAnimationFrame(frame);
    };
  }, [activeModule, phase]);

  useEffect(() => {
    if (!showPrompt) return;
    const promptTimer = window.setInterval(() => {
      setPromptIndex((current) => (current + 1) % ROTATING_PROMPTS.length);
    }, 7000);
    return () => window.clearInterval(promptTimer);
  }, [showPrompt]);

  useLayoutEffect(() => {
    const textarea = textareaRef.current;
    if (!textarea) return;
    const resize = () => {
      textarea.style.height = "28px";
      const height = Math.min(184, Math.max(28, textarea.scrollHeight));
      textarea.style.height = `${height}px`;
      textarea.style.overflowY = textarea.scrollHeight > 184 ? "auto" : "hidden";
    };
    resize();
    // Re-measure wrapping when fonts finish loading or the viewport changes.
    let width = textarea.clientWidth;
    const observer = new ResizeObserver(() => {
      if (textarea.clientWidth !== width) { width = textarea.clientWidth; resize(); }
    });
    observer.observe(textarea);
    document.fonts.addEventListener("loadingdone", resize);
    return () => { observer.disconnect(); document.fonts.removeEventListener("loadingdone", resize); };
  }, [displayedText, phase, restoring]);

  useEffect(() => () => {
    speechSession.current?.dispose();
    interpretationAbortController.current?.abort();
  }, []);

  useEffect(() => {
    if (IMAGE_GENERATION_DEMO || imageGenerating) return;
    if (!session || !dreamImage || (dreamImage.status !== "pending" && dreamImage.status !== "processing")) return;
    const timer = window.setTimeout(() => {
      apiRequest<DreamImage>(`/dreams/${session.id}/image`)
        .then(setDreamImage)
        .catch((requestError) => {
          if (requestError.status >= 400 && requestError.status < 500) {
            setDreamImage((current) => current ? { ...current, status: current.image_url ? "completed" : "failed", recovery_action: null } : current);
            setError(requestError.message);
            return;
          }
          // A temporary polling failure says nothing about the provider task.
          // Keep polling instead of converting it into a generation failure.
          setDreamImage((current) => current ? { ...current, retry_after_seconds: 5 } : current);
          setError(requestError instanceof Error ? `连接暂时中断，正在继续确认图片状态：${requestError.message}` : "连接暂时中断，正在继续确认图片状态");
        });
    }, (dreamImage.retry_after_seconds ?? 3) * 1000);
    return () => window.clearTimeout(timer);
  }, [dreamImage, session, imageGenerating]);

  useEffect(() => {
    if (!IMAGE_GENERATION_DEMO || dreamImage?.status !== "processing") return;
    const timer = window.setTimeout(() => {
      setDreamImage((current) => current === dreamImage ? { ...current, status: "completed", image_url: "/assets/showcase/dream-preview.svg" } : current);
    }, 7800);
    return () => window.clearTimeout(timer);
  }, [dreamImage]);

  useEffect(() => {
    if (!isImageWaiting) {
      setImageLoadingStage(0);
      return;
    }
    const timer = window.setInterval(() => {
      setImageLoadingStage((current) => (current + 1) % IMAGE_GENERATION_STAGES.length);
    }, 2600);
    return () => window.clearInterval(timer);
  }, [isImageWaiting]);

  useEffect(() => {
    if (dreamText.length >= MAX_DREAM_CHARS && listening) {
      speechSession.current?.dispose();
      setVoiceIssue(speechIssue("limit"));
    }
  }, [dreamText, listening]);

  const editDreamText = (value: string) => {
    // Typing takes over the visible text, including the latest interim words.
    speechSession.current?.dispose();
    speechSession.current = null;
    setInterimText("");
    setVoiceIssue(null);
    setDreamText(value.slice(0, MAX_DREAM_CHARS));
  };

  const submitDream = async () => {
    if (listening) return;
    if (!dreamText.trim()) {
      setInputNotice({ message: "先写下一点你记得的梦境内容" });
      return;
    }
    setInputNotice(null);
    setError("");
    if (!isAuthenticated) {
      setLoginGateSignal((current) => current + 1);
      return;
    }
    setLoading(true);
    try {
      const created = await apiRequest<DreamSession>("/dreams/extract", {
        method: "POST",
        body: JSON.stringify({ dream_text: dreamText.trim() }),
      });
      localStorage.setItem(SESSION_KEY, created.id);
      clearResultView(localStorage);
      setSession(created);
      setSymbols(created.symbols);
      setClarificationAnswer(created.clarification_answer ?? "");
      loadAppearance(created);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "梦境整理暂时失败，请稍后重试");
    } finally {
      setLoading(false);
    }
  };

  const updateSymbol = (key: SymbolKey, index: number, value: string) => {
    setSymbols((current) => ({ ...current, [key]: current[key].map((item, itemIndex) => itemIndex === index ? value : item) }));
  };

  const removeSymbol = (key: SymbolKey, index: number) => {
    setSymbols((current) => ({ ...current, [key]: current[key].filter((_, itemIndex) => itemIndex !== index) }));
  };

  const addSymbol = (key: SymbolKey) => {
    setSymbols((current) => ({ ...current, [key]: [...current[key], ""] }));
  };

  const confirmSymbols = async (subjectConfirmed = false) => {
    if (!session || confirmingSymbolsRef.current) return;
    if (!characterAppearance || (characterAppearance === "other" && !characterForm.trim())) {
      setEditingAppearance(true);
      appearanceRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
      setShowAppearanceReminder(true);
      return;
    }
    if (session.clarification && !clarificationAnswer) {
      setError("请先选择一个最接近的答案，也可以选择“记不清”。");
      setClarificationAttention(true);
      window.requestAnimationFrame(() => {
        clarificationRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
        clarificationRef.current?.focus({ preventScroll: true });
      });
      if (clarificationAttentionTimer.current) window.clearTimeout(clarificationAttentionTimer.current);
      clarificationAttentionTimer.current = window.setTimeout(() => setClarificationAttention(false), 1800);
      return;
    }
    if (!subjectConfirmed) {
      setShowSubjectConfirm(true);
      return;
    }
    confirmingSymbolsRef.current = true;
    const cleaned = Object.fromEntries(Object.entries(symbols).map(([key, values]) => [key, values.map((item) => item.trim()).filter(Boolean)])) as DreamSymbols;
    setLoading(true);
    setError("");
    try {
      const updated = await apiRequest<DreamSession>(`/dreams/${session.id}/symbols`, {
        method: "PUT",
        body: JSON.stringify({ symbols: { ...cleaned, dreamer: [appearanceLabel] }, clarification_answer: clarificationAnswer || null, character_appearance: characterAppearance, character_form: characterAppearance === "other" ? characterForm.trim() : "" }),
      });
      setSession(updated);
      setSymbols(updated.symbols);
      setShowSubjectConfirm(false);
      if (interpretation && updated.revision !== interpretation.revision) {
        setInterpretation(null);
        setDreamImage(null);
        setShowDreamCardPreview(false);
        setShowDreamCardPage(false);
        setShowInterpretationResult(true);
      }
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "确认失败，请重试");
      setShowSubjectConfirm(false);
    } finally {
      confirmingSymbolsRef.current = false;
      setLoading(false);
    }
  };

  const generateDreamCard = async (includeImage: boolean) => {
    if (!session) return;
    interpretationAbortController.current?.abort();
    const controller = new AbortController();
    interpretationAbortController.current = controller;
    const startedAt = performance.now();
    setShowDreamCardPreview(includeImage);
    setShowDreamCardPage(includeImage);
    setGenerationChoice(includeImage ? "together" : "interpretation");
    setGenerationNotice("");
    setLoading(true);
    setError("");
    try {
      const generated = await apiRequest<InterpretationResponse>(
        // 用户再次点击时，显式允许重试此前失败的生成；首次调用不受影响。
        `/dreams/${session.id}/interpretation?retry=true`,
        { method: "POST", signal: controller.signal },
      );
      if (!includeImage) {
        const remaining = Math.max(0, 1800 - (performance.now() - startedAt));
        if (remaining) await new Promise((resolve) => window.setTimeout(resolve, remaining));
      }
      if (controller.signal.aborted) return;
      setInterpretation(generated);
      setShowInterpretationResult(true);
      setDreamImage(null);
      if (includeImage) void generateDreamImage(session.id);
    } catch (requestError) {
      if (requestError instanceof DOMException && requestError.name === "AbortError") return;
      if (includeImage) { setShowDreamCardPage(false); setShowDreamCardPreview(false); }
      setError(requestError instanceof Error ? requestError.message : "梦卡生成暂时失败，请重试");
    } finally {
      if (interpretationAbortController.current === controller) {
        interpretationAbortController.current = null;
        setLoading(false);
        setGenerationChoice(null);
      }
    }
  };

  const cancelDreamInterpretation = () => {
    interpretationAbortController.current?.abort();
    interpretationAbortController.current = null;
    setLoading(false);
    setGenerationChoice(null);
    setError("");
  };

  const retryDreamInterpretation = () => {
    interpretationAbortController.current?.abort();
    interpretationAbortController.current = null;
    void generateDreamCard(false);
  };

  const deferDreamCardGeneration = () => {
    setShowGenerationOptions(false);
    setGenerationNotice(TEMPORARY_DEMO ? "这场梦已临时保留，服务重启后可能清空" : "这场梦已安全保存，你可以稍后回到这里开启解析。");
  };

  const chooseDreamCardGeneration = (includeImage: boolean) => {
    setShowGenerationOptions(false);
    window.scrollTo({ top: 0 });
    void generateDreamCard(includeImage);
  };

  const generateDreamImage = async (sessionId: string, retry = false, regenerate = false) => {
    if (imageGenerating) return;
    const reviewOnly = retry && !regenerate && (dreamImage?.recovery_action === "check_task" || dreamImage?.failure_reason === "subject_review_unavailable" || dreamImage?.failure_reason === "image_review_unavailable");
    setImageVersion(Date.now());
    setImageDisplayFailed(false);
    setImageReveal(dreamImage?.image_url ? "idle" : "waiting");
    if (IMAGE_GENERATION_DEMO) {
      setError("");
      setImageLoadingStage(0);
      setDreamImage({
        session_id: sessionId,
        revision: session?.revision ?? 0,
        status: "processing",
        image_url: null,
        retry_after_seconds: null,
        failure_reason: null,
      });
      return;
    }
    setImageGenerating(true);
    setError("");
    setImageLoadingStage(0);
    setDreamImage({
      session_id: sessionId,
      revision: session?.revision ?? 0,
      status: "processing",
      image_url: dreamImage?.image_url ?? null,
      variants: dreamImage?.variants,
      selected_variant: dreamImage?.selected_variant,
      supplementary_attempts: dreamImage?.supplementary_attempts,
      retry_after_seconds: null,
      failure_reason: null,
    });
    try {
      const generated = await apiRequest<DreamImage>(`/dreams/${sessionId}/image${reviewOnly ? "/review" : regenerate ? "?retry=true&regenerate=true" : retry ? "?retry=true" : ""}`, { method: "POST" });
      setDreamImage(generated);
    } catch (requestError) {
      // Submission timeouts are ambiguous: the provider may already have
      // accepted the task. Preserve the processing state and let polling ask
      // the backend for the authoritative result, avoiding a duplicate charge.
      const status = (requestError as { status?: number }).status;
      if ((requestError as { code?: string }).code === "image_quota_exhausted") {
        setDreamImage(dreamImage);
        setImageReveal("idle");
        // A rejected submission is not a failed image. Keep the existing card,
        // or return to its saved article when there is no image to show.
        if (!dreamImage?.image_url) {
          setShowDreamCardPage(false);
          setShowDreamCardPreview(false);
          setShowInterpretationResult(true);
          setEnteringStudio(false);
        }
        setError("额度不足");
        return;
      }
      if (status && status >= 400 && status < 500) {
        setDreamImage(dreamImage ?? { session_id: sessionId, revision: session?.revision ?? 1, status: "failed", image_url: null, retry_after_seconds: null });
        setImageReveal("idle");
        setError(requestError instanceof Error ? requestError.message : "暂时无法生成");
        return;
      }
      setDreamImage((current) => current ? { ...current, status: "processing", retry_after_seconds: 3 } : current);
      setError(requestError instanceof Error ? `${requestError.message}，正在核对任务状态` : "正在核对图片任务状态");
    } finally {
      setImageGenerating(false);
    }
  };

  const continueToDreamCard = () => {
    if (!session || enteringStudio) return;
    setShowDreamCardPage(true);
    setShowDreamCardPreview(true);
    window.scrollTo({ top: 0, behavior: "instant" });
    if (!dreamImage) void generateDreamImage(session.id);
  };

  const selectImageVariant = async (variant: string) => {
    if (!session || isImageWaiting) return;
    try {
      setDreamImage(await apiRequest<DreamImage>(`/dreams/${session.id}/image/select/${variant}`, { method: "POST" }));
      setImageDisplayFailed(false);
      setImageVersion(Date.now());
    } catch (e) { setError(e instanceof Error ? e.message : "切换图片失败，请重试"); }
  };

  const returnToInterpretation = async () => {
    if (!session || restoringArticle) return;
    setRestoringArticle(true);
    try {
      const saved = await apiRequest<InterpretationResponse>(`/dreams/${session.id}/interpretation`);
      if (!saved.interpretation || saved.session_id !== session.id || saved.revision !== session.revision) throw new Error("这次梦境的解读尚未完成，请稍后重试");
      setInterpretation(saved);
      setShowDreamCardPage(false);
      setShowDreamCardPreview(false);
      setShowInterpretationResult(true);
      setError("");
      window.scrollTo({ top: 0, behavior: "smooth" });
    } catch (e) { setError(e instanceof Error ? e.message : "读取解梦文章失败，请重试"); }
    finally { setRestoringArticle(false); }
  };

  const selectDreamCardFrame = (frame: DreamCardFrame) => {
    setDreamCardFrame(frame);
    localStorage.setItem(DREAMCARD_FRAME_KEY, frame);
  };

  const copyInterpretation = async () => {
    if (!interpretation) return;
    try {
      await navigator.clipboard.writeText(interpretationAsText(interpretation));
      setError("文字解读已复制");
    } catch {
      setError("复制失败，请稍后重试");
    }
  };

  const prepareDreamCard = async () => {
    const node = dreamCardRef.current;
    if (!node || !dreamImage || dreamImage.status !== "completed") throw new Error("dreamcard_not_ready");
      await document.fonts.ready;
      await Promise.all(Array.from(node.querySelectorAll("img")).map(async (image) => {
        if (!image.complete) {
          await new Promise<void>((resolve, reject) => {
            image.addEventListener("load", () => resolve(), { once: true });
            image.addEventListener("error", () => reject(new Error("dreamcard_image_load_failed")), { once: true });
          });
        }
        await image.decode();
      }));
      // Preserve the actual responsive layout, then scale the canvas. Forcing
      // a 540px clone leaves mobile descendants at their computed pixel sizes.
      const computed = getComputedStyle(node);
      const exportWidth = parseFloat(computed.width);
      const exportHeight = parseFloat(computed.height);
      const dataUrl = await toPng(node, {
        fetchRequestInit: { credentials: "same-origin" },
        cacheBust: true,
        pixelRatio: 2,
        width: exportWidth,
        height: exportHeight,
        canvasWidth: 540,
        canvasHeight: 720,
        backgroundColor: "transparent",
        style: {
          width: `${exportWidth}px`,
          height: `${exportHeight}px`,
          inlineSize: `${exportWidth}px`,
          blockSize: `${exportHeight}px`,
          margin: "0",
          borderRadius: "0",
          transform: "none",
        },
      });
      const exported = new Image();
      exported.src = dataUrl;
      await exported.decode();
      if (exported.naturalWidth !== 1080 || exported.naturalHeight !== 1440) {
        throw new Error("dreamcard_export_size_invalid");
      }
      return { dataUrl, filename: `梦卡-${(session && cardSettings[session.id]?.date) || recordDate(session?.created_at)}.png` };
  };

  const downloadDreamCard = async () => {
    if (!dreamCardRef.current || !dreamImage || dreamImage.status !== "completed") return;
    setDownloading(true);
    setError("");
    try {
      const { dataUrl, filename } = await prepareDreamCard();
      const link = document.createElement("a");
      link.download = filename;
      link.href = dataUrl;
      link.style.display = "none";
      document.body.appendChild(link);
      link.click();
      link.remove();
    } catch {
      setError("梦卡下载暂时失败，请稍后重试");
    } finally {
      setDownloading(false);
    }
  };

  const startAnotherDream = () => {
    localStorage.removeItem(SESSION_KEY);
    localStorage.removeItem(DRAFT_KEY);
    clearResultView(localStorage);
    window.location.reload();
  };

  const startOver = async () => {
    if (session && !window.confirm("这会清除当前梦境和已确认的梦象，是否继续？")) return;
    if (session) {
      try {
        await apiRequest(`/dreams/${session.id}`, { method: "DELETE" });
      } catch {
        // Keep local reset available when the backend record is already gone.
      }
    }
    localStorage.removeItem(SESSION_KEY);
    clearResultView(localStorage);
    localStorage.removeItem(DRAFT_KEY);
    setSession(null);
    setDreamText("");
    setSymbols(emptySymbols());
    setClarificationAnswer("");
    setInterpretation(null);
    setShowInterpretationResult(true);
    setDreamImage(null);
    setShowDreamCardPreview(false);
    setShowDreamCardPage(false);
    setError("");
  };

  const toggleSpeech = () => {
    if (listening) {
      speechSession.current?.stop();
      return;
    }
    setError("");
    setVoiceIssue(null);
    if (dreamText.length >= MAX_DREAM_CHARS) { setVoiceIssue(speechIssue("limit")); return; }
    const Recognition = window.SpeechRecognition ?? window.webkitSpeechRecognition;
    if (!Recognition) {
      setVoiceIssue(speechIssue("unsupported"));
      return;
    }
    speechSession.current?.dispose();
    try {
      speechSession.current = startSpeechSession(new Recognition(), {
        onStatus: setSpeechStatus,
        onFinal: (text) => setDreamText((current) => appendSpeech(current, text)),
        onInterim: setInterimText,
        onIssue: setVoiceIssue,
      });
    } catch {
      setSpeechStatus("idle");
      setVoiceIssue(speechIssue("unknown"));
    }
  };

  const openInviteLogin = () => {
    window.history.pushState(null, "", "#invite");
    setShowInviteLogin(true);
    window.scrollTo({ top: 0 });
  };

  const closeInviteLogin = () => {
    window.history.replaceState(null, "", `${window.location.pathname}${window.location.search}`);
    setShowInviteLogin(false);
    window.scrollTo({ top: 0 });
  };

  const completeInviteLogin = () => {
    setAccountProfile(undefined);
    // Return to the composer with the visitor's current draft. Only explicit
    // sign-out/start-over clears that draft; login clears the old result view.
    localStorage.removeItem(SESSION_KEY);
    clearResultView(localStorage);
    setSession(null);
    setInterpretation(null);
    setDreamImage(null);
    setShowDreamCardPage(false);
    setShowDreamCardPreview(false);
    window.history.replaceState(null, "", window.location.pathname + window.location.search);
    setShowInviteLogin(false);
    setRestoring(true);
    setIsAuthenticated(true);
    setActiveModule("record");
    setActiveLandingSection("record");
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  if (checkingAuth || restoring) return <main className="restore-screen">正在恢复上次记录…</main>;
  if (restoreError) return <main className="restore-screen">
    <section className="restore-reconnect" aria-labelledby="restore-reconnect-title">
      <h1 id="restore-reconnect-title">连接暂时中断</h1>
      <p role="status">暂时无法恢复页面，已保留本机的记录入口。<br />请检查网络后重新连接，不会重新提交生图任务。</p>
      <button type="button" className="primary-button" onClick={() => window.location.reload()}>重新连接</button>
    </section>
  </main>;

  if (showInviteLogin) return <InviteLoginPage onBack={closeInviteLogin} onSuccess={completeInviteLogin} onZhihuLogin={async () => {
    const result = await apiRequest<{ authorization_url: string }>("/auth/zhihu/start", { method: "POST" });
    const url = new URL(result.authorization_url);
    if (url.protocol !== "https:" || url.host !== "openapi.zhihu.com" || url.pathname !== "/authorize" || url.username || url.password) throw new Error("登录地址无效");
    window.location.assign(url.toString());
  }} onAuthenticate={async (invite_code) => {
    const result = await apiRequest<{ account_id: string }>("/auth/login", { method: "POST", body: JSON.stringify({ invite_code }) });
    localStorage.setItem("dreamcard.account", result.account_id);
  }} />;

  const openModule = (module: ProductModule) => {
    if (module === "record" && activeModule === "record") {
      window.scrollTo({ top: 0, behavior: "smooth" });
    }
    setActiveModule(module);
    setError("");
  };

  const signOut = async () => {
    try { await apiRequest("/auth/logout", { method: "POST" }); }
    catch { setError("退出暂时失败，请检查网络后重试"); return; }
    interpretationAbortController.current?.abort();
    interpretationAbortController.current = null;
    setShowSignOutConfirm(false);
    setAccountProfile(undefined);
    localStorage.removeItem(AUTH_KEY);
    localStorage.removeItem(SESSION_KEY);
    localStorage.removeItem("dreamcard.account");
    clearResultView(localStorage);
    localStorage.removeItem(DRAFT_KEY);
    setCharacterAppearance(null);
    setCharacterForm("");
    setShowAppearanceReminder(false);
    setShowImageRegenerateConfirm(false);
    setIsAuthenticated(false);
    setActiveModule("record");
    setActiveLandingSection("record");
    setSession(null);
    setDreamText("");
    setSymbols(emptySymbols());
    setClarificationAnswer("");
    setInterpretation(null);
    setShowInterpretationResult(true);
    setDreamImage(null);
    setShowDreamCardPreview(false);
    setShowDreamCardPage(false);
    setLoading(false);
    setGenerationChoice(null);
    setGenerationNotice("");
    setError("");
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const scrollToLandingSection = (section: LandingSection) => {
    setActiveModule("record");
    setActiveLandingSection(section);
    window.requestAnimationFrame(() => document.getElementById(section)?.scrollIntoView({ behavior: "smooth", block: "start" }));
  };

  const returnToComposer = () => {
    scrollToLandingSection("record");
    window.setTimeout(() => textareaRef.current?.focus({ preventScroll: true }), 620);
  };

  const returnToDreamInput = () => {
    localStorage.removeItem(SESSION_KEY);
    clearResultView(localStorage);
    setSession(null);
    setSymbols(emptySymbols());
    setClarificationAnswer("");
    setInterpretation(null);
    setShowInterpretationResult(true);
    setDreamImage(null);
    setShowDreamCardPreview(false);
    setShowDreamCardPage(false);
    setError("");
    setActiveModule("record");
    setActiveLandingSection("record");
    window.scrollTo({ top: 0, behavior: "smooth" });
    window.setTimeout(() => textareaRef.current?.focus({ preventScroll: true }), 420);
  };

  const returnToPreviousPage = () => {
    setError("");
    if (isInterpretationLoading) {
      cancelDreamInterpretation();
      window.scrollTo({ top: 0, behavior: "smooth" });
      return;
    }
    if (activeModule !== "record") {
      setActiveModule("record");
      window.scrollTo({ top: 0, behavior: "smooth" });
      return;
    }
    if (phase === "dreamcard") {
      void returnToInterpretation();
      return;
    }
    if (phase === "interpretation") {
      setShowInterpretationResult(false);
      window.scrollTo({ top: 0, behavior: "smooth" });
      return;
    }
    if (phase === "confirmed") {
      setSession((current) => current ? {
        ...current,
        status: current.clarification ? "awaiting_clarification" : "reviewing_symbols",
      } : current);
      window.scrollTo({ top: 0, behavior: "smooth" });
      return;
    }
    returnToDreamInput();
  };

  const returnToSavedResult = () => {
    if (!interpretation) return;
    setShowDreamCardPage(false);
    setShowInterpretationResult(true);
    setError("");
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  return (
    <div className={`app-shell${showSignOutConfirm || showGenerationOptions || showSubjectConfirm || showSupplementConfirm ? " is-modal-blurred" : ""}`} inert={showSignOutConfirm || showGenerationOptions || showSubjectConfirm || showSupplementConfirm}>
      <header className={`site-header${isAuthenticated ? " is-authenticated" : ""}`}>
        <div className={isAuthenticated ? "header-inner" : "landing-header-inner"}>
          {isAuthenticated && <div className="header-leading">
            <div className="brand-lockup">
              <DreamCardLogo />
              <button className="wordmark" onClick={() => isAuthenticated ? openModule("record") : scrollToLandingSection("record")} aria-label="返回 LUCIDREAM 首页">LUCIDREAM</button>
            </div>
            {(activeModule !== "record" || phase !== "input") && (
              <button className="flow-back-button" type="button" onClick={returnToPreviousPage} aria-label="返回上一页">
                <ArrowLeft size={16} strokeWidth={1.7} aria-hidden="true" />
                <span>返回上一页</span>
              </button>
            )}
          </div>}
          {isAuthenticated ? (
            <TubelightNavBar
              items={AUTH_NAV_ITEMS}
              activeValue={activeModule}
              onSelect={(value) => openModule(value as ProductModule)}
            />
          ) : (
            <Navbar className="landing-resizable-navbar">
              <NavBody>
                <div className="brand-lockup landing-navbar-brand">
                  <DreamCardLogo />
                  <button className="wordmark" onClick={() => scrollToLandingSection("record")} aria-label="返回 LUCIDREAM 首页">LUCIDREAM</button>
                </div>
                <NavItems items={[{ name: "记录梦境", link: "#record" }, { name: "如何生成", link: "#process" }, { name: "梦卡作品", link: "#showcase" }, { name: "分享与共鸣", link: "#pricing" }, { name: "方法与来源", link: "#sources" }]} activeLink={`#${activeLandingSection}`} onItemClick={(link) => scrollToLandingSection(link.slice(1) as LandingSection)} />
                <LiquidLoginButton onClick={openInviteLogin} attentionKey={loginGateSignal} />
              </NavBody>
              <MobileNav>
                <MobileNavHeader>
                  <button className="mobile-nav-brand" onClick={() => scrollToLandingSection("record")} aria-label="返回 LUCIDREAM 首页"><DreamCardLogo /><span className="mobile-nav-label">LUCIDREAM</span></button>
                  <MobileNavToggle isOpen={isMobileMenuOpen} onClick={() => setIsMobileMenuOpen((value) => !value)} />
                </MobileNavHeader>
                <MobileNavMenu isOpen={isMobileMenuOpen} onClose={() => setIsMobileMenuOpen(false)}>
                  {[{ name: "记录梦境", link: "#record" }, { name: "如何生成", link: "#process" }, { name: "梦卡作品", link: "#showcase" }, { name: "分享与共鸣", link: "#pricing" }, { name: "方法与来源", link: "#sources" }].map((item) => <a key={item.name} href={item.link} onClick={(event) => { event.preventDefault(); setIsMobileMenuOpen(false); scrollToLandingSection(item.link.slice(1) as LandingSection); }}>{item.name}</a>)}
                  <button className="mobile-nav-login" type="button" onClick={openInviteLogin}>Login</button>
                </MobileNavMenu>
              </MobileNav>
            </Navbar>
          )}
          {isAuthenticated && <div className="header-meta">
            {session?.model_mode === "mock" && <span className="mode-note">演示模式</span>}
            {activeModule === "record" && phase === "confirmed" && interpretation && (
              <button className="flow-forward-button" type="button" onClick={returnToSavedResult} aria-label="返回下一页">
                <span>返回下一页</span>
                <ArrowRight size={16} strokeWidth={1.7} aria-hidden="true" />
              </button>
            )}
            {isAuthenticated ? (
              <AccountMenu profile={accountProfile} onAccount={() => openModule("account")} onPrivacy={() => openModule("settings")} onSignOut={() => setShowSignOutConfirm(true)} />
            ) : <LiquidLoginButton onClick={openInviteLogin} attentionKey={loginGateSignal} />}
          </div>}
        </div>
      </header>

      {activeModule === "record" ? <main className={phase === "input" ? "input-main" : `flow-main phase-${isInterpretationLoading ? "parsing" : phase}`}>
        {phase === "input" && (
          <>
          <section id="record" className="hero-section">
            <p className="eyebrow hero-identity"><span>梦境回声</span><span className="hero-identity-divider" aria-hidden="true">·</span><span>看山说梦</span></p>
            <h1 className="hero-title"><span>将梦境</span><span>留作一张卡</span></h1>
            <p className="hero-copy hero-introduction"><span>带着梦卡去知乎，</span><span>分享故事与共鸣</span></p>
            {loginGateSignal > 0 && (
              <div key={loginGateSignal} className="login-gate-notice" role="alert" aria-live="assertive">
                请先登录后进入梦境
              </div>
            )}
            <p id="dream-composer-hint" className="hero-input-hint">记得多少，就写多少</p>
            <div className="composer-row">
              <KanshanGuide onActivate={() => textareaRef.current?.focus({ preventScroll: true })} />
              <div className={`dream-composer ${displayedText ? "has-content" : ""} ${listening ? "is-listening" : ""}`}>
                <div className="composer-textarea-wrap">
                  <textarea
                    ref={textareaRef}
                    rows={1}
                    value={displayedText}
                    onChange={(event) => editDreamText(event.target.value)}
                    onFocus={() => setComposerFocused(true)}
                    onBlur={() => setComposerFocused(false)}
                    placeholder=""
                    aria-label="梦境内容"
                    aria-describedby={`dream-composer-hint${voiceIssue ? " voice-feedback" : listening ? " voice-status" : ""}`}
                  />
                  {showPrompt && (
                    <span key={promptIndex} className="rotating-prompt" aria-hidden="true">
                      {Array.from(ROTATING_PROMPTS[promptIndex]).map((character, index) => (
                        <span key={`${character}-${index}`} className="rotating-prompt-character" style={{ animationDelay: `${index * 90}ms` }}>{character}</span>
                      ))}
                    </span>
                  )}
                  {speechStatus === "listening" && !displayedText && !composerFocused && (
                    <span className="voice-input-caret" aria-hidden="true" />
                  )}
                </div>
                <div className="composer-tools">
                  <span>{displayedText.length} / {MAX_DREAM_CHARS}</span>
                  <VoiceInput status={speechStatus} onToggle={toggleSpeech} />
                </div>
              </div>
              <FlowButton className="dream-enter-button" text={isDreamSubmitting ? dreamLoadingLabel : "进入梦境"} loading={isDreamSubmitting} onClick={submitDream} disabled={loading || listening} aria-busy={isDreamSubmitting} />
            </div>
            <div id="voice-status" className="voice-status" role="status" aria-live="polite">
              {speechStatus === "starting" ? "正在连接麦克风 · 请留意浏览器授权提示" : speechStatus === "listening" ? "正在听写 · 停止收听后可确认和提交" : speechStatus === "stopping" ? "正在确认最后一句 · 请稍候" : ""}
            </div>
            {voiceIssue && (
              <div id="voice-feedback" className="voice-feedback" role="alert">
                <div><p className="feedback-title">{voiceIssue.title}</p><p className="feedback-message">{voiceIssue.message}</p></div>
                <button type="button" onClick={() => { setVoiceIssue(null); textareaRef.current?.focus(); }}>继续文字输入</button>
              </div>
            )}
            <div className="prompt-row" aria-label="梦境示例">
              <span className="prompt-row-label">试试示例</span>
              {EXAMPLES.map((example) => <button key={example.label} disabled={listening} onClick={() => editDreamText(example.text)}>{example.label}</button>)}
            </div>
            <p className="hero-disclaimer">AI 解读仅供自我探索</p>
            <div className="input-notice-anchor">
              {inputNotice && <div className="input-notice" role="alert">{inputNotice.message}</div>}
            </div>
            <div className={`scroll-line${inputNotice ? " is-obscured" : ""}`} aria-hidden="true" />
          </section>
          {!isAuthenticated && <HomeStory
            onStart={returnToComposer}
          />}
          </>
        )}

        {phase === "review" && session && (
          <section className="review-layout">
            <aside className="review-intro">
              <p className="eyebrow align-left">梦 象 确 认</p>
              <h1 className="flow-title">从梦里<br /><span>找到线索</span></h1>
              <p className="flow-copy">修改、补充或删除任何不准确的内容。梦象用于检索与解读，近期现实经历只用于文字解读。</p>
              <div className="source-note"><span>梦境原文</span><p>{session.dream_text}</p></div>
            </aside>
            <div className="symbol-workspace">
              <div className="workspace-heading">
                <div><span>已识别</span><strong>{totalSymbols.toString().padStart(2, "0")}</strong></div>
                <p>分别确认梦中线索与近期现实经历</p>
              </div>
              <div className="symbol-list">
                {CATEGORIES.map(({ key, label, hint }, categoryIndex) => (
                  <article key={key} className={`symbol-section${key === "reality_context" ? " reality-context" : ""}`}>
                    {key === "dreamer" && <KanshanPageGuide scene="review" />}
                    <header>
                      <span className="section-number">{String(categoryIndex + 1).padStart(2, "0")}</span>
                      <div><h2>{label}</h2><p>{hint}</p></div>
                      {key === "dreamer" ? (!editingAppearance && <button className="symbol-add-button" onClick={() => setEditingAppearance(true)}>修改形象</button>) : <button className="symbol-add-button" onClick={() => addSymbol(key)}><span aria-hidden="true"><Plus size={12} strokeWidth={1.8} /></span>添加一项</button>}
                    </header>
                    {key === "dreamer" ? (!editingAppearance && <p className="empty-symbol" style={{ color: "#354052", fontSize: 16 }}>{appearanceLabel}</p>) : (symbols[key] ?? []).length === 0 ? <p className="empty-symbol">未识别到相关内容</p> : (
                      <div className="symbol-chips">
                        {symbols[key].map((item, index) => (
                          <div key={`${key}-${index}`} className="symbol-chip">
                            <input value={item} onChange={(event) => updateSymbol(key, index, event.target.value)} aria-label={`${label} ${index + 1}`} />
                            <button onClick={() => removeSymbol(key, index)} aria-label={`删除${item || label}`}>删除</button>
                          </div>
                        ))}
                      </div>
                    )}
                    {key === "dreamer" && <div ref={appearanceRef} tabIndex={-1} className="character-appearance">
                      {editingAppearance && <>
                      {!characterAppearance && (symbols.dreamer?.length ?? 0) > 1 && <><p>原文出现了多种形态，请选择这张梦卡采用哪一种</p><div className="character-appearance-options">{symbols.dreamer.map((form) => <button key={form} type="button" onClick={() => { setCharacterAppearance("other"); setCharacterForm(form); setEditingAppearance(false); }}>{form}</button>)}</div></>}
                      <p>梦中的你，是什么形态？</p>
                      <small>不是现实中的性别，也不是梦里遇见的其他角色。</small>
                      <div className="character-appearance-options" role="group" aria-label="梦中自己的形态">
                        {([ ["male", "男性形象"], ["female", "女性形象"], ["other", "其他形态"], ["unspecified", "没有明确形象"] ] as const).map(([value, label]) => <button type="button" key={value} aria-pressed={characterAppearance === value} onClick={() => setCharacterAppearance(value)}>{label}</button>)}
                      </div>
                      {characterAppearance === "other" && <label className="character-form-input">描述梦中的自己<input required maxLength={100} value={characterForm} onChange={(event) => setCharacterForm(event.target.value)} placeholder="例如：我变成了一只螃蟹" /><small>只填写你自己的形态，不是梦里看到的动物或人物。</small></label>}
                      {characterAppearance === "unspecified" && <p><small>没看见自己的样子，或记不清。</small></p>}
                      {characterAppearance && (characterAppearance !== "other" || characterForm.trim()) && <button type="button" className="secondary-button" onClick={() => setEditingAppearance(false)}>保存形象</button>}
                      </>}
                      <small>仅用于生成画面，不代表你的现实性别，也不影响文字解梦。</small>
                    </div>}
                  </article>
                ))}
              </div>
              {session.clarification && (
                <article ref={clarificationRef} tabIndex={-1} className={`clarification-card${clarificationAttention ? " needs-attention" : ""}`}>
                  <p className="eyebrow align-left">一 次 澄 清</p>
                  <h2>{session.clarification.question}</h2>
                  <div className="option-grid">
                    {session.clarification.options.map((option) => (
                      <label key={option} className={clarificationAnswer === option ? "selected" : ""}>
                        <input type="radio" name="clarification" value={option} checked={clarificationAnswer === option} onChange={() => { setClarificationAnswer(option); setClarificationAttention(false); setError(""); }} />
                        <span>{option}</span>
                      </label>
                    ))}
                  </div>
                </article>
              )}
              <div className="review-actions">
                <button className="secondary-button" onClick={startOver}>重新记录</button>
                <button className="primary-button" onClick={() => confirmSymbols()} disabled={loading}>{loading ? "正在保存" : "确认这些梦象"}</button>
              </div>
            </div>
          </section>
        )}

        {isInterpretationLoading && session && (
          <InterpretationLoading symbols={interpretationSymbols} onCancel={cancelDreamInterpretation} onRetry={retryDreamInterpretation} />
        )}

        {!isInterpretationLoading && phase === "confirmed" && session && (
          <section className="result-section">
            <p className="eyebrow">梦 象 已 确 认</p>
            <h1 className="result-title">梦象已经确认<br /><span>准备生成梦卡</span></h1>
            <KanshanPageGuide scene={loading ? "loading" : "confirmed"} />
            <div className="receipt">
              <div><span>梦境编号</span><strong title={`系统记录编号：${session.id}`}>{displayDreamNumber(session)}</strong></div>
              <div><span>梦象状态</span><strong>已确认</strong></div>
              <div><span>保存状态</span><strong className="saved-state"><i aria-hidden="true" />{TEMPORARY_DEMO ? "仅临时保留" : "已安全保存"}</strong></div>
            </div>
            <button className="primary-button standalone" type="button" onClick={() => { if (interpretation) returnToSavedResult(); else { setGenerationNotice(""); setShowGenerationOptions(true); } }} disabled={loading} aria-haspopup={interpretation ? undefined : "dialog"} aria-expanded={interpretation ? undefined : showGenerationOptions}>
              {interpretation ? "查看已保存结果" : generationChoice === "interpretation" ? "正在解析" : generationChoice === "together" ? "正在生成" : "生成这张梦卡"}
            </button>
            {generationNotice && <p className="generation-notice" role="status">{generationNotice}</p>}
          </section>
        )}

        {phase === "interpretation" && interpretation && (
          <section className={`interpretation-section${enteringStudio ? " is-leaving-for-studio" : ""}`} aria-busy={enteringStudio}>
            <h1 className="result-title">{interpretation.interpretation.title}</h1>
            <div className="interpretation-content-layout">
              <aside className="interpretation-action-rail" aria-label="文字解读操作">
                <div className="interpretation-complete-state">
                  <i aria-hidden="true" />
                  <div>
                    <span>{dreamCardProgress.label}</span>
                    <strong>{dreamCardProgress.title}</strong>
                    <p>{dreamCardProgress.detail}</p>
                  </div>
                </div>
                <button className="primary-button" type="button" onClick={continueToDreamCard}>{showDreamCardPreview ? dreamImage?.status === "completed" ? "查看梦卡" : "查看进度" : "制作梦卡"}</button>
                <div className="interpretation-tool-buttons">
                  <button type="button" onClick={copyInterpretation}>复制文字解读</button>
                  <button type="button" onClick={returnToPreviousPage}>返回修改梦象</button>
                  <button type="button" onClick={startAnotherDream}>记录另一个梦</button>
                </div>
              </aside>
              <div className="interpretation-reading-column">
                <KanshanPageGuide scene="reading" />
                {interpretation.generation_mode === "personalized" ? (() => {
                  const draft = interpretation.interpretation as PersonalizedInterpretation;
                  return <article className="interpretation-card">
                    <section><span>梦境片段</span><p>{draft.dream_summary}</p></section>
                    <section className="interpretation-analysis">
                      <span>逐层解读</span>
                      <div>{draft.reflections.map((reflection, index) => (
                        <article key={reflection}>
                          <b>{String(index + 1).padStart(2, "0")}</b>
                          <p>{reflection}</p>
                        </article>
                      ))}</div>
                    </section>
                    <section><span>现实校准</span><p>{calibratedQuestion(draft.reflection_question)}</p></section>
                    <section><span>温和行动</span><p>{draft.gentle_action}</p></section>
                  </article>;
                })() : (() => {
                  const draft = interpretation.interpretation as SourceBackedInterpretation;
                  return <article className="interpretation-card">
                    {draft.readings.map((reading) => <section key={reading.source_id}><span>梦境回望</span><p>{reading.reading}</p></section>)}
                    <section><span>值得留意</span><p>{calibratedQuestion(draft.reflection_question)}</p></section>
                  </article>;
                })()}
              </div>
            </div>
          </section>
        )}

        {phase === "dreamcard" && (() => {
          const draft = interpretation?.interpretation ?? { title: "正在整理梦境", reflections: [], card_summary: "", reflection_question: "" };
          const coreReading = interpretation ? cardCoreReading(interpretation.interpretation) : "";
          const imageIsGenerating = isImageWaiting || (dreamImage?.status === "completed" && !imageDisplayFailed && (imageReveal !== "idle" || loadedImageSource !== imageSource));
          const canDownloadImage = Boolean(imageSource && dreamImage?.status === "completed" && !imageIsGenerating && !imageDisplayFailed);
          const recoveryLabel = dreamImage?.recovery_action === "check_task" ? "查询生成结果" : dreamImage?.recovery_action === "retry_review" ? "重新核验" : "重试生成";
          const canRecover = Boolean(dreamImage?.recovery_action && dreamImage.recovery_action !== "contact_support");
          return <section className="dreamcard-studio-section" aria-label="梦卡制作">
            <section className="dreamcard-area" aria-labelledby="dreamcard-heading">
              <div className="dreamcard-area-heading">
                <span>梦 卡 制 作</span>
                <p>1080 × 1440 PNG</p>
              </div>
              <div className="dreamcard-preview-layout">
                <div className="dreamcard-review-warning" role="status" aria-busy={imageIsGenerating}>
                  <KanshanPageGuide scene="card" disabled={imageIsGenerating} message={imageIsGenerating ? "画面正在准备，稍等一下就好" : dreamImage?.status === "failed" ? "画面暂未完成，解读已经保留" : undefined} />
                  <strong>{imageIsGenerating ? (isImageWaiting ? dreamImage?.image_url ? "正在补生成，原图已保留" : "正在生成梦卡" : "正在载入图片") : dreamImage?.status === "failed" ? "画面生成未完成" : imageDisplayFailed ? imageLoadTimedOut ? "图片加载超时" : "图片暂未加载" : "图片已生成"}</strong>
                  {dreamImage?.failure_reason && !imageIsGenerating && <small>最近一次生成的检查提示</small>}
                  <p>{imageIsGenerating ? "画面完成后，操作按钮会自动恢复" : imageDisplayFailed ? "生成结果仍然保留，请重新载入图片" : !imageSource ? "解梦文章已保留，可以返回查看" : dreamImage?.failure_reason === "contains_panels" ? "画面可能出现分镜或拼接，仍可预览和下载。你可以保留，也可以确认后重绘。" : dreamImage?.failure_reason === "contains_text" ? "画面可能含有文字，仍可预览和下载。" : dreamImage?.failure_reason === "contains_band" ? "画面可能存在空白或色带，请查看实际效果。" : dreamImage?.failure_reason === "subject_mismatch" ? "主体可能与你确认的形态有出入，请查看实际效果。" : ["generation_failed", "generation_timeout", "submission_unknown"].includes(dreamImage?.failure_reason || "") ? "补生成暂未取得可用结果，原图仍然保留。" : dreamImage?.failure_reason ? "质量核验暂未完成，图片已保留供你查看。" : "可以预览、下载这张梦卡。"}</p>
                  {(dreamImage?.variants?.length ?? 0) > 1 && <div className="dreamcard-version-options" aria-label="选择生成版本">{dreamImage?.variants?.map((variant, index) => <button key={variant} className="secondary-button" type="button" disabled={imageIsGenerating} aria-pressed={dreamImage.selected_variant === variant} onClick={() => selectImageVariant(variant)}>{dreamImage.selected_variant === variant ? "使用中 · " : "使用"}第 {index + 1} 张</button>)}</div>}
                  {dreamImage?.image_url && dreamImage.failure_reason && dreamImage.recovery_action === "retry_generation" && (dreamImage.supplementary_attempts ?? 0) < 1 && <button type="button" className="secondary-button" disabled={imageIsGenerating} onClick={() => setShowSupplementConfirm(true)}>重新生成一次</button>}
                  {dreamImage?.recovery_action === "check_task" && <button type="button" className="secondary-button" disabled={imageIsGenerating} onClick={() => session && generateDreamImage(session.id, true)}>查询原任务</button>}
                  <div className="dreamcard-review-footer">
                    <button type="button" className="secondary-button" disabled={imageIsGenerating || restoringArticle} onClick={returnToInterpretation}>{restoringArticle ? "正在读取文章" : "返回解梦文章"}</button>
                    <button type="button" className="secondary-button" disabled={imageIsGenerating} onClick={startAnotherDream}>记录下一个梦境</button>
                  </div>
                  <DreamShare key={`${session?.id}-${session?.revision}-${Boolean(interpretation)}`} title={draft.title} reading={coreReading}
                    disabled={!canDownloadImage || downloading}
                    prepareCard={prepareDreamCard} />
                </div>
                <aside className={`dreamcard-toolbar${toolbarCollapsed ? " is-collapsed" : ""}${toolbarCollapsed && framePanelOpen ? " is-frame-view" : ""}`} aria-label="梦卡工具栏">
                  <button type="button" disabled={imageIsGenerating} className="dreamcard-toolbar-toggle" aria-label={toolbarCollapsed ? "展开所有工具" : "收起所有工具"} aria-expanded={!toolbarCollapsed} aria-controls="dreamcard-toolbar-content" onClick={() => { setToolbarCollapsed((value) => !value); setFramePanelOpen(false); }}>
                    <Settings2 size={16} aria-hidden="true" />
                    <span>{toolbarCollapsed ? "工具" : "梦卡工具"}</span>
                    {toolbarCollapsed ? <PanelLeftOpen size={16} aria-hidden="true" /> : <PanelLeftClose size={16} aria-hidden="true" />}
                  </button>
                  {toolbarCollapsed && !framePanelOpen && <nav className="dreamcard-compact-tools" aria-label="梦卡快捷工具">
                    <button type="button" disabled={imageIsGenerating || !session} onClick={openImageAdjustment} title="画面调整">
                      <Sparkles size={19} aria-hidden="true" /><span>画面调整</span>
                    </button>
                    <button type="button" disabled={imageIsGenerating} onClick={() => setFramePanelOpen(true)} title="进入边框选择">
                      <Frame size={19} aria-hidden="true" /><span>选择边框</span>
                    </button>
                    <button type="button" disabled={!canDownloadImage || downloading} onClick={downloadDreamCard} title="下载梦卡 PNG">
                      <Download size={19} aria-hidden="true" /><span>{downloading ? "正在导出" : "下载梦卡"}</span>
                    </button>
                  </nav>}
                  {toolbarCollapsed && framePanelOpen && <button type="button" disabled={imageIsGenerating} className="dreamcard-frame-back" onClick={() => setFramePanelOpen(false)}><ArrowLeft size={14} aria-hidden="true" />返回工具</button>}
                  <div id="dreamcard-toolbar-content" hidden={toolbarCollapsed && !framePanelOpen}>
                <details className="dreamcard-adjustment-panel" open>
                  <summary aria-disabled={imageIsGenerating} onClick={event => { if (imageIsGenerating) event.preventDefault(); }}><Sparkles size={15} aria-hidden="true" /><span>画面调整</span><ChevronDown size={14} aria-hidden="true" /></summary>
                  <button
                    type="button"
                    disabled={imageIsGenerating || !session}
                    onClick={openImageAdjustment}
                  >
                    日期与文字设置
                  </button>
                  <small>调整日期与小看山标识</small>
                </details>
                <div className="dreamcard-side-controls">
                  <details key={toolbarCollapsed && framePanelOpen ? "frame-view" : "all-tools"} className="dreamcard-frame-picker" open>
                    <summary aria-disabled={imageIsGenerating} onClick={(event) => { if (imageIsGenerating) event.preventDefault(); }}><Frame size={15} aria-hidden="true" /><span>选择边框</span><ChevronDown size={14} aria-hidden="true" /></summary>
                    <div className="dreamcard-frame-options">
                      {DREAM_CARD_FRAMES.map((frame) => <button key={frame.id} className={dreamCardFrame === frame.id ? "is-active" : ""} type="button" disabled={imageIsGenerating} aria-pressed={dreamCardFrame === frame.id} onClick={() => selectDreamCardFrame(frame.id)}>
                        <i className={`frame-swatch frame-swatch-${frame.id}`} aria-hidden="true" />
                        <span><strong>{frame.name}</strong><small>{frame.description}</small></span>
                      </button>)}
                    </div>
                  </details>
                  <div className="dreamcard-actions">
                    {imageIsGenerating ? <p role="status">{dreamImage?.supplementary_attempts ? "正在补生成画面，请稍候" : "正在处理画面，请稍候"}</p> : !dreamImage ? <button className="primary-button" onClick={() => session && generateDreamImage(session.id)}>生成梦境图像</button> : dreamImage.status === "completed" ? <button className="primary-button" onClick={downloadDreamCard} disabled={!canDownloadImage || downloading}>{downloading ? "正在导出" : "下载梦卡 PNG"}</button> : canRecover ? <button className="secondary-button" onClick={() => session && generateDreamImage(session.id, true)}>{recoveryLabel}</button> : <p>解梦文章已保留</p>}
                  </div>
                </div>
                  </div>
                </aside>
                <article ref={dreamCardRef} className={`dreamcard-export dreamcard-frame-${dreamCardFrame}${dreamImage?.status === "failed" || imageDisplayFailed ? " is-failed" : ""}`} aria-label="可下载的梦卡">
                  <div className={`dreamcard-artwork ${imageSource ? "is-ready" : ""}`}>
                    {imageSource ? <img key={imageSource} src={imageSource} alt="根据当前梦境生成的图像" crossOrigin="use-credentials" onLoad={() => { setLoadedImageSource(imageSource); setImageDisplayFailed(false); setImageLoadTimedOut(false); if (imageReveal === "waiting") setImageReveal("revealing"); }} onError={() => { setImageReveal("idle"); setImageDisplayFailed(true); }} /> : <div className="dreamcard-placeholder" aria-hidden="true" />}
                  </div>
                    {imageDisplayFailed && dreamImage?.status === "completed" && <div className="dreamcard-image-failure" role="status">
                      <span>{imageLoadTimedOut ? "图片已生成，但加载超时" : "图片已生成，当前加载暂时中断"}</span>
                      <small>生成结果已保留，重新载入不消耗生成额度</small>
                      <button type="button" className="secondary-button" onClick={() => { setImageDisplayFailed(false); setImageLoadTimedOut(false); setImageVersion(value => Math.max(Date.now(), value + 1)); }}>重新载入图片</button>
                    </div>}
                    {dreamImage?.status === "failed" && <div className="dreamcard-image-failure" role="status">
                      <span>{dreamImage.failure_reason === "submission_unknown" ? "暂时无法确认图片是否生成" : dreamImage.failure_reason === "generation_timeout" ? "生成时间比预期更长" : dreamImage.failure_reason === "contains_text" ? "画面中检测到文字" : dreamImage.failure_reason === "contains_band" ? "画面完整性未通过检查" : "画面生成未完成"}</span>
                      <small>{dreamImage.failure_reason === "submission_unknown" ? "请联系维护人员核对本次任务，避免重复生成。解梦文章已保留。" : dreamImage.failure_reason === "generation_timeout" ? "可以查询原任务的结果，解梦文章已保留。" : (dreamImage.supplementary_attempts ?? 0) >= 1 ? "本次补生成仍未完成，请联系维护人员处理。解梦文章已保留。" : "解梦文章已保留，可以重试生成一次。"}</small>
                      {canRecover && <button type="button" className="secondary-button" onClick={() => session && generateDreamImage(session.id, true)}>{recoveryLabel}</button>}
                      <button type="button" className="secondary-button" disabled={restoringArticle} onClick={returnToInterpretation}>{restoringArticle ? "正在读取文章" : "返回解梦文章"}</button>
                      {dreamImage.recovery_action === "contact_support" && <small>记录编号：{dreamImage.session_id}</small>}
                    </div>}
                  <div className="dreamcard-mist" aria-hidden="true" />
                  {imageIsGenerating && (!imageSource || imageReveal !== "idle") && <DreamCardGenerationWaiting stage={IMAGE_GENERATION_STAGES[imageLoadingStage]} revealing={imageReveal === "revealing"} onRevealed={() => setImageReveal("idle")} />}
                  <header className="dreamcard-topline">
                    <div className="dreamcard-brand">
                      <DreamCardLogo tone="card" aria-hidden="true" />
                      <span>LUCIDREAM</span>
                    </div>
                    {(!session || cardSettings[session.id]?.showDate !== false) && <time>{(session && cardSettings[session.id]?.date) || recordDate(session?.created_at)}</time>}
                  </header>
                  <div className="dreamcard-copy" hidden={!interpretation}>
                    <h2 id="dreamcard-heading" className={cardTitleClass(draft.title)}>{draft.title}</h2>
                    <section className="dreamcard-reading">
                      <span>核心解梦</span>
                      <p>{coreReading}</p>
                    </section>
                    <section className="dreamcard-question">
                      <span>留给你的问题</span>
                      <p>{calibratedQuestion(draft.reflection_question)}</p>
                    </section>
                  </div>
                  {(!session || cardSettings[session.id]?.showLabel !== false) && <div className="dreamcard-label"><img src={`${import.meta.env.BASE_URL}assets/kanshan/idle-static.png`} alt="刘看山" width={44} height={44} /></div>}
                  <footer className="dreamcard-footer">梦境回光 · 仅供自我观察 · 由 AI 为此梦绘成</footer>
                </article>
              </div>
            </section>
          </section>;
        })()}

        {phase === "safety" && session && (
          <section className="safety-section">
            <p className="eyebrow">先 照 顾 此 刻 的 自 己</p>
            <h1 className="result-title">普通解梦流程<br /><span>已暂时停下。</span></h1>
            <p className="safety-message">{session.safety_message}</p>
            <KanshanPageGuide scene="safety" />
            <p className="safety-detail">如果你正处于立即危险中，请联系当地紧急服务。梦卡不能替代专业支持。</p>
            <button className="secondary-button standalone" onClick={startOver}>清除本次内容</button>
          </section>
        )}
      </main> : <ProductModuleView module={activeModule}
        onOpenDream={(id, revision, view) => {
          if (dreamText.trim() && !session && !window.confirm("打开历史记录会替换当前未提交的草稿，是否继续？")) return;
          localStorage.setItem(SESSION_KEY, id);
          saveResultView(localStorage, id, revision, view);
          window.location.reload();
        }}
        onNewDream={() => {
          if (dreamText.trim() && !session && !window.confirm("开始新记录会清空当前未提交的草稿，是否继续？")) return;
          // Leave every saved backend record intact when starting another dream.
          localStorage.removeItem(SESSION_KEY);
          localStorage.removeItem(DRAFT_KEY);
          clearResultView(localStorage);
          window.location.reload();
        }} />}

      <footer id="archive" className="site-footer"><span>梦卡 DREAM CARD</span><p>用于文化解释与自我观察，不预测现实，也不替代医学或心理专业建议。</p></footer>
      {showSignOutConfirm && createPortal(
        <div className="signout-dialog-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) setShowSignOutConfirm(false); }}>
          <section className="signout-dialog" role="dialog" aria-modal="true" aria-labelledby="signout-dialog-title" aria-describedby="signout-dialog-description">
            <p className="eyebrow align-left">登 录 状 态</p>
            <h2 id="signout-dialog-title">确定退出登录？</h2>
            <p id="signout-dialog-description">退出后，本次梦境内容仍会保留；再次进入完整功能时需要重新登录。</p>
            <div className="signout-dialog-actions">
              <button type="button" className="signout-cancel" autoFocus onClick={() => setShowSignOutConfirm(false)}>取消</button>
              <button type="button" className="signout-confirm" onClick={signOut}>确定退出</button>
            </div>
          </section>
        </div>, document.body
      )}
      {showSupplementConfirm && createPortal(<div className="signout-dialog-backdrop">
        <section className="signout-dialog" role="alertdialog" aria-modal="true" aria-labelledby="supplement-title" onKeyDown={(event) => {
          if (event.key === "Escape") setShowSupplementConfirm(false);
          if (event.key === "Tab") {
            const buttons = event.currentTarget.querySelectorAll<HTMLButtonElement>("button");
            if (event.shiftKey && document.activeElement === buttons[0]) { event.preventDefault(); buttons[1]?.focus(); }
            if (!event.shiftKey && document.activeElement === buttons[1]) { event.preventDefault(); buttons[0]?.focus(); }
          }
        }}>
          <h2 id="supplement-title">再生成一张背景？</h2>
          <p>原图会保留，完成后可以选择使用哪张。本次可补生成一次，不额外扣除额度；日期、文字和边框不会改变。</p>
          <div className="signout-dialog-actions">
            <button type="button" className="secondary-button" autoFocus onClick={() => setShowSupplementConfirm(false)}>保留当前图片</button>
            <button type="button" className="primary-button" onClick={() => { setShowSupplementConfirm(false); if (session) void generateDreamImage(session.id, true, true); }}>确认补生成</button>
          </div>
        </section>
      </div>, document.body)}
      {showGenerationOptions && createPortal(
        <div className="generation-dialog-backdrop generation-choice-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) setShowGenerationOptions(false); }}>
          <section className="generation-dialog" role="dialog" aria-modal="true" aria-labelledby="generation-dialog-title" aria-describedby="generation-dialog-description">
            <button className="generation-dialog-close" type="button" onClick={() => setShowGenerationOptions(false)} aria-label="关闭梦境解析选择"><X size={17} /></button>
            <p className="eyebrow align-left">梦 境 解 读</p>
            <h2 id="generation-dialog-title">现在开始解析梦境吗？</h2>
            <p id="generation-dialog-description">梦境已经保存，你可以现在查看解读，也可以稍后再开启。</p>
            <div className="generation-choices" role="group" aria-label="选择是否开始解析梦境">
              <button className="generation-choice" type="button" onClick={() => chooseDreamCardGeneration(false)} autoFocus>
                <span>01</span>
                <strong>开始解析梦境</strong>
                <small>生成文字解读，完成后再决定是否制作梦卡</small>
              </button>
              <button className="generation-choice" type="button" onClick={deferDreamCardGeneration}>
                <span>02</span>
                <strong>暂不开启</strong>
                <small>保留本次确认结果，之后可以随时继续</small>
              </button>
            </div>
          </section>
        </div>, document.body
      )}
      {showImageRegenerateConfirm && (
        <div className="generation-dialog-backdrop adjustment-scroll-backdrop" style={{ paddingTop: adjustmentTop }} onMouseDown={(event) => { if (event.target === event.currentTarget) setShowImageRegenerateConfirm(false); }}>
          <section className="regenerate-dialog" role="dialog" aria-modal="true" aria-labelledby="regenerate-dialog-title" aria-describedby="regenerate-dialog-description">
            <button className="generation-dialog-close" type="button" onClick={() => setShowImageRegenerateConfirm(false)} aria-label="关闭画面调整"><X size={17} /></button>
            <p className="eyebrow align-left">画 面 调 整</p>
            <h2 id="regenerate-dialog-title">调整梦卡上的日期与标识</h2>
            <p id="regenerate-dialog-description">设置即时应用于预览与下载，不改变背景图片。</p>
            {session && <div className="dreamcard-text-settings">
              <label>显示梦境日期<input type="checkbox" role="switch" checked={cardSettings[session.id]?.showDate !== false} onChange={(event) => updateCardSettings(session.id, cardSettings[session.id]?.date || recordDate(session.created_at), cardSettings[session.id]?.showLabel !== false, event.target.checked)} /></label>
              {cardSettings[session.id]?.showDate !== false && <div className="dreamcard-date-setting"><span>梦境日期</span><DreamDatePicker value={cardSettings[session.id]?.date || recordDate(session.created_at)} onChange={(value) => updateCardSettings(session.id, value, cardSettings[session.id]?.showLabel !== false)} /></div>}
              <label>显示左下角小看山<input type="checkbox" role="switch" checked={cardSettings[session.id]?.showLabel !== false} onChange={(event) => updateCardSettings(session.id, cardSettings[session.id]?.date || recordDate(session.created_at), event.target.checked)} /></label>
            </div>}
            <div className="regenerate-dialog-actions">
              <button type="button" className="regenerate-confirm" onClick={() => setShowImageRegenerateConfirm(false)} autoFocus>完成</button>
            </div>
          </section>
        </div>
      )}
      {showSubjectConfirm && createPortal(<div className="signout-dialog-backdrop">
        <section className="signout-dialog" role="alertdialog" aria-modal="true" aria-labelledby="subject-confirm-title" aria-describedby="subject-confirm-description" onKeyDown={(event) => {
          if (event.key === "Escape" && !loading) { setShowSubjectConfirm(false); window.requestAnimationFrame(() => appearanceRef.current?.focus()); }
          if (event.key === "Tab") {
            const buttons = Array.from(event.currentTarget.querySelectorAll<HTMLButtonElement>("button:not(:disabled)"));
            if (!buttons.length) { event.preventDefault(); return; }
            const first = buttons[0], last = buttons[buttons.length - 1];
            if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
            else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
          }
        }}>
          <p className="eyebrow align-left">主 角 形 象 确 认</p>
          <h2 id="subject-confirm-title">梦中的你，是这个形象吗？</h2>
          <div className="subject-confirm-value">{appearanceLabel}</div>
          <p id="subject-confirm-description">{characterAppearance === "unspecified" || characterAppearance === "none" ? "梦卡不会额外添加代表你的人物形象。请确认是否符合你的梦境。" : "梦卡将以这个形象呈现梦中的你，其他人物与生物保持各自的形象。请确认是否符合你的梦境。"}</p>
          <div className="signout-dialog-actions">
            <button type="button" className="secondary-button" autoFocus disabled={loading} onClick={() => { setShowSubjectConfirm(false); setEditingAppearance(true); window.requestAnimationFrame(() => { appearanceRef.current?.scrollIntoView({ behavior: "smooth", block: "center" }); appearanceRef.current?.focus({ preventScroll: true }); }); }}>返回修改</button>
            <button type="button" className="primary-button" disabled={loading} onClick={() => void confirmSymbols(true)}>{loading ? "正在保存…" : "形象正确，继续"}</button>
          </div>
        </section>
      </div>, document.body)}
      {showAppearanceReminder && <div className="generation-dialog-backdrop">
        <section className="regenerate-dialog" role="alertdialog" aria-modal="true" aria-labelledby="appearance-reminder-title">
          <h2 id="appearance-reminder-title">{characterAppearance === "other" ? "请描述梦中的自己" : "请先选择梦中自己的形态"}</h2>
          <p>{characterAppearance === "other" ? "例如：我变成了一只螃蟹。请填写自己的形态，不是遇见的其他角色。" : "请选择一个选项；没看见自己的样子或记不清时，可以选择“没有明确形象”。"}</p>
          <div className="regenerate-dialog-actions"><button type="button" className="regenerate-confirm" autoFocus onClick={() => { setShowAppearanceReminder(false); appearanceRef.current?.scrollIntoView({ behavior: "smooth", block: "center" }); appearanceRef.current?.focus({ preventScroll: true }); }}>去选择</button></div>
        </section>
      </div>}
      {error && <div role="alert" className="toast"><span>{error}</span><button onClick={() => setError("")} aria-label="关闭提示">关闭</button></div>}
    </div>
  );
}
