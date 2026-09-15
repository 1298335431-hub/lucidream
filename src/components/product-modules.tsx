import { useEffect, useState } from "react";
import { Check, Search, ShieldCheck } from "lucide-react";
import KanshanPageGuide, { type GuideScene } from "./kanshan-page-guide";
import { TEMPORARY_DEMO } from "../demo-mode";

export type ProductModule = "record" | "archive" | "account" | "settings";

type DreamEntry = {
  id: string; revision: number; title: string; dream_text: string; created_at: string;
  tags: string[]; status: string; interpretation_status: string | null;
  image_status: string | null; has_image: boolean;
};
type OpenDream = (id: string, revision: number, view: "record" | "interpretation" | "dreamcard") => void;

function ModuleIntro({ eyebrow, title, muted, copy, guide, guideMessage }: { eyebrow: string; title: string; muted: string; copy: string; guide?: GuideScene; guideMessage?: string }) {
  return (
    <header className="module-intro">
      <p className="eyebrow align-left">{eyebrow}</p>
      <h1>{title}<br /><span>{muted}</span></h1>
      <p className="module-intro-copy">{copy}</p>
      {guide && <KanshanPageGuide scene={guide} message={guideMessage} />}
    </header>
  );
}

function ArchiveModule({ onRecord, onOpenDream }: { onRecord: () => void; onOpenDream: OpenDream }) {
  const [query, setQuery] = useState("");
  const [search, setSearch] = useState("");
  const [dreams, setDreams] = useState<DreamEntry[]>([]);
  const [total, setTotal] = useState<number | null>(null);
  const [offset, setOffset] = useState(0);
  const [nextOffset, setNextOffset] = useState<number | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [loading, setLoading] = useState(true);
  const [notice, setNotice] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setNotice("");
    const timer = window.setTimeout(() => controller.abort(), 20000);
    let active = true;
    fetch(`${import.meta.env.VITE_API_BASE_URL ?? "/api/v1"}/dreams?offset=${offset}&q=${encodeURIComponent(search)}`, { credentials: "include", signal: controller.signal })
      .then(async (response) => {
        if (response.status === 401) window.dispatchEvent(new Event("dreamcard-auth-expired"));
        if (!response.ok) throw new Error("暂时无法读取梦境册，请重新连接");
        return response.json() as Promise<{ dreams: DreamEntry[]; total: number; next_offset: number | null }>;
      }).then((data) => {
        if (!active) return;
        setDreams((current) => offset === 0 ? data.dreams : [...current, ...data.dreams.filter((entry) => !current.some((item) => item.id === entry.id))]);
        setTotal(data.total);
        setNextOffset(data.next_offset);
      }).catch(() => { if (active) setNotice("暂时无法读取梦境册，请检查网络后重试。"); })
      .finally(() => { window.clearTimeout(timer); if (active) setLoading(false); });
    return () => { active = false; controller.abort(); window.clearTimeout(timer); };
  }, [search, offset, attempt]);
  const runSearch = (value: string) => {
    setQuery(value); setSearch(value.trim()); setOffset(0); setDreams([]); setTotal(null); setNextOffset(null); setAttempt((n) => n + 1);
  };
  return (
    <main className="module-main">
      <div className="module-layout">
        <ModuleIntro guide="archive" eyebrow="梦 境 册" title="把梦留下" muted="也看见变化" copy={TEMPORARY_DEMO ? "这里仅临时保留当前账户的演示记录，服务重启后可能清空，请及时下载喜欢的梦卡" : "这里保存着当前邀请码账户的梦境。回看已有解读、打开梦卡继续下载，都不会再次消耗生图额度。"} />
        <section className="module-workspace" aria-busy={loading}>
          <div className="workspace-heading archive-heading">
            <div><span>{search ? "搜索结果" : "已保存"}</span><strong>{total === null ? "—" : total}</strong></div>
            <form className="archive-search" onSubmit={(event) => { event.preventDefault(); runSearch(query); }}>
              <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索梦境或线索" aria-label="搜索梦境" />
              <button type="submit" aria-label="搜索"><Search size={17} /></button>
            </form>
          </div>
          {search && <button className="text-action" onClick={() => runSearch("")}>清除搜索</button>}
          <div className="archive-list">
            {dreams.map((dream, index) => (
              <article className="archive-entry" key={dream.id}>
                <span className="archive-index">{String(index + 1).padStart(2, "0")}</span>
                <div className="archive-content">
                  <time dateTime={dream.created_at}>{new Date(dream.created_at).toLocaleDateString("zh-CN")}</time>
                  <strong>{dream.title}</strong>
                  <p className="archive-excerpt">{dream.dream_text}</p>
                  <small>{dream.tags.join(" · ")}</small>
                  <div className="archive-entry-actions">
                    <button className="secondary-button" onClick={() => onOpenDream(dream.id, dream.revision, dream.interpretation_status === "completed" ? "interpretation" : "record")}>{dream.interpretation_status === "completed" ? "查看解读" : "继续查看记录"}</button>
                    {(dream.has_image || dream.image_status === "processing") && <button className="secondary-button" onClick={() => onOpenDream(dream.id, dream.revision, "dreamcard")}>{dream.has_image ? "查看梦卡 / 下载" : "查看生成进度"}</button>}
                  </div>
                </div>
                <span className="archive-state">{dream.image_status === "processing" ? "画面生成中" : dream.has_image ? "梦卡已生成" : dream.interpretation_status === "completed" ? "解读已完成" : dream.interpretation_status === "processing" ? "解读处理中" : dream.status === "ready_to_generate" ? "梦象已确认" : "已保存记录"}</span>
              </article>
            ))}
            {notice && <div className="module-empty" role="status"><p>{notice}</p><button className="secondary-button" onClick={() => setAttempt((n) => n + 1)}>重新连接</button></div>}
            {loading && <p role="status">正在读取记录…</p>}
            {!loading && !notice && dreams.length === 0 && <div className="module-empty"><p>{search ? "没有找到相关梦境" : "还没有保存的梦境"}</p></div>}
          </div>
          {!loading && !notice && nextOffset !== null && <button className="secondary-button" onClick={() => setOffset(nextOffset)}>加载更多记录</button>}
          <button className="primary-button module-cta" onClick={onRecord}>记录新的梦境</button>
        </section>
      </div>
    </main>
  );
}

