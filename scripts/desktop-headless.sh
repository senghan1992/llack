#!/usr/bin/env bash
#
# 헤드리스(Xvfb)에서 실제 Tauri 데스크톱 앱을 띄우고 스크린샷을 남깁니다.
#
#   scripts/desktop-headless.sh                       # 앱을 띄우고 기본 경로에 캡처
#   scripts/desktop-headless.sh --shot /tmp/a.png     # 캡처 경로 지정
#   scripts/desktop-headless.sh --login               # 데모 계정으로 로그인한 화면까지
#   scripts/desktop-headless.sh --stop                # 띄워둔 앱 정리
#
# 필요: Xvfb, ffmpeg. --login 은 xdotool 도 필요합니다.
#
# 왜 이게 필요한가: 웹 브라우저로 보는 것과 데스크톱 셸로 보는 것은 다릅니다.
# 셸은 프런트엔드에 API 주소를 심고, 창 상태를 저장하고, OS 알림을 띄웁니다.
# Xvfb 위에서 진짜 바이너리를 띄우면 그 경로까지 함께 검증됩니다.
#
# 창 좌표는 로그인 화면 레이아웃 기준입니다(창 기준 오프셋).
#   이메일 필드 (319, 374) · 비밀번호 (319, 449) · 로그인 버튼 (319, 593)

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BIN="$ROOT/desktop/src-tauri/target/release/llack"
DISPLAY_NUM="${LLACK_DISPLAY:-:99}"
SHOT="$ROOT/desktop/headless.png"
LOG="/tmp/llack-headless.log"
APP_PID_FILE="/tmp/llack-headless-app.pid"
XVFB_PID_FILE="/tmp/llack-headless-xvfb.pid"
DO_LOGIN=0
DO_STOP=0
WIDTH=1440
HEIGHT=900

while [[ $# -gt 0 ]]; do
  case "$1" in
    --shot) SHOT="$2"; shift 2 ;;
    --display) DISPLAY_NUM="$2"; shift 2 ;;
    --login) DO_LOGIN=1; shift ;;
    --stop) DO_STOP=1; shift ;;
    -h|--help) sed -n '2,20p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) echo "알 수 없는 인자: $1" >&2; exit 2 ;;
  esac
done

die() { echo "오류: $*" >&2; exit 1; }
need() { command -v "$1" >/dev/null || die "$1 이(가) 필요합니다 (apt-get install $2)"; }

kill_pidfile() {
  [[ -f "$1" ]] || return 0
  local pid
  pid="$(cat "$1" 2>/dev/null || true)"
  if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
    kill "$pid" 2>/dev/null || true
  fi
  rm -f "$1"
}

# ── 정리 ────────────────────────────────────────────────────────────────
stop_all() {
  # pkill -f 는 명령줄 전체를 훑으므로 사용자의 셸까지 죽일 수 있습니다.
  # PID 파일과 정확한 프로세스 이름(llack)만으로 정리합니다.
  kill_pidfile "$APP_PID_FILE"
  for pid in $(pgrep -x llack 2>/dev/null || true); do
    kill "$pid" 2>/dev/null || true
  done
  kill_pidfile "$XVFB_PID_FILE"
  echo "정리했습니다."
}

if [[ $DO_STOP -eq 1 ]]; then
  stop_all
  exit 0
fi

need ffmpeg ffmpeg
need Xvfb xvfb

# ── 1. 빌드 ────────────────────────────────────────────────────────────
if [[ ! -x "$BIN" ]]; then
  echo "▸ 릴리스 셸을 빌드합니다 (1~2분 걸립니다)"
  (cd "$ROOT/desktop/src-tauri" && cargo build --release)
fi

# ── 2. 가상 화면 ───────────────────────────────────────────────────────
if [[ ! -e "/tmp/.X11-unix/X${DISPLAY_NUM#:}" ]]; then
  echo "▸ Xvfb $DISPLAY_NUM 을 띄웁니다 (${WIDTH}x${HEIGHT})"
  setsid Xvfb "$DISPLAY_NUM" -screen 0 "${WIDTH}x${HEIGHT}x24" -nolisten tcp \
    >/tmp/xvfb"${DISPLAY_NUM#:}".log 2>&1 < /dev/null &
  echo $! > "$XVFB_PID_FILE"
  disown || true
  sleep 2
fi
export DISPLAY="$DISPLAY_NUM"

# ── 3. 앱 실행 ─────────────────────────────────────────────────────────
# 앱 프로필을 임시 홈으로 격리합니다. 그러면 매번 로그인 화면에서 시작하고
# (저장된 세션 때문에 이미 로그인된 상태로 뜨는 일이 없고) 창 상태도
# 오염되지 않습니다.
HEADLESS_HOME="${LLACK_HEADLESS_HOME:-/tmp/llack-headless-home}"
rm -rf "${HEADLESS_HOME:?}/data"
mkdir -p "$HEADLESS_HOME/data" "$HEADLESS_HOME/config"
export XDG_DATA_HOME="$HEADLESS_HOME/data"
export XDG_CONFIG_HOME="$HEADLESS_HOME/config"

