import { useEffect, useMemo, useState, type CSSProperties, type ReactNode } from "react";
import {
  Building2,
  FolderTree,
  Menu as MenuIcon,
  Plus,
  Search,
  Trash2,
  UserMinus,
} from "lucide-react";
import { Avatar } from "./Avatar";
import { PersonPicker } from "./PersonPicker";
import { Select } from "./Select";
import { useStore } from "../store/useStore";
import type { Role } from "../lib/types";

/** The role a person holds in the workspace, in the app's own words. */
const ROLE_LABEL: Record<Role, string> = {
  owner: "소유자",
  admin: "관리자",
  member: "멤버",
};

export function OrgHead({
  onToggleRail,
  actions,
}: {
  onToggleRail: () => void;
  /** Extra keys at the edge of the bar. */
  actions?: ReactNode;
}) {
  return (
    <header className="head">
      <div className="head__inner">
        <button
          type="button"
          className="iconbtn head__menu"
          aria-label="채널 목록 열기"
          onClick={onToggleRail}
        >
          <MenuIcon size={17} aria-hidden="true" />
        </button>
        <Building2 size={17} className="u-muted" aria-hidden="true" />
        <div className="head__id">
          <span className="head__name">조직 관리</span>
        </div>
        <span className="head__topic">부서와 팀, 그리고 그 관리자를 봅니다</span>
        <div className="head__actions">{actions}</div>
      </div>
    </header>
  );
}