function AccountModule() {
  const [quota, setQuota] = useState<{total: number; used: number; remaining: number} | null>(null);
  const [notice, setNotice] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    fetch(`${import.meta.env.VITE_API_BASE_URL ?? "/api/v1"}/account/quota`, { credentials: "include", signal: controller.signal })
      .then(async (response) => {
        if (response.status === 401) window.dispatchEvent(new Event("dreamcard-auth-expired"));
        if (!response.ok) throw new Error("暂时无法读取额度，请稍后重新打开此页面");
        return response.json();
      }).then(setQuota).catch((error) => { if (!controller.signal.aborted) setNotice(error.message); });
    return () => controller.abort();
  }, []);
  return (
    <main className="module-main">
      <div className="module-layout">
        <ModuleIntro guide="account" guideMessage={quota?.remaining === 0 ? "额度不足" : undefined} eyebrow="账 户 与 额 度" title="清楚知道" muted="每一次生成" copy={TEMPORARY_DEMO ? "演示账户有 8 次生图额度，支持连续体验，服务重启后账户与额度记录可能清空" : "新用户体验额度为 8 次，用于生成梦卡画面，与账户绑定，不会因刷新或退出登录而重置"} />
        <section className="module-workspace account-workspace">
          <div className="workspace-heading"><div><span>剩余次数</span><strong>{quota ? quota.remaining : "—"}</strong></div><p>{quota ? `当前账户共 ${quota.total} 次生图额度` : "正在读取账户额度"}</p></div>
          {quota && <div className="usage-meter" aria-label={`已使用 ${quota.used} 次，共 ${quota.total} 次`}><span style={{ width: `${quota.total > 0 ? Math.min(100, Math.max(0, quota.used / quota.total * 100)) : 0}%` }} /></div>}
          <div className="account-summary">
            <div><span>当前身份</span><strong>体验账户</strong></div>
            <div><span>当前方案</span><strong>免费体验</strong></div>
            <div><span>已使用</span><strong>{quota ? `${quota.used} 次` : "读取中"}</strong></div>
          </div>
          <div className="plans-heading"><span>使用说明</span><p>累计额度，不按月重置</p></div>
          <dl className="quota-guide" aria-label="生图额度使用说明">
            <div><dt>如何计次</dt><dd>每次发起新的生图任务占用 1 次额度。失败任务仍保留这次占用，同一任务的故障重试不重复扣除。</dd></div>
            <div><dt>图片不满意</dt><dd>图片存在质量提示时，可由你确认后补生成一次，原图会保留，不额外扣额度。补生成与故障重试共用一次机会，不会自动重绘。</dd></div>
            <div><dt>哪些不扣次数</dt><dd>记录梦境、文字解读、查看和下载已有梦卡均不消耗生图额度。</dd></div>
            <div><dt>额度与保留</dt><dd>{TEMPORARY_DEMO ? "删除记录不返还次数，额度用完仍可下载尚未清空的梦卡；本版本不提供长期保存与恢复" : "不设置生图频率限制，额度不按月重置。删除记录不返还次数，额度用完后已有梦卡仍可查看与下载。"}</dd></div>
          </dl>
          {notice && <div className="inline-notice" role="status"><Check size={15} />{notice}</div>}
        </section>
      </div>
    </main>
  );
}

