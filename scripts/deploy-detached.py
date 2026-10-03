#!/usr/bin/env python3
"""
Detached deploy wrapper for macOS.

为什么需要这个:
  macOS 默认没装 `setsid` (brew install coreutils 才有),也没 `stdbuf`.
  Cursor shell 工具超时后会 SIGKILL 整个 process group, 所以
  `bash scripts/deploy.sh &` / `nohup bash ... &` 都活不过 30s.

修法:
  Python 直接调 POSIX setsid(2) (os.setsid() = Linux setsid 等价物) +
  double-fork 彻底脱离 process group. stdout/stderr 走 line-buffered
  文件,父进程立刻退出留下 detached grandchild.

用法:
  python3 scripts/deploy-detached.py
  python3 scripts/deploy-detached.py --restart
  python3 scripts/deploy-detached.py --action=deploy

环境:
  - 透传给 deploy.sh: SSH_TARGET, PROFILE, SSHPASS, KBKKK_PASS
  - 不在这里读 keychain (避免在 production 启动时卡 IO)

输出:
  第一行 stdout:  PID=<grandchild-pid>
  第二行 stdout: LOG=<log-file-path>
  然后立刻 exit 0. 父进程 (Cursor shell) 拿到 PID+LOG, 可用
  `kill -0 <PID>` 轮询 + `tail -f <LOG>` 看进度.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEPLOY_SH = REPO_ROOT / "scripts" / "deploy.sh"
LOG_DIR = Path("/tmp")
LOG_PREFIX = "deploy-detached"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "deploy_args",
        nargs=argparse.REMAINDER,
        help="Args passed through to deploy.sh (e.g. --restart, --health, --frontend)",
    )
    parser.add_argument(
        "--log-prefix",
        default=LOG_PREFIX,
        help=f"Log file prefix (default: {LOG_PREFIX}, files in {LOG_DIR})",
    )
    args = parser.parse_args()

    # Strip leading "--" that argparse.REMAINDER leaves in place
    passthrough = [a for a in args.deploy_args if a != "--"]

    if not DEPLOY_SH.exists():
        print(f"deploy.sh not found: {DEPLOY_SH}", file=sys.stderr)
        return 2

    # Build log filename with timestamp
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    # Suffix comes from action (deploy/restart/health/...) or generic
    action_suffix = "deploy"
    for a in passthrough:
        if a in ("--restart", "--health", "--logs", "--frontend"):
            action_suffix = a.lstrip("-")
            break
    log_path = LOG_DIR / f"{args.log_prefix}-{action_suffix}-{ts}.log"

    # Use a pipe to pass PID/LOG from child back to parent
    r_fd, w_fd = os.pipe()

    pid = os.fork()
    if pid > 0:
        # Parent: read PID + LOG from pipe, print, exit
        os.close(w_fd)
        with os.fdopen(r_fd, "r") as r:
            data = r.read()
        sys.stdout.write(data)
        sys.stdout.flush()
        return 0

    # Child: become session leader and fork again to fully detach
    os.close(r_fd)
    os.setsid()
    pid2 = os.fork()
    if pid2 > 0:
        # First child: write PID+LOG to pipe and exit (intermediate parent done)
        with os.fdopen(w_fd, "w") as w:
            grandchild = pid2
            w.write(f"PID={grandchild}\n")
            w.write(f"LOG={log_path}\n")
        os._exit(0)

    # Grandchild: the actual deploy worker
    # Open log file for stdout+stderr (line-buffered, append mode)
    # buffering=1 = line buffered for text mode
    log_fp = open(log_path, "w", buffering=1)
    os.dup2(log_fp.fileno(), 1)  # stdout
    os.dup2(log_fp.fileno(), 2)  # stderr
    os.dup2(os.open("/dev/null", os.O_RDONLY), 0)  # stdin

    # Build env: inherit parent env, but force unbuffered Python output (defensive)
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"

    # Exec deploy.sh with passthrough args
    cmd = ["bash", str(DEPLOY_SH), *passthrough]
    try:
        os.execvpe(cmd[0], cmd, env)
    except FileNotFoundError:
        # If exec fails, log and exit
        print(f"FATAL: cannot exec {cmd}", flush=True)
        os._exit(127)


if __name__ == "__main__":
    sys.exit(main())
