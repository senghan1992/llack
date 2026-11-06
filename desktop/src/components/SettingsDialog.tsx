/**
 * 앱 설정.
 *
 * 앱 전체가 쓰는 것을 한곳에서 고치는 자리다. 네 갈래로 나뉜다 —
 * 알림 · 외관 · 계정 및 조직 · 파일 및 링크.
 *
 * 계정 것(이름 · 직함 · 아바타 · 역할)은 서버에 있고, 기기 것(알림 · 화면 ·
 * 파일)은 이 창을 쓰는 사람마다 달라서 이 기기에 남는다.
 */

import { useEffect, useMemo, useState } from "react";
import {
  Bell,
  Building2,
  FolderDown,
  LogOut,
  Paperclip,
  SunMoon,
  User,
  X,
} from "lucide-react";
import { api } from "../lib/api";
import { Avatar } from "./Avatar";
import { AVATAR_PALETTE, readableOn } from "../lib/color";
import { formatDate } from "../lib/format";
import { pickFolder, useInDesktop } from "../lib/desktop";
import { setSettings, useSettings } from "../lib/settings";
import { useStore } from "../store/useStore";
import type { Role, Workspace } from "../lib/types";

type Section = "notifications" | "appearance" | "account" | "files";

const SECTIONS: { id: Section; label: string; icon: typeof Bell }[] = [
  { id: "notifications", label: "알림", icon: Bell },
  { id: "appearance", label: "외관", icon: SunMoon },
  { id: "account", label: "계정 및 조직", icon: User },
  { id: "files", label: "파일 및 링크", icon: Paperclip },
];

/* ── controls ────────────────────────────────────────────────────────── */

function Switch({
  checked,
  onChange,
  label,
  disabled,
}: {
  checked: boolean;
  onChange: (next: boolean) => void;
  label: string;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      className="switch"
      disabled={disabled}
      onClick={() => onChange(!checked)}
    />
  );
}

function Segmented<T extends string>({
  value,
  options,
  onChange,
  label,
  disabled,
}: {
  value: T;
  options: { value: T; label: string; disabled?: boolean }[];
  onChange: (next: T) => void;
  label: string;
  disabled?: boolean;
}) {
  return (
    <div className="segmented" role="group" aria-label={label}>
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          className="segmented__item"
          aria-pressed={option.value === value}
          disabled={disabled || option.disabled}
          onClick={() => onChange(option.value)}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}

/** 고르는 것이 있는 한 줄. */
function Row({
  label,
  hint,
  children,
  disabled,
}: {
  label: string;
  hint?: string;
  children?: React.ReactNode;
  disabled?: boolean;
}) {
  return (
    <div className={`setrow${disabled ? " setrow--off" : ""}`}>
      <div className="setrow__text">
        <p className="setrow__label">{label}</p>
        {hint ? <p className="setrow__hint">{hint}</p> : null}
      </div>
      {children ? <div className="setrow__control">{children}</div> : null}
    </div>
  );
}

/** 읽기만 하는 한 줄 — 값이 오른쪽에 놓인다. */
function Fact({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="setrow">
      <div className="setrow__text">
        <p className="setrow__label">{label}</p>
        {hint ? <p className="setrow__hint">{hint}</p> : null}
      </div>
      <div className="setrow__control">
        <span className="setrow__value">{value}</span>
      </div>
    </div>
  );
}

/* ── the modal ──────────────────────────────────────────────────────── */

export function SettingsDialog() {
  // 들어온 자리에 맞는 구역으로 연다 — 프로필 메뉴에서 열면 계정 쪽으로.
  const target = useStore((s) => s.dialogTarget);
  const [section, setSection] = useState<Section>(
    target === "account" || target === "appearance" || target === "files" || target === "notifications"
      ? target
      : "notifications",
  );
  const setDialog = useStore((s) => s.setDialog);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setDialog(null);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [setDialog]);

  return (
    <div
      className="scrim"
      onPointerDown={(event) => event.target === event.currentTarget && setDialog(null)}
    >
      <div className="settings" role="dialog" aria-modal="true" aria-label="설정">
        <header className="settings__head">
          <h2 className="settings__title">설정</h2>
          <button
            type="button"
            className="iconbtn"
            aria-label="닫기"
            onClick={() => setDialog(null)}
          >
            <X size={16} aria-hidden="true" />
          </button>
        </header>
        <div className="settings__body">
          <nav className="settings__nav" aria-label="설정 구역">
            {SECTIONS.map((item) => {
              const Icon = item.icon;
              return (
                <button
                  key={item.id}
                  type="button"
                  className="settings__tab"
                  aria-current={section === item.id ? "true" : undefined}
                  onClick={() => setSection(item.id)}
                >
                  <Icon size={15} aria-hidden="true" />
                  {item.label}
                </button>
              );
            })}
          </nav>
          <div className="settings__content">
            {section === "notifications" ? <Notifications /> : null}
            {section === "appearance" ? <Appearance /> : null}
            {section === "account" ? <Account /> : null}
            {section === "files" ? <Files /> : null}
          </div>
        </div>
      </div>
    </div>
  );
}