function SettingsModule() {
  return (
    <main className="module-main">
      <div className="module-layout">
        <ModuleIntro guide="privacy" eyebrow="设 置 与 隐 私" title="你的梦境" muted="如何被保存" copy="以下说明当前邀请码体验版的实际数据处理方式。尚未开放的管理功能不提供无效开关。" />
        <section className="module-workspace settings-workspace">
          <div className="workspace-heading"><div><ShieldCheck size={19} /><strong>隐私与数据</strong></div><p>当前保存方式</p></div>
          <dl className="quota-guide">
            <div><dt>账户记录</dt><dd>{TEMPORARY_DEMO ? "梦境、解读和图片仅临时保留在演示服务中，并按账户隔离；不接云存储、不做备份，服务重启后可能清空" : "已提交并保存的梦境、文字解读与生成结果保存在服务端，与当前邀请码账户关联。退出登录不会删除这些记录，再次使用同一邀请码可在梦境册查看。"}</dd></div>
            <div><dt>浏览器保存</dt><dd>未提交的输入草稿、当前记录入口，以及日期、标识和边框等显示设置会保存在当前浏览器。退出登录会清除草稿和当前记录入口；清除浏览器数据不会删除服务端记录。</dd></div>
            <div><dt>模型处理</dt><dd>梦境内容与确认信息会发送给所接入的 AI 服务，用于整理梦象、文字解读和生成画面。近期现实经历用于文字解读，不作为生图素材。</dd></div>
            <div><dt>保留与管理</dt><dd>{TEMPORARY_DEMO ? "不保证记录保留时长，也不提供故障恢复，请勿输入敏感信息；生成后请立即下载需要保留的作品" : "当前没有按 30 天或一年自动删除的机制。批量删除、账户数据导出和保留期限设置尚未开放；你仍可在梦卡页面下载已有作品。"}</dd></div>
            <div><dt>邀请码保护</dt><dd>邀请码是进入账户的凭据，请勿公开或与他人共用。持有同一邀请码的人可以访问这个账户的记录。</dd></div>
          </dl>
          <p className="privacy-note">梦境解读仅用于文化解释与自我观察，不作为医学诊断、现实预测或确定性结论。</p>
        </section>
      </div>
    </main>
  );
}

export function ProductModuleView({ module, onOpenDream, onNewDream }: { module: Exclude<ProductModule, "record">; onOpenDream: OpenDream; onNewDream: () => void }) {
  if (module === "archive") return <ArchiveModule onRecord={onNewDream} onOpenDream={onOpenDream} />;
  if (module === "account") return <AccountModule />;
  return <SettingsModule />;
}
