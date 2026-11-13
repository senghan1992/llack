import { useEffect, useMemo, useState } from "react";
import { Dialog } from "./Dialogs";
import { Select } from "./Select";
import { FormRow, FormTitle } from "./Form";
import { useStore } from "../store/useStore";
import type { OrgUnitInput } from "../lib/types";

/**
 * The "new unit" dialog. It answers for the two places a unit is made
 * from: the tree's own button, where the parent is chosen here, and the
 * detail pane's "하위 조직 추가", where the parent is the unit that is
 * open and cannot be changed.
 */
export function OrgUnitDialog() {
  /** The unit the new unit hangs on — null when the parent is chosen here. */
  const parentId = useStore((s) => s.dialogTarget);
  const units = useStore((s) => s.orgUnits);
  const members = useStore((s) => s.members);
  const user = useStore((s) => s.user);
  const managedUnitIds = useStore((s) => s.orgManagedUnitIds);
  const createOrgUnit = useStore((s) => s.createOrgUnit);
  const setDialog = useStore((s) => s.setDialog);

  const [name, setName] = useState("");
  const [kind, setKind] = useState("");
  const [description, setDescription] = useState("");
  const [parentChoice, setParentChoice] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // My own role in the workspace — the same place the rail reads it.
  const myRole = members.find((member) => member.user.id === user?.id)?.role;
  const isWorkspaceAdmin = myRole === "owner" || myRole === "admin";

  const parentUnit = useMemo(
    () => units.find((unit) => unit.id === parentId) ?? null,
    [units, parentId],
  );

  /**
   * The units a new unit may hang on: a top-level unit is the owner's own
   * right, and below that only the units I manage.
   */
  const creatable = useMemo(
    () =>
      isWorkspaceAdmin
        ? units
        : units.filter(
            (unit) => unit.is_manager || managedUnitIds.includes(unit.id),
          ),
    [units, isWorkspaceAdmin, managedUnitIds],
  );

  // The parent the dialog opens with: the fixed one, or the first place I
  // may put a unit.
  useEffect(() => {
    if (parentId) {
      setParentChoice(parentId);
      return;
    }
    setParentChoice(isWorkspaceAdmin ? "" : (creatable[0]?.id ?? ""));
  }, [parentId, isWorkspaceAdmin, creatable]);

  const submit = async () => {
    const trimmed = name.trim();
    if (!trimmed) {
      setError("조직 이름을 입력해 주세요");
      return;
    }
    setBusy(true);
    setError(null);
    const input: OrgUnitInput = {
      name: trimmed,
      parent_id: parentId ?? (parentChoice || null),
      kind: kind.trim(),
      description: description.trim(),
    };
    const made = await createOrgUnit(input);
    setBusy(false);
    if (made) setDialog(null);
  };

  return (
    <Dialog
      title="새 조직"
      onClose={() => setDialog(null)}
      footer={
        <>
          <span className="u-grow" />
          <button
            type="button"
            className="btn"
            onClick={() => setDialog(null)}
            disabled={busy}
          >
            취소
          </button>
          <button
            type="button"
            className="btn btn--primary"
            onClick={() => void submit()}
            disabled={busy}
          >
            만들기
          </button>
        </>
      }
    >
      <div className="dialog__body u-col u-gap-3">
        {error ? <p className="field__error">{error}</p> : null}

        <div className="form">
          <FormTitle
            id="org-new-name"
            value={name}
            onChange={setName}
            placeholder="조직 이름"
            label="조직 이름"
            autoFocus
            maxLength={120}
            onEnter={() => void submit()}
          />

          <FormRow label="조직 종류" htmlFor="org-new-kind">
            <input
              id="org-new-kind"
              className="field__input"
              value={kind}
              placeholder="부서 또는 팀"
              maxLength={24}
              onChange={(event) => setKind(event.target.value)}
            />
          </FormRow>

          <FormRow label="설명" htmlFor="org-new-desc">
            <textarea
              id="org-new-desc"
              className="field__input u-h-auto u-minh-72 u-full u-py-2"
              value={description}
              maxLength={4000}
              onChange={(event) => setDescription(event.target.value)}
            />
          </FormRow>

          {parentUnit ? (
            <FormRow label="상위 조직">
              <p className="orgdlg__parent">{parentUnit.name}</p>
            </FormRow>
          ) : (
            <FormRow label="상위 조직">
              <Select
                value={parentChoice}
                onChange={setParentChoice}
                ariaLabel="상위 조직"
                options={[
                  ...(isWorkspaceAdmin
                    ? [{ value: "", label: "최상위 조직" }]
                    : []),
                  ...creatable.map((unit) => ({ value: unit.id, label: unit.name })),
                ]}
              />
            </FormRow>
          )}
        </div>
      </div>
    </Dialog>
  );
}
