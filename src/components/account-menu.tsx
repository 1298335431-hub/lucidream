import { useEffect, useId, useRef, useState } from "react";
import { ChevronDown, CircleUserRound, LogOut, ShieldCheck } from "lucide-react";
import "./account-menu.css";

export type AccountProfile = { nickname: string; avatarUrl?: string; provider: "invite" | "zhihu" };

// Only pass profile information verified by the backend; never infer a Zhihu
// identity from a URL parameter or a locally stored login flag.
export default function AccountMenu({ profile, onAccount, onPrivacy, onSignOut }: {
  profile?: AccountProfile;
  onAccount: () => void;
  onPrivacy: () => void;
  onSignOut: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [failedAvatar, setFailedAvatar] = useState<string | null>(null);
  const root = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const menu = useRef<HTMLDivElement>(null);
  const id = useId();
  const nickname = profile?.nickname.trim() || (profile?.provider === "zhihu" ? "知乎用户" : "体验用户");
  const avatarUrl = profile?.avatarUrl?.startsWith("https://") ? profile.avatarUrl : undefined;

  useEffect(() => {
    if (!open) return;
    const outside = (event: PointerEvent) => {
      if (event.target instanceof Node && !root.current?.contains(event.target)) setOpen(false);
    };
    document.addEventListener("pointerdown", outside);
    return () => document.removeEventListener("pointerdown", outside);
  }, [open]);

  useEffect(() => {
    if (open) menu.current?.querySelector<HTMLButtonElement>("[role=menuitem]")?.focus();
  }, [open]);

  const avatar = <span className="profile-avatar" aria-hidden="true">
    {avatarUrl && failedAvatar !== avatarUrl
      ? <img src={avatarUrl} alt="" referrerPolicy="no-referrer" onError={() => setFailedAvatar(avatarUrl)} />
      : <CircleUserRound size={22} strokeWidth={1.4} />}
  </span>;
  const choose = (action: () => void) => {
    setOpen(false);
    trigger.current?.focus();
    action();
  };

  return <div className="profile-menu" ref={root} onBlur={event => {
    if (!event.currentTarget.contains(event.relatedTarget)) setOpen(false);
  }} onKeyDown={event => {
    if (event.key === "Escape" && open) {
      event.preventDefault();
      setOpen(false);
      trigger.current?.focus();
    }
  }}>
    <button ref={trigger} type="button" className="profile-trigger" aria-label={`${nickname}，账号菜单`}
      aria-haspopup="menu" aria-expanded={open} aria-controls={open ? id : undefined}
      onClick={() => setOpen(value => !value)} onKeyDown={event => {
        if (event.key === "ArrowDown" || event.key === "ArrowUp") { event.preventDefault(); setOpen(true); }
      }}>
      {avatar}<span className="profile-trigger-name" title={nickname}>{nickname}</span>
      <ChevronDown className="profile-chevron" size={14} aria-hidden="true" />
    </button>
    {open && <div className="profile-popover">
      <div className="profile-summary">
        {avatar}
        <div><strong title={nickname}>{nickname}</strong><p>{profile?.provider === "zhihu" ? "通过知乎登录" : "邀请码体验账户"}</p></div>
      </div>
      <div id={id} ref={menu} role="menu" aria-label="账号操作" onKeyDown={event => {
        if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) return;
        event.preventDefault();
        const items = Array.from(event.currentTarget.querySelectorAll<HTMLButtonElement>("[role=menuitem]"));
        const current = items.indexOf(document.activeElement as HTMLButtonElement);
        const next = event.key === "Home" ? 0 : event.key === "End" ? items.length - 1 : (current + (event.key === "ArrowDown" ? 1 : -1) + items.length) % items.length;
        items[next]?.focus();
      }}>
        <button type="button" role="menuitem" tabIndex={-1} onClick={() => choose(onAccount)}><CircleUserRound size={17} aria-hidden="true" />账户与额度</button>
        <button type="button" role="menuitem" tabIndex={-1} onClick={() => choose(onPrivacy)}><ShieldCheck size={17} aria-hidden="true" />隐私设置</button>
        <div className="profile-menu-divider" />
        <button type="button" role="menuitem" tabIndex={-1} onClick={() => choose(onSignOut)}><LogOut size={17} aria-hidden="true" />退出登录</button>
      </div>
    </div>}
  </div>;
}
