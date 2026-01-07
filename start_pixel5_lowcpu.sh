#!/usr/bin/env bash
set -euo pipefail

# ================== 可配置参数 ==================
AVD_NAME="Pixel_5"
EMULATOR_BIN="/mnt/data/TOOL/anzhuomoniqi/emulator/emulator"

CORES=2
MEMORY=1536            # 注意：Pixel 5 AVD 可能会被 emulator 自动抬到 2048
GPU_MODE="swiftshader_indirect"

HEADLESS=0             # 1=无窗口(-no-window)  0=有窗口
KILL_EXISTING=1        # 1=启动前先杀掉所有已运行 emulator  0=不杀（可能触发同AVD多开FATAL）
ALLOW_SAME_AVD_MULTI=0 # 1=允许同AVD多开（加 -read-only） 0=不允许（推荐）

TARGET_SIZE="720x1280" # 你日志里用的是 720x1280；想 600x800 改这里
TARGET_DENSITY="160"

RENICE_VALUE=5
BOOT_TIMEOUT_SEC=240   # 等待开机超时（秒）
# =================================================

log() { echo -e "$*"; }

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || { echo "❌ Missing command: $1"; exit 127; }
}

require_cmd adb
require_cmd awk
require_cmd grep
require_cmd tr
require_cmd ps

log "▶ Starting Android Emulator: $AVD_NAME"

# ---------- 可选：启动前杀掉旧 emulator，避免同 AVD 多开 FATAL ----------
if [[ "$KILL_EXISTING" -eq 1 ]]; then
  log "▶ Checking existing emulator devices..."
  mapfile -t RUNNING_EMUS < <(adb devices | awk '/^emulator-[0-9]+\tdevice$/{print $1}')
  if [[ "${#RUNNING_EMUS[@]}" -gt 0 ]]; then
    log "▶ Found running emulator(s): ${RUNNING_EMUS[*]}"
    log "▶ Killing existing emulator(s)..."
    for d in "${RUNNING_EMUS[@]}"; do
      adb -s "$d" emu kill >/dev/null 2>&1 || true
    done
    sleep 3
  else
    log "✔ No running emulator found"
  fi
fi

# ---------- 记录启动前已有的 emulator 列表，用于识别“新启动”的那台 ----------
mapfile -t BEFORE_EMUS < <(adb devices | awk '/^emulator-[0-9]+\tdevice$/{print $1}')

# ---------- 组装 emulator 启动参数 ----------
EMU_ARGS=( -avd "$AVD_NAME"
          -gpu "$GPU_MODE"
          -cores "$CORES"
          -memory "$MEMORY"
          -no-snapshot-load
          -no-audio
)

if [[ "$HEADLESS" -eq 1 ]]; then
  EMU_ARGS+=( -no-window )
fi

if [[ "$ALLOW_SAME_AVD_MULTI" -eq 1 ]]; then
  EMU_ARGS+=( -read-only )
fi

# ---------- 启动 emulator ----------
"$EMULATOR_BIN" "${EMU_ARGS[@]}" >/dev/null 2>&1 &
EMU_PID=$!
log "▶ Emulator launcher PID: $EMU_PID"

# ---------- 等待新的 emulator deviceId 出现（不使用 adb wait-for-device，避免多设备报错） ----------
log "▶ Waiting for new emulator device to appear..."
DEVICE_ID=""
deadline=$((SECONDS + 60))

while [[ -z "$DEVICE_ID" && $SECONDS -lt $deadline ]]; do
  mapfile -t NOW_EMUS < <(adb devices | awk '/^emulator-[0-9]+\tdevice$/{print $1}')
  for e in "${NOW_EMUS[@]}"; do
    found=0
    for b in "${BEFORE_EMUS[@]:-}"; do
      [[ "$e" == "$b" ]] && found=1 && break
    done
    if [[ $found -eq 0 ]]; then
      DEVICE_ID="$e"
      break
    fi
  done
  sleep 1
done

