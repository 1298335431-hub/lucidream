import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { ArrowUpRight, Check, Copy, Download, X } from "lucide-react";
import "./dream-share.css";
import KanshanPageGuide from "./kanshan-page-guide";

type CardFile = { dataUrl: string; filename: string };
type Props = { title: string; reading: string; disabled: boolean; prepareCard: () => Promise<CardFile> };

export default function DreamShare({ title, reading, disabled, prepareCard }: Props) {
  const [open, setOpen] = useState(false);
  const [shareTitle, setShareTitle] = useState(title);
  const [story, setStory] = useState("");
  const [includeReading, setIncludeReading] = useState(false);
  const trigger = useRef<HTMLButtonElement>(null);
  const close = () => { setOpen(false); trigger.current?.focus(); };
  return <section className="dream-share-entry" aria-label="分享与共鸣">
    <strong>分享与共鸣</strong>
    <button ref={trigger} type="button" className="secondary-button" disabled={disabled} aria-label="准备分享到知乎" aria-haspopup="dialog" onClick={() => setOpen(true)}>
      <span className="dream-share-brand-label">准备分享到<img className="dream-share-zhihu-mark" src={`${import.meta.env.BASE_URL}assets/zhihu/wordmark.svg`} alt="" aria-hidden="true" width={36} height={17} /></span><ArrowUpRight size={15} aria-hidden="true" />
    </button>
    <small>先整理内容，由你决定是否分享</small>
    {open && createPortal(<ShareDialog title={shareTitle} setTitle={setShareTitle} story={story} setStory={setStory}
      includeReading={includeReading} setIncludeReading={setIncludeReading} reading={reading} prepareCard={prepareCard} onClose={close} />, document.body)}
  </section>;
}

function ShareDialog({ title, setTitle, story, setStory, reading, includeReading, setIncludeReading, prepareCard, onClose }: {
  title: string; setTitle: (value: string) => void; story: string; setStory: (value: string) => void;
  reading: string; includeReading: boolean; setIncludeReading: (value: boolean) => void;
  prepareCard: () => Promise<CardFile>; onClose: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [card, setCard] = useState<CardFile | null>(null);
  const [cardError, setCardError] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const [notice, setNotice] = useState("");
  const [copying, setCopying] = useState(false);
  const prepareRef = useRef(prepareCard);
  const text = [title.trim(), story.trim(), includeReading ? `梦境解读\n${reading}\n\nAI 解读仅供自我探索` : ""].filter(Boolean).join("\n\n");

  useEffect(() => {
    const node = dialog.current!;
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    node.showModal();
    return () => { node.close(); document.body.style.overflow = previous; };
  }, []);
  useEffect(() => {
    let active = true;
    setCardError(false);
    void prepareRef.current().then(result => { if (active) setCard(result); }).catch(() => { if (active) setCardError(true); });
    return () => { active = false; };
  }, [attempt]);

  return <dialog ref={dialog} className="dream-share-dialog" aria-labelledby="dream-share-title" aria-describedby="dream-share-description"
    onCancel={event => { event.preventDefault(); onClose(); }}
    onClick={event => { if (event.target === event.currentTarget) { const r = event.currentTarget.getBoundingClientRect(); if (event.clientX < r.left || event.clientX > r.right || event.clientY < r.top || event.clientY > r.bottom) onClose(); } }}>
    <header className="dream-share-heading">
      <div><span>分 享 与 共 鸣</span><h2 id="dream-share-title">把这场梦，整理成故事</h2><p id="dream-share-description">先预览，再决定分享什么</p></div>
      <button type="button" className="dream-share-close" aria-label="关闭分享预览" onClick={onClose}><X size={20} /></button>
    </header>
    <KanshanPageGuide scene="share" />
    <div className="dream-share-content">
      <section className="dream-share-card" aria-label="待分享的梦卡">
        {card ? <img src={card.dataUrl} alt="当前选中的完整梦卡，包含画面和卡上解读" /> : <div className="dream-share-image-status" role="status">
          <p>{cardError ? "梦卡预览暂时无法载入" : "正在整理梦卡预览…"}</p>
          {cardError && <button type="button" className="secondary-button" onClick={() => setAttempt(value => value + 1)}>重新载入预览</button>}
        </div>}
        <p>使用当前选中的梦卡，保留边框、日期与卡上解读</p>
      </section>
      <section className="dream-share-editor" aria-label="分享文案编辑">
        <label htmlFor="dream-share-heading-input">标题</label>
        <input id="dream-share-heading-input" value={title} maxLength={100} onChange={event => { setTitle(event.target.value); setNotice(""); }} />
        <label htmlFor="dream-share-story">想分享的梦境故事</label>
        <textarea id="dream-share-story" value={story} maxLength={2000} rows={5} placeholder="写下一段愿意公开的片段，也可以聊聊醒来后的感受" onChange={event => { setStory(event.target.value); setNotice(""); }} />
        <p className="dream-share-private-note">未自动填入梦境原文，请避开姓名、联系方式等私密信息</p>
        <label className="dream-share-reading-toggle"><input type="checkbox" checked={includeReading} onChange={event => { setIncludeReading(event.target.checked); setNotice(""); }} /><span>文案中附上这张梦卡的解读</span></label>
        <p className="dream-share-private-note">此选项只影响复制文案，梦卡图片仍包含卡上解读</p>
        <label htmlFor="dream-share-copy-preview">文案预览</label>
        <textarea id="dream-share-copy-preview" className="dream-share-text-preview" readOnly value={text} rows={5} placeholder="填写后，可以在这里查看或选中文案" />
      </section>
    </div>
    <footer className="dream-share-bottom">
      <p>用自己的知乎账号发布<br /><span>在知乎粘贴文案、添加已下载的梦卡<br />请确认发布账号，内容不会自动带入</span></p>
      <div className="dream-share-buttons">
        <button type="button" className="secondary-button" disabled={!card} onClick={() => {
          if (!card) return;
          const link = document.createElement("a"); link.href = card.dataUrl; link.download = card.filename;
          document.body.appendChild(link); link.click(); link.remove(); setNotice("已发起梦卡下载");
        }}><Download size={16} aria-hidden="true" />下载梦卡</button>
        <button type="button" className="primary-button" disabled={!text || copying} onClick={async () => {
          setCopying(true);
          try { await navigator.clipboard.writeText(text); setNotice("文案已复制，尚未发布到知乎"); }
          catch { setNotice("复制未成功，请在文案预览中长按或选中文字复制"); }
          finally { setCopying(false); }
        }}>{notice.startsWith("文案已复制") ? <Check size={16} aria-hidden="true" /> : <Copy size={16} aria-hidden="true" />}{copying ? "正在复制" : "复制文案"}</button>
        <a className="secondary-button" href="https://www.zhihu.com/" target="_blank" rel="noopener noreferrer" aria-label="打开知乎（新窗口）">打开知乎<ArrowUpRight size={16} aria-hidden="true" /></a>
      </div>
      <p className="dream-share-notice" role="status" aria-live="polite">{notice}</p>
    </footer>
  </dialog>;
}
