#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Minimal scrcpy raw stream diagnostic tool.
Starts scrcpy-server, connects to the forwarded socket, strips the 69-byte header,
and dumps raw H.264 bytes to a file for ffprobe/ffmpeg testing.

Usage:
  python3 scripts/scrcpy_diag.py --device SERIAL --out /tmp/scrcpy_raw.h264 --seconds 5
"""
import argparse
import os
import socket
import subprocess
import sys
import time
from collections import deque
from threading import Thread


SCRCPY_JAR_CANDIDATES = [
    "/opt/homebrew/share/scrcpy/scrcpy-server",
    "/usr/local/share/scrcpy/scrcpy-server",
    "/usr/share/scrcpy/scrcpy-server",
]


def find_scrcpy_jar():
    for p in SCRCPY_JAR_CANDIDATES:
        if os.path.exists(p):
            return p
    return None


def run(cmd, **kwargs):
    return subprocess.run(cmd, **kwargs)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--device", required=True, help="adb device serial")
    ap.add_argument("--out", default="/tmp/scrcpy_raw.h264", help="output file")
    ap.add_argument("--seconds", type=float, default=5.0, help="capture duration")
    ap.add_argument("--max-size", type=int, default=800)
    ap.add_argument("--bit-rate", type=int, default=2_000_000)
    ap.add_argument("--fps", type=int, default=15)
    args = ap.parse_args()

    jar = find_scrcpy_jar()
    if not jar:
        print("scrcpy-server JAR not found. Install scrcpy or set it in standard locations.", file=sys.stderr)
        return 2

    scid = f"{os.getpid() & 0x7FFFFFFF:08x}"
    # Pick a free local port
    tmp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    tmp.bind(("127.0.0.1", 0))
    local_port = tmp.getsockname()[1]
    tmp.close()

    # Push JAR
    run(["adb", "-s", args.device, "push", jar, "/data/local/tmp/scrcpy-server.jar"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)

    # Forward port (cleanup any existing forward on this port)
    run(["adb", "-s", args.device, "forward", "--remove", f"tcp:{local_port}"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    run(["adb", "-s", args.device, "forward", f"tcp:{local_port}", f"localabstract:scrcpy_{scid}"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)

    # Start server
    server = subprocess.Popen(
        ["adb", "-s", args.device, "shell",
         "CLASSPATH=/data/local/tmp/scrcpy-server.jar",
         "app_process", "/", "com.genymobile.scrcpy.Server", "3.3.4",
         f"scid={scid}",
         "video=true", "audio=false", "control=false",
         "video_codec=h264",
         f"max_size={args.max_size}",
         f"max_fps={args.fps}",
         f"video_bit_rate={args.bit_rate}",
         "tunnel_forward=true",
         "send_frame_meta=false",
         "log_level=info"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0
    )
    stderr_tail = deque(maxlen=50)

    def drain(pipe, label):
        try:
            for line in pipe:
                try:
                    s = line.decode("utf-8", errors="replace").rstrip()
                except Exception:
                    s = repr(line)
                if s:
                    stderr_tail.append(f"{label}: {s}")
        except Exception:
            pass

    Thread(target=drain, args=(server.stdout, "stdout"), daemon=True).start()
    Thread(target=drain, args=(server.stderr, "stderr"), daemon=True).start()

    # Connect
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(10)
    time.sleep(1.5)
    for _ in range(60):
        try:
            sock.connect(("127.0.0.1", local_port))
            break
        except Exception:
            time.sleep(0.2)
    else:
        server.terminate()
        print("Failed to connect to scrcpy socket.", file=sys.stderr)
        return 3

    # Read 69-byte header
    header = b""
    sock.settimeout(5)
    while len(header) < 69:
        chunk = sock.recv(69 - len(header))
        if not chunk:
            print("Socket closed during header.", file=sys.stderr)
            if stderr_tail:
                print("Last scrcpy-server logs:", file=sys.stderr)
                for s in list(stderr_tail)[-10:]:
                    print(s, file=sys.stderr)
            return 4
        header += chunk

    device_name = header[1:65].decode("utf-8", errors="replace").rstrip("\x00")
    codec = header[65:69].decode("ascii", errors="replace")
    print(f"Connected: device={device_name} codec={codec}")

    # Dump raw stream
    t_end = time.time() + args.seconds
    total = 0
    with open(args.out, "wb") as f:
        while time.time() < t_end:
            try:
                data = sock.recv(65536)
                if not data:
                    break
                f.write(data)
                total += len(data)
            except socket.timeout:
                break

    sock.close()
    try:
        server.terminate()
    except Exception:
        pass
    run(["adb", "-s", args.device, "forward", "--remove", f"tcp:{local_port}"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)

    print(f"Wrote {total} bytes to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