export function OrgView() {
  const units = useStore((s) => s.orgUnits);
  const admins = useStore((s) => s.orgAdmins);
  const loading = useStore((s) => s.orgLoading);
  const error = useStore((s) => s.orgError);
  const canManageAdmins = useStore((s) => s.orgCanManageAdmins);
  const activeUnitId = useStore((s) => s.activeOrgUnitId);
  const members = useStore((s) => s.members);
  const user = useStore((s) => s.user);
  const selectOrgUnit = useStore((s) => s.selectOrgUnit);
  const loadOrg = useStore((s) => s.loadOrg);
  const updateOrgUnit = useStore((s) => s.updateOrgUnit);
  const deleteOrgUnit = useStore((s) => s.deleteOrgUnit);
  const addOrgUnitMember = useStore((s) => s.addOrgUnitMember);
  const removeOrgUnitMember = useStore((s) => s.removeOrgUnitMember);
  const addOrgUnitManager = useStore((s) => s.addOrgUnitManager);
  const removeOrgUnitManager = useStore((s) => s.removeOrgUnitManager);
  const updateMemberRole = useStore((s) => s.updateMemberRole);
  const removeMember = useStore((s) => s.removeMember);
  const reportError = useStore((s) => s.reportError);
  const setDialog = useStore((s) => s.setDialog);

  const [query, setQuery] = useState("");
  const [confirmDelete, setConfirmDelete] = useState(false);
  /** The person whose place in the workspace is being taken away. */
  const [removingAdminId, setRemovingAdminId] = useState<string | null>(null);
  const [form, setForm] = useState({ name: "", kind: "", description: "" });

  // My own role in the workspace — the same place the rail reads it.
  const myRole = members.find((member) => member.user.id === user?.id)?.role;
  const isWorkspaceAdmin = myRole === "owner" || myRole === "admin";

  // The tree is a flat list on the server — it is read here as a tree.
  const ordered = useMemo(
    () =>
      [...units].sort(
        (a, b) =>
          a.depth - b.depth || a.position - b.position || a.name.localeCompare(b.name),
      ),
    [units],
  );

  const needle = query.trim().toLowerCase();
  const visible = useMemo(
    () => (needle ? ordered.filter((unit) => unit.name.toLowerCase().includes(needle)) : ordered),
    [ordered, needle],
  );

  const unit = useMemo(
    () => units.find((item) => item.id === activeUnitId) ?? null,
    [units, activeUnitId],
  );

  // The unit below the open one — a unit may never be moved into its own
  // branch.
  const descendants = useMemo(() => {
    const ids = new Set<string>();
    if (!unit) return ids;
    const walk = (parentId: string) => {
      for (const child of units) {
        if (child.parent_id === parentId && !ids.has(child.id)) {
          ids.add(child.id);
          walk(child.id);
        }
      }
    };
    walk(unit.id);
    return ids;
  }, [units, unit]);

  const parentOptions = useMemo(() => {
    if (!unit) return [];
    return units
      .filter((item) => item.id !== unit.id && !descendants.has(item.id))
      .map((item) => ({ value: item.id, label: item.name }));
  }, [units, unit, descendants]);

  // The form follows the unit that is open.
  useEffect(() => {
    setForm({
      name: unit?.name ?? "",
      kind: unit?.kind ?? "",
      description: unit?.description ?? "",
    });
    setConfirmDelete(false);
  }, [unit?.id]);

  const saveUnit = async () => {
    if (!unit) return;
    const name = form.name.trim();
    if (!name) return;
    await updateOrgUnit(unit.id, {
      name,
      kind: form.kind.trim(),
      description: form.description.trim(),
    });
  };

  /** The role of an admin — the owner is the one, and nobody else. */
  const roleOptions = (role: Role) =>
    role === "owner"
      ? [
          { value: "owner", label: ROLE_LABEL.owner },
          { value: "admin", label: ROLE_LABEL.admin },
          { value: "member", label: ROLE_LABEL.member },
        ]
      : [
          { value: "admin", label: ROLE_LABEL.admin },
          { value: "member", label: ROLE_LABEL.member },
        ];

  const changeRole = async (userId: string, role: string) => {
    try {
      await updateMemberRole(userId, role as Role);
      await loadOrg();
    } catch (err) {
      // The server has the last word — its own sentence is the answer.
      reportError(err, "권한을 변경하지 못했습니다");
    }
  };

  const appointAdmin = async (userId: string) => {
    await changeRole(userId, "admin");
  };

  /**
   * Take the appointment away. The person stays in the workspace, so the
   * appointment may be given again at any time.
   */
  const demoteAdmin = async (userId: string) => {
    await changeRole(userId, "member");
  };

  const dropMember = async (userId: string) => {
    setRemovingAdminId(null);
    try {
      await removeMember(userId);
      await loadOrg();
    } catch (err) {
      reportError(err, "멤버를 내보내지 못했습니다");
    }
  };

  /**
   * The people who may still be appointed. Everyone who is not an owner or
   * an admin right now: a person whose appointment was taken away comes
   * back here, and may be appointed again at any time.
   */
  const adminCandidates = useMemo(
    () => members.filter((member) => member.role !== "owner" && member.role !== "admin"),
    [members],
  );

  return (
    <div className="org">
      <section className="org__admins" aria-label="워크스페이스 관리자">
        <header className="org__adminshead">
          <div className="u-col">
            <h2 className="org__sectiontitle">워크스페이스 관리자</h2>
            <p className="org__sectionhint">
              워크스페이스 소유자가 관리자를 임명합니다
            </p>
          </div>
          {canManageAdmins ? (
            <PersonPicker
              size="sm"
              members={adminCandidates}
              placeholder="관리자 임명"
              ariaLabel="관리자 임명"
              emptyText="임명할 사람이 없습니다."
              onPick={(userId) => void appointAdmin(userId)}
            />
          ) : null}
        </header>

        {loading && admins.length === 0 ? (
          <div className="org__skels" aria-hidden="true">
            <span className="skel org__skel" />
          </div>
        ) : admins.length === 0 ? (
          <p className="org__hint">아직 워크스페이스 관리자가 없습니다</p>
        ) : (
          <ul className="org__adminlist">
            {admins.map((admin) => (
              <li key={admin.user.id} className="org__adminrow">
                <Avatar user={admin.user} size="sm" />
                <span className="org__adminname u-truncate">{admin.user.name}</span>
                <span className="org__admintitle u-tiny u-muted u-truncate">
                  {admin.user.title ?? ROLE_LABEL[admin.role]}
                </span>
                {canManageAdmins ? (
                  <>
                    <Select
                      size="sm"
                      value={admin.role}
                      ariaLabel={`${admin.user.name} 권한`}
                      options={roleOptions(admin.role)}
                      onChange={(next) => void changeRole(admin.user.id, next)}
                    />
                    {admin.role === "admin" ? (
                      <button
                        type="button"
                        className="iconbtn"
                        aria-label={`${admin.user.name} 관리자 임면 해제`}
                        title="관리자 임면 해제"
                        onClick={() => void demoteAdmin(admin.user.id)}
                      >
                        <UserMinus size={14} aria-hidden="true" />
                      </button>
                    ) : null}
                    <button
                      type="button"
                      className="iconbtn"
                      aria-label={`${admin.user.name} 워크스페이스에서 내보내기`}
                      title="워크스페이스에서 내보내기"
                      onClick={() => setRemovingAdminId(admin.user.id)}
                    >
                      <Trash2 size={14} aria-hidden="true" />
                    </button>
                  </>
                ) : (
                  <span className="u-tiny u-muted">{ROLE_LABEL[admin.role]}</span>
                )}
              </li>
            ))}
          </ul>
        )}
        {removingAdminId ? (
          <div className="org__confirm">
            <span>
              ‘{admins.find((admin) => admin.user.id === removingAdminId)?.user.name}’님을
              워크스페이스에서 내보낼까요?
            </span>
            <span className="u-grow" />
            <button
              type="button"
              className="btn btn--sm"
              onClick={() => setRemovingAdminId(null)}
            >
              취소
            </button>
            <button
              type="button"
              className="btn btn--sm btn--danger"
              onClick={() => void dropMember(removingAdminId)}
            >
              내보내기
            </button>
          </div>
        ) : null}
      </section>

      <div className="org__body">
        <aside className="org__tree" aria-label="조직도">
          <div className="org__treehead">
            <span className="org__treetitle">조직</span>
            {isWorkspaceAdmin ? (
              <button
                type="button"
                className="rail__add"
                aria-label="최상위 조직 추가"
                onClick={() => setDialog("newOrgUnit", null)}
              >
                <Plus size={14} aria-hidden="true" />
              </button>
            ) : null}
          </div>

          <div className="find">
            <Search size={15} className="u-muted" aria-hidden="true" />
            <input
              className="find__input"
              value={query}
              placeholder="조직 이름으로 찾기"
              aria-label="조직 검색"
              onChange={(event) => setQuery(event.target.value)}
            />
          </div>

          <div className="org__treescroll">
            {error ? (
              <div className="errorstate">
                <p className="errorstate__title">조직을 불러오지 못했습니다</p>
                <p className="errorstate__text">{error}</p>
                <button
                  type="button"
                  className="btn btn--sm"
                  onClick={() => void loadOrg()}
                >
                  다시 시도
                </button>
              </div>
            ) : null}

            {!error && loading && units.length === 0 ? (
              <div className="org__skels" aria-hidden="true">
                {[0, 1, 2, 3, 4].map((row) => (
                  <span key={row} className="skel org__skel" />
                ))}
              </div>
            ) : null}

            {!error && !loading && units.length === 0 ? (
              <div className="empty">
                <span className="empty__mark" aria-hidden="true">
                  <Building2 size={20} />
                </span>
                <p className="empty__title">아직 조직이 없습니다</p>
                <p className="empty__text">
                  팀의 부서와 팀을 만들고, 각 조직의 관리자를 정합니다.
                </p>
                {isWorkspaceAdmin ? (
                  <button
                    type="button"
                    className="btn btn--sm empty__action"
                    onClick={() => setDialog("newOrgUnit", null)}
                  >
                    첫 조직 만들기
                  </button>
                ) : null}
              </div>
            ) : null}

            {!error && units.length > 0 && visible.length === 0 ? (
              <p className="u-small u-muted u-px-2 u-py-2">
                일치하는 조직이 없습니다.
              </p>
            ) : null}

            {visible.map((item) => (
              <button
                key={item.id}
                type="button"
                className={`orgrow${item.id === activeUnitId ? " orgrow--on" : ""}`}
                style={{ "--org-depth": item.depth } as CSSProperties}
                aria-current={item.id === activeUnitId ? "true" : undefined}
                onClick={() => selectOrgUnit(item.id)}
              >
                <span className="orgrow__name u-truncate">{item.name}</span>
                {item.is_manager ? (
                  <span className="badge orgrow__badge">관리자</span>
                ) : null}
                <span className="orgrow__count">{item.member_count}</span>
              </button>
            ))}
          </div>
        </aside>

        <section className="org__detail" aria-label="조직 상세">
          {!unit ? (
            <div className="empty">
              <span className="empty__mark" aria-hidden="true">
                <FolderTree size={20} />
              </span>
              <p className="empty__title">조직을 골라 주세요</p>
              <p className="empty__text">
                왼쪽에서 조직을 고르면 그 안의 사람과 관리자를 볼 수 있습니다.
              </p>
            </div>
          ) : (
            <div className="org__scroll">
              <header className="org__detailhead">
                <div className="u-col u-grow">
                  <h2 className="org__name">{unit.name}</h2>
                  <p className="org__meta">
                    {unit.kind || "팀"} · 구성원 {unit.member_count}명 · 하위 조직{" "}
                    {unit.child_count}개
                  </p>
                </div>
              </header>

              {unit.can_manage ? (
                <form
                  className="org__form"
                  onSubmit={(event) => {
                    event.preventDefault();
                    void saveUnit();
                  }}
                >
                  <div className="field">
                    <label className="field__label" htmlFor="org-unit-name">
                      조직 이름
                    </label>
                    <input
                      id="org-unit-name"
                      className="field__input"
                      value={form.name}
                      maxLength={120}
                      onChange={(event) =>
                        setForm((state) => ({ ...state, name: event.target.value }))
                      }
                    />
                  </div>
                  <div className="field">
                    <label className="field__label" htmlFor="org-unit-kind">
                      조직 종류
                    </label>
                    <input
                      id="org-unit-kind"
                      className="field__input"
                      value={form.kind}
                      placeholder="부서, 팀"
                      maxLength={60}
                      onChange={(event) =>
                        setForm((state) => ({ ...state, kind: event.target.value }))
                      }
                    />
                  </div>
                  <div className="field">
                    <label className="field__label" htmlFor="org-unit-desc">
                      설명
                    </label>
                    <textarea
                      id="org-unit-desc"
                      className="field__input org__textarea"
                      value={form.description}
                      maxLength={500}
                      onChange={(event) =>
                        setForm((state) => ({
                          ...state,
                          description: event.target.value,
                        }))
                      }
                    />
                  </div>
                  <div className="u-row u-gap-2">
                    <button
                      type="submit"
                      className="btn btn--sm btn--primary"
                      disabled={!form.name.trim()}
                    >
                      저장
                    </button>
                  </div>
                </form>
              ) : (
                <section className="org__section">
                  <h3 className="org__sectiontitle">소개</h3>
                  {unit.description ? (
                    <p className="org__text">{unit.description}</p>
                  ) : (
                    <p className="org__hint">소개가 없습니다</p>
                  )}
                </section>
              )}

              <section className="org__section">
                <header className="org__sectionhead">
                  <h3 className="org__sectiontitle">관리자</h3>
                  {unit.can_appoint_managers ? (
                    <PersonPicker
                      size="sm"
                      members={members}
                      exclude={unit.managers.map((person) => person.id)}
                      placeholder="관리자 지정"
                      ariaLabel="관리자 지정"
                      emptyText="임명할 사람이 없습니다."
                      onPick={(userId) => void addOrgUnitManager(unit.id, userId)}
                    />
                  ) : null}
                </header>
                {unit.managers.length === 0 ? (
                  <p className="org__hint">이 조직에는 관리자가 없습니다</p>
                ) : (
                  <ul className="org__people">
                    {unit.managers.map((person) => (
                      <li key={person.id} className="org__person">
                        <Avatar user={person} size="sm" />
                        <span className="u-grow u-truncate">{person.name}</span>
                        {unit.can_appoint_managers ? (
                          <button
                            type="button"
                            className="iconbtn"
                            aria-label={`${person.name} 관리자 해제`}
                            onClick={() => void removeOrgUnitManager(unit.id, person.id)}
                          >
                            <UserMinus size={14} aria-hidden="true" />
                          </button>
                        ) : null}
                      </li>
                    ))}
                  </ul>
                )}
              </section>

              <section className="org__section">
                <header className="org__sectionhead">
                  <h3 className="org__sectiontitle">구성원</h3>
                  {unit.can_manage ? (
                    <PersonPicker
                      size="sm"
                      members={members}
                      exclude={unit.members.map((person) => person.id)}
                      placeholder="사람 추가"
                      ariaLabel="사람 추가"
                      emptyText="추가할 사람이 없습니다."
                      onPick={(userId) => void addOrgUnitMember(unit.id, userId)}
                    />
                  ) : null}
                </header>
                {unit.members.length === 0 ? (
                  <p className="org__hint">이 조직에는 아직 사람이 없습니다</p>
                ) : (
                  <ul className="org__people">
                    {unit.members.map((person) => (
                      <li key={person.id} className="org__person">
                        <Avatar user={person} size="sm" />
                        <span className="u-grow u-truncate">{person.name}</span>
                        {unit.can_manage ? (
                          <button
                            type="button"
                            className="iconbtn"
                            aria-label={`${person.name} 내보내기`}
                            onClick={() => void removeOrgUnitMember(unit.id, person.id)}
                          >
                            <UserMinus size={14} aria-hidden="true" />
                          </button>
                        ) : null}
                      </li>
                    ))}
                  </ul>
                )}
              </section>

              {unit.can_manage ? (
                <>
                  <section className="org__section">
                    <h3 className="org__sectiontitle">하위 조직</h3>
                    <button
                      type="button"
                      className="btn btn--sm"
                      onClick={() => setDialog("newOrgUnit", unit.id)}
                    >
                      <Plus size={13} aria-hidden="true" />
                      하위 조직 추가
                    </button>
                  </section>

                  <section className="org__section">
                    <h3 className="org__sectiontitle">상위 조직 이동</h3>
                    <Select
                      value={unit.parent_id ?? ""}
                      ariaLabel="상위 조직"
                      options={[
                        { value: "", label: "최상위 조직" },
                        ...parentOptions,
                      ]}
                      onChange={(next) =>
                        void updateOrgUnit(unit.id, { parent_id: next || null })
                      }
                    />
                  </section>

                  <section className="org__section">
                    <h3 className="org__sectiontitle">조직 삭제</h3>
                    {confirmDelete ? (
                      <div className="org__confirm">
                        <span>‘{unit.name}’ 조직을 삭제할까요?</span>
                        <span className="u-grow" />
                        <button
                          type="button"
                          className="btn btn--sm"
                          onClick={() => setConfirmDelete(false)}
                        >
                          취소
                        </button>
                        <button
                          type="button"
                          className="btn btn--sm btn--danger"
                          onClick={() => {
                            setConfirmDelete(false);
                            void deleteOrgUnit(unit.id);
                          }}
                        >
                          삭제
                        </button>
                      </div>
                    ) : (
                      <button
                        type="button"
                        className="btn btn--sm btn--danger"
                        onClick={() => setConfirmDelete(true)}
                      >
                        <Trash2 size={13} aria-hidden="true" />
                        조직 삭제
                      </button>
                    )}
                  </section>
                </>
              ) : null}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
