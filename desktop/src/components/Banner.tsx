import { useApp } from "@/store/app";

export function Banner() {
  const banner = useApp((state) => state.banner);
  const dismiss = useApp((state) => state.dismissBanner);

  if (!banner) return null;

  return (
    <div className={`banner banner-${banner.kind}`} role="status">
      <span>{banner.message}</span>
      <button type="button" onClick={dismiss} aria-label="닫기">
        ×
      </button>
    </div>
  );
}