/* ── 알림 ───────────────────────────────────────────────────────────── */

function Notifications() {
  const settings = useSettings();
  const desktop = useInDesktop();

  return (
    <>
      <h3 className="settings__heading">알림</h3>
      <p className="settings__lead">이 창이 알림을 어떻게 보여줄지 정합니다.</p>

      <div className="setgroup">
        <Row
          label="데스크톱 알림"
          hint={
            desktop
              ? "도착한 메시지를 OS 의 알림 영역에 띄웁니다."
              : "알림은 데스크톱 앱에서 옵니다 — 브라우저에서는 뜨지 않습니다."
          }
          disabled={!desktop}
        >
          <Switch
            checked={settings.notifications}
            onChange={(next) => setSettings({ notifications: next })}
            label="데스크톱 알림"
            disabled={!desktop}
          />
        </Row>
        <Row
          label="알림 내용"
          hint="미리보기가 없으면 알림에는 보낸 사람의 이름만 남습니다."
          disabled={!desktop || !settings.notifications}
        >
          <Segmented
            value={settings.notificationPreview}
            label="알림 내용"
            disabled={!desktop || !settings.notifications}
            options={[
              { value: "preview", label: "미리보기" },
              { value: "subject", label: "미리보기 없음" },
            ]}
            onChange={(next) => setSettings({ notificationPreview: next })}
          />
        </Row>
      </div>
    </>
  );
}

/* ── 외관 ───────────────────────────────────────────────────────────── */

function Appearance() {
  const settings = useSettings();

  return (
    <>
      <h3 className="settings__heading">외관</h3>
      <p className="settings__lead">
        화면의 밝기와, 시간을 읽는 방식, 화면을 나누는 방식입니다.
      </p>

      <div className="setgroup">
        <Row label="화면 모드" hint="시스템을 고르면 OS 의 화면 설정을 따라갑니다.">
          <Segmented
            value={settings.theme}
            label="화면 모드"
            options={[
              { value: "light", label: "밝게" },
              { value: "dark", label: "어둡게" },
              { value: "system", label: "시스템" },
            ]}
            onChange={(next) => setSettings({ theme: next })}
          />
        </Row>
        <Row label="시간 표기" hint="메시지 옆에 붙는 시간을 표기하는 방식입니다.">
          <Segmented
            value={settings.clock}
            label="시간 표기"
            options={[
              { value: "24h", label: "24시간" },
              { value: "12h", label: "12시간" },
            ]}
            onChange={(next) => setSettings({ clock: next })}
          />
        </Row>
        <Row
          label="나란히 보기"
          hint="창이 넓을 때 일정과 프로젝트를 대화 옆에 붙여 놓습니다."
        >
          <Switch
            checked={settings.splitView}
            onChange={(next) => setSettings({ splitView: next })}
            label="나란히 보기"
          />
        </Row>
      </div>
    </>
  );
}