# 兜底：如果没找出“新”的，就选当前唯一 emulator；如果多个则报错提示
if [[ -z "$DEVICE_ID" ]]; then
  mapfile -t NOW_EMUS < <(adb devices | awk '/^emulator-[0-9]+\tdevice$/{print $1}')
  if [[ "${#NOW_EMUS[@]}" -eq 1 ]]; then
    DEVICE_ID="${NOW_EMUS[0]}"
  else
    log "❌ Could not uniquely determine the new emulator device."
    log "   Current emulators: ${NOW_EMUS[*]:-NONE}"
    log "   Tip: set KILL_EXISTING=1 (recommended) or use ALLOW_SAME_AVD_MULTI=1 (-read-only)."
    exit 1
  fi
fi

log "▶ Using device: $DEVICE_ID"

# ---------- 等待系统完全启动（带超时） ----------
log "▶ Waiting for Android system boot (timeout ${BOOT_TIMEOUT_SEC}s)..."
boot_deadline=$((SECONDS + BOOT_TIMEOUT_SEC))
while [[ $SECONDS -lt $boot_deadline ]]; do
  v="$(adb -s "$DEVICE_ID" shell getprop sys.boot_completed 2>/dev/null | tr -d '\r' || true)"
  [[ "$v" == "1" ]] && break
  sleep 2
done

if [[ "$(adb -s "$DEVICE_ID" shell getprop sys.boot_completed 2>/dev/null | tr -d '\r' || true)" != "1" ]]; then
  log "❌ Boot timeout."
  exit 2
fi
log "✔ Android boot completed"

# ---------- 分辨率/DPI 设置 + 二次确认 ----------
log "▶ Forcing low resolution $TARGET_SIZE and density $TARGET_DENSITY"
adb -s "$DEVICE_ID" shell wm size "$TARGET_SIZE"
adb -s "$DEVICE_ID" shell wm density "$TARGET_DENSITY"

log "▶ Verifying resolution & density..."
WM_SIZE_OUT="$(adb -s "$DEVICE_ID" shell wm size 2>/dev/null | tr -d '\r')"
WM_DENSITY_OUT="$(adb -s "$DEVICE_ID" shell wm density 2>/dev/null | tr -d '\r')"

log "   wm size output:"
log "   $WM_SIZE_OUT"
log "   wm density output:"
log "   $WM_DENSITY_OUT"

echo "$WM_SIZE_OUT" | grep -q "Override size: $TARGET_SIZE" || {
  log "❌ Override size not applied (expected $TARGET_SIZE)"
  exit 3
}
echo "$WM_DENSITY_OUT" | grep -q "Override density: $TARGET_DENSITY" || {
  log "❌ Override density not applied (expected $TARGET_DENSITY)"
  exit 3
}
log "✔ Resolution & density verified"

# ---------- 关闭动画 ----------
log "▶ Disabling Android animations"
adb -s "$DEVICE_ID" shell settings put global animator_duration_scale 0
adb -s "$DEVICE_ID" shell settings put global transition_animation_scale 0
adb -s "$DEVICE_ID" shell settings put global window_animation_scale 0

# ---------- renice：尽量只 renice 本次启动关联的 qemu 进程 ----------
# 多数情况下，emulator 启动后会 fork 出实际的 qemu/system 进程；用子进程定位更稳
log "▶ Locating qemu process for renice..."
QEMU_PID="$(ps --ppid "$EMU_PID" -o pid= 2>/dev/null | awk '{print $1}' | head -n 1 || true)"

# 兜底：如果没抓到子进程，再用 pgrep 但做一次更精确过滤
if [[ -z "$QEMU_PID" ]]; then
  QEMU_PID="$(pgrep -f "qemu-system.*$AVD_NAME" | head -n 1 || true)"
fi

if [[ -n "$QEMU_PID" ]]; then
  log "▶ Lowering priority of qemu/system (PID=$QEMU_PID) -> nice +$RENICE_VALUE"
  sudo renice +"$RENICE_VALUE" -p "$QEMU_PID" || true
else
  log "⚠ Could not find qemu PID (skipping renice)"
fi

log "✔ Emulator started: device=$DEVICE_ID | size=$TARGET_SIZE | density=$TARGET_DENSITY | headless=$HEADLESS"
log "   Tip: stop it with: adb -s $DEVICE_ID emu kill"
