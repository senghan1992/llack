import { Dialog } from "./Dialogs";

/**
 * Generic destructive-action confirmation.
 *
 * The copy is supplied by the caller; only the confirm button label has a
 * Korean default. Focus starts on the cancel button so an accidental Enter
 * cannot trigger the destructive action.
 */
export function ConfirmDialog({
  title,
  message,
  detail,
  confirmLabel = "삭제",
  busy = false,
  onConfirm,
  onClose,
}: {
  title: string;
  message: React.ReactNode;
  detail?: React.ReactNode;
  confirmLabel?: string;
  busy?: boolean;
  onConfirm: () => void;
  onClose: () => void;
}): React.JSX.Element {
  return (
    <Dialog
      title={title}
      onClose={onClose}
      footer={
        <>
          <button type="button" className="btn btn--sm" onClick={onClose} autoFocus>
            취소
          </button>
          <button
            type="button"
            className="btn btn--danger btn--sm"
            onClick={onConfirm}
            disabled={busy}
          >
            {confirmLabel}
          </button>
        </>
      }
    >
      <div className="dialog__body grid gap-3">
        <p>{message}</p>
        {detail ? <p className="u-small u-muted">{detail}</p> : null}
      </div>
    </Dialog>
  );
}