/* ── 계정 및 조직 ───────────────────────────────────────────────────── */

function Account() {
  const user = useStore((s) => s.user);
  const workspaceName = useStore((s) => s.workspaceName);
  const workspaceId = useStore((s) => s.workspaceId);
  const members = useStore((s) => s.members);
  const updateProfile = useStore((s) => s.updateProfile);
  const loadWorkspace = useStore((s) => s.loadWorkspace);
  const signOut = useStore((s) => s.signOut);
  const toast = useStore((s) => s.toast);
  const setDialog = useStore((s) => s.setDialog);

  const [name, setName] = useState(user?.name ?? "");
  const [title, setTitle] = useState(user?.title ?? "");
  const [color, setColor] = useState(() => readableOn(user?.avatar_color ?? AVATAR_PALETTE[0]));
  const [busy, setBusy] = useState(false);
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);

  useEffect(() => {
    let alive = true;
    void api.workspaces().then((list) => {
      if (alive) setWorkspaces(list);
    });
    return () => {
      alive = false;
    };
  }, []);

  const role = members.find((member) => member.user.id === user?.id)?.role;
  const others = workspaces.filter((workspace) => workspace.id !== workspaceId);

  const save = async () => {
    setBusy(true);
    try {
      await updateProfile({
        name: name.trim() || undefined,
        title: title.trim() || undefined,
        avatar_color: color,
      });
      toast("프로필을 저장했습니다");
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <h3 className="settings__heading">계정 및 조직</h3>
      <p className="settings__lead">팀에서 나를 어떻게 보이는지, 그리고 내가 속한 곳입니다.</p>

      <div className="setgroup">
        <div className="setrow setrow--stack">
          <div className="setrow__text">
            <p className="setrow__label">내 프로필</p>
            <p className="setrow__hint">이름과 직함은 팀의 모든 곳에 그대로 보입니다.</p>
          </div>
          <div className="profile">
            <div className="profile__face">
              <Avatar
                user={{ id: user?.id ?? "me", name: name || "나", avatar_color: color }}
                size="lg"
              />
              <div className="swatches">
                {AVATAR_PALETTE.map((swatch) => (
                  <button
                    key={swatch}
                    type="button"
                    className={`swatch${swatch === color ? " swatch--on" : ""}`}
                    style={{ ["--swatch" as string]: swatch }}
                    onClick={() => setColor(swatch)}
                    aria-label={`아바타 색 ${swatch}`}
                    aria-pressed={swatch === color}
                  />
                ))}
              </div>
            </div>
            <div className="profile__fields">
              <label className="field">
                <span className="field__label">이름</span>
                <input
                  className="field__input"
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                />
              </label>
              <label className="field">
                <span className="field__label">직함</span>
                <input
                  className="field__input"
                  value={title}
                  placeholder="예: 백엔드 엔지니어"
                  onChange={(event) => setTitle(event.target.value)}
                />
              </label>
            </div>
            <div className="profile__save">
              <button
                type="button"
                className="btn btn--primary btn--sm"
                disabled={busy}
                onClick={() => void save()}
              >
                저장
              </button>
            </div>
          </div>
        </div>

        <Fact
          label="계정"
          value={user?.email ?? ""}
          hint={`${roleLabel(role)} · ${user?.created_at ? `${formatDate(user.created_at)} 가입` : ""}`}
        />

        <div className="setrow">
          <div className="setrow__text">
            <p className="setrow__label">조직</p>
            <p className="setrow__hint">
              {workspaceName} · 구성원 {members.length}명 · {roleLabel(role)}
            </p>
          </div>
          <div className="setrow__control">
            {others.length ? (
              <div className="switcher">
                {others.map((workspace) => (
                  <button
                    key={workspace.id}
                    type="button"
                    className="btn btn--sm"
                    onClick={() => {
                      void loadWorkspace(workspace.id);
                      setDialog(null);
                    }}
                  >
                    <Building2 size={13} aria-hidden="true" />
                    {workspace.name}
                  </button>
                ))}
              </div>
            ) : (
              <span className="setrow__value">
                <Building2 size={13} aria-hidden="true" />
                {workspaceName}
              </span>
            )}
          </div>
        </div>

        <Row label="로그아웃" hint="이 기기에서 나갑니다. 대화와 파일은 그대로 남습니다.">
          <button
            type="button"
            className="btn btn--sm"
            onClick={() => {
              signOut();
              setDialog(null);
            }}
          >
            <LogOut size={13} aria-hidden="true" />
            로그아웃
          </button>
        </Row>
      </div>
    </>
  );
}

