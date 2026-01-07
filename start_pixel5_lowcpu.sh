#!/bin/bash

# ====== 可按需修改的参数 ======
AVD_NAME="Pixel_5"
EMULATOR_BIN="/mnt/data/TOOL/anzhuomoniqi/emulator/emulator"
CORES=2
MEMORY=1536
RENICE_VALUE=5
# =============================

echo "▶ Starting Android Emulator: $AVD_NAME"

$EMULATOR_BIN \
  -avd "$AVD_NAME" \
  -gpu swiftshader_indirect \
  -cores $CORES \
  -memory $MEMORY \
  -no-snapshot-load \
  -no-audio &

EMU_PID=$!
echo "▶ Emulator process PID: $EMU_PID"

# 等待 adb 就绪
echo "▶ Waiting for adb device..."
adb wait-for-device

# 等待系统完全启动
echo "▶ Waiting for Android system boot..."
while [[ "$(adb shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')" != "1" ]]; do
  sleep 2
done

echo "✔ Android boot completed"

# 关闭所有动画（极大降低 CPU）
echo "▶ Disabling Android animations"
adb shell settings put global animator_duration_scale 0
adb shell settings put global transition_animation_scale 0
adb shell settings put global window_animation_scale 0

# 找 qemu-system 进程并降优先级
QEMU_PID=$(pgrep -f qemu-system | head -n 1)

if [[ -n "$QEMU_PID" ]]; then
  echo "▶ Lowering priority of qemu-system (PID=$QEMU_PID)"
  sudo renice +$RENICE_VALUE -p "$QEMU_PID"
else
  echo "⚠ Could not find qemu-system PID"
fi

echo "✔ Emulator started with low CPU profile"