echo "▸ 앱을 띄웁니다"
# 이전에 띄워둔 인스턴스가 남아 있으면 창이 둘이 되어 캡처가 꼬입니다.
kill_pidfile "$APP_PID_FILE"
sleep 0.5

WEBKIT_DISABLE_COMPOSITING_MODE=1 \
WEBKIT_DISABLE_DMABUF_RENDERER=1 \
WEBKIT_DISABLE_SANDBOX_THIS_IS_DANGEROUS=1 \
LIBGL_ALWAYS_SOFTWARE=1 \
GDK_BACKEND=x11 \
setsid "$BIN" >"$LOG" 2>&1 < /dev/null &
disown || true

# 앱의 실제 PID를 기록합니다. setsid 는 상황에 따라 fork 하므로 $! 를
# 그대로 믿으면 엉뚱한 PID가 저장됩니다. 이름이 정확히 llack 인 프로세스만
# 찾으므로 다른 셸은 건드리지 않습니다.
APP_PID=""
for _ in $(seq 1 25); do
  APP_PID="$(pgrep -x llack 2>/dev/null | tail -1 || true)"
  [[ -n "$APP_PID" ]] && break
  sleep 0.2
done
[[ -n "$APP_PID" ]] || die "앱 프로세스가 뜨지 않았습니다 (로그: $LOG)"
echo "$APP_PID" > "$APP_PID_FILE"

# 창이 뜰 때까지 기다린다.
# GTK는 10x10짜리 유틸리티 창도 같은 이름으로 노출한다. 앱 PID로 걸러
# 놓고, 그 안에서 제일 큰 창을 고른다(설정된 창은 1280x860).
geom() {
  xdotool getwindowgeometry --shell "$1" 2>/dev/null | awk -F= '
    /^X=/ {x=$2} /^Y=/ {y=$2} /^WIDTH=/ {w=$2} /^HEIGHT=/ {h=$2}
    END {print x, y, w, h}'
}

WID=""
for _ in $(seq 1 40); do
  if command -v xdotool >/dev/null; then
    WID=""
    best=0
    for id in $(xdotool search --pid "$APP_PID" --name 'Llack' 2>/dev/null || true); do
      read -r _ _ w h < <(geom "$id")
      [[ -n "${w:-}" && -n "${h:-}" ]] || continue
      if (( w * h > best )); then
        best=$((w * h))
        WID="$id"
      fi
    done
  fi
  [[ -n "$WID" ]] && break
  sleep 0.5
done
[[ -n "$WID" ]] || die "창이 열리지 않았습니다 (로그: $LOG)"
echo "▸ 창 준비됨 (창 id $WID, 프로세스 $APP_PID)"

# ── 4. 로그인 (선택) ───────────────────────────────────────────────────
if [[ $DO_LOGIN -eq 1 ]]; then
  command -v xdotool >/dev/null || die "--login 에는 xdotool 이 필요합니다 (apt-get install xdotool)"
  read -r X Y _ _ < <(geom "$WID")
  echo "▸ 로그인합니다 (창 ${X},${Y} 기준)"
  xdotool windowfocus "$WID"
  sleep 1
  xdotool mousemove $((X + 319)) $((Y + 374)) click 1; sleep 0.4
  xdotool key --clearmodifiers ctrl+a; sleep 0.2
  xdotool type --delay 25 "${LLACK_EMAIL:-hyunjin@hanbit.co.kr}"; sleep 0.4
  xdotool mousemove $((X + 319)) $((Y + 449)) click 1; sleep 0.4
  xdotool key --clearmodifiers ctrl+a; sleep 0.2
  xdotool type --delay 25 "${LLACK_PASSWORD:-hanbit2026}"; sleep 0.6
  xdotool mousemove $((X + 319)) $((Y + 593)) click 1
  sleep 4
fi

# ── 5. 캡처 ────────────────────────────────────────────────────────────
sleep 1
read -r X Y W H < <(geom "$WID")

if [[ -n "${W:-}" ]]; then
  ffmpeg -y -f x11grab -video_size "${WIDTH}x${HEIGHT}" -i "$DISPLAY" -frames:v 1 -update 1 \
    -vf "crop=${W}:${H}:${X}:${Y}" "$SHOT" >/dev/null 2>&1
else
  ffmpeg -y -f x11grab -video_size "${WIDTH}x${HEIGHT}" -i "$DISPLAY" -frames:v 1 -update 1 \
    "$SHOT" >/dev/null 2>&1
fi

echo "▸ 캡처: $SHOT"
echo "▸ 앱은 계속 떠 있습니다. 종료: scripts/desktop-headless.sh --stop"