function roleLabel(role: Role | undefined): string {
  if (role === "owner") return "소유자";
  if (role === "admin") return "관리자";
  return "구성원";
}

/* ── 파일 및 링크 ───────────────────────────────────────────────────── */

function Files() {
  const settings = useSettings();
  const desktop = useInDesktop();
  const [picking, setPicking] = useState(false);

  const choose = async () => {
    setPicking(true);
    try {
      const folder = await pickFolder("다운로드 폴더 고르기");
      if (folder) setSettings({ downloadFolder: folder });
    } finally {
      setPicking(false);
    }
  };

  const folderName = useMemo(() => {
    const folder = settings.downloadFolder;
    if (!folder) return null;
    const parts = folder.split(/[\\/]/).filter(Boolean);
    return parts[parts.length - 1] ?? folder;
  }, [settings.downloadFolder]);

  const saving = settings.fileOpen === "save";

  return (
    <>
      <h3 className="settings__heading">파일 및 링크</h3>
      <p className="settings__lead">파일을 어디에 두고, 어떻게 보여줄지 정합니다.</p>

      <div className="setgroup">
        <Row
          label="다운로드 폴더"
          hint={
            desktop
              ? "파일을 내려받을 때 이 폴더에 넣습니다."
              : "폴더를 고르는 것은 데스크톱 앱에서만 됩니다."
          }
        >
          <div className="folderpick">
            <span className="folderpick__path" title={settings.downloadFolder ?? ""}>
              <FolderDown size={13} aria-hidden="true" />
              {folderName ?? "설정되지 않음"}
            </span>
            <button
              type="button"
              className="btn btn--sm"
              disabled={!desktop || picking}
              onClick={() => void choose()}
            >
              <FolderDown size={13} aria-hidden="true" />
              폴더 고르기
            </button>
            {settings.downloadFolder ? (
              <button
                type="button"
                className="btn btn--quiet btn--sm"
                onClick={() => setSettings({ downloadFolder: null })}
              >
                지우기
              </button>
            ) : null}
          </div>
        </Row>

        <Row
          label="파일을 열 때"
          hint={
            saving && !settings.downloadFolder
              ? "먼저 폴더를 고르세요. 폴더가 없으면 원래 위치에서 열립니다."
              : "원래 위치에서 열거나, 폴더에 내려받아 저장합니다."
          }
        >
          <Segmented
            value={settings.fileOpen}
            label="파일을 열 때"
            options={[
              { value: "open", label: "원래 위치에서 열기" },
              { value: "save", label: "폴더에 저장", disabled: !desktop },
            ]}
            onChange={(next) => setSettings({ fileOpen: next })}
          />
        </Row>

        <Row label="이미지 미리보기" hint="이미지를 메시지 안에 그대로 펼쳐 보여줍니다.">
          <Switch
            checked={settings.imagePreview}
            onChange={(next) => setSettings({ imagePreview: next })}
            label="이미지 미리보기"
          />
        </Row>
      </div>
    </>
  );
}
