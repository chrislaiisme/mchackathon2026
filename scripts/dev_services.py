#!/usr/bin/env python3
"""跨平台一鍵啟動／關閉／重啟 demo 服務的工具。

為什麼要有這支腳本：`scripts/start-demo.ps1` 已經做得很完整（port 重用、健康檢查、
log 導檔），但只有 Windows 上的 PowerShell 能跑；團隊裡有非 Windows 的組員，需要一支
任何 OS 都能跑的等效工具。這支刻意只用 Python 標準庫（subprocess／socket／argparse／
json／pathlib／urllib），不额外要求 psutil 之類的第三方套件——這樣沒特別裝過套件的
機器也能直接執行，不會卡在「先幫我裝一個套件」這一步。

跟 start-demo.ps1 的關係：兩支腳本功能對等、並存，不是取代關係——習慣 PowerShell 的
Windows 隊友可以繼續用 start-demo.ps1，其他 OS 的隊友用這支。細節見根目錄
README.md「Running the services」一節。

用法：
    python scripts/dev_services.py start                 # 啟動全部 6 個服務
    python scripts/dev_services.py start engine01 engine02 # 只啟動指定的幾個
    python scripts/dev_services.py status                 # 列出每個服務目前狀態
    python scripts/dev_services.py stop frontend           # 關掉單一服務
    python scripts/dev_services.py restart engine01 --env CORS_ALLOWED_ORIGINS=https://xxx.trycloudflare.com,http://localhost:3000
                                                            # 重啟並覆蓋一個環境變數
                                                            # （Cloudflare Quick Tunnel 流程會用到，見 docs/remote-demo-tunnel.md）
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable, Optional

# repo 根目錄：這支檔案在 scripts/ 底下，往上一層就是根目錄——跟 start-demo.ps1
# 用 Split-Path -Parent $PSScriptRoot 是同一個邏輯。
ROOT = Path(__file__).resolve().parents[1]
LOGS_DIR = ROOT / "data" / "runtime" / "logs"
PIDS_FILE = ROOT / "data" / "runtime" / "pids.json"
IS_WINDOWS = platform.system() == "Windows"


def _venv_python(venv_dirname: str) -> Path:
    """算出某個 venv 資料夾底下的 python 執行檔路徑——Windows 跟 POSIX 的
    venv 內部佈局不一樣（Scripts/python.exe vs bin/python），這裡統一處理，
    呼叫端不用自己判斷 OS。"""
    venv_dir = ROOT / venv_dirname
    if IS_WINDOWS:
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def _find_npm() -> str:
    """找系統上的 npm 執行檔。Windows 上 npm 實際是 npm.cmd，shutil.which("npm")
    在大多數環境也找得到（Windows 的 PATHEXT 機制），但為了保險兩個都試一次。

    找不到時刻意不在這裡就丟例外——這支函式在組所有服務的規格表時都會被呼叫
    一次（就算這次只是要 start/stop/status 別的服務），沒裝 Node.js 的機器
    不應該連查詢 ENGINE01 的狀態都做不到。真的要啟動 frontend、npm 路徑卻是
    空字串時，Popen 自然會丟出清楚的 FileNotFoundError，不需要在這裡先擋。
    """
    candidates = ["npm.cmd", "npm"] if IS_WINDOWS else ["npm"]
    for candidate in candidates:
        found = shutil.which(candidate)
        if found:
            return found
    return "npm"


# 每個服務的定義：port、健康檢查網址、怎麼組出啟動指令、額外的預設環境變數。
# 這份清單刻意跟 start-demo.ps1 的 $services 一一對應，兩邊要同時維護，
# 不要只改一邊——這是兩支腳本並存要付出的代價，換取跨平台可用性。
def _build_service_specs() -> dict[str, dict]:
    engine01_python = _venv_python(".venv")
    engine02_python = _venv_python(".venv-engine02")
    return {
        "engine02": {
            "port": 8002,
            "health_url": "http://127.0.0.1:8002/health",
            "cwd": ROOT,
            "command": [
                str(engine02_python), "-m", "uvicorn", "mcp_servers.catalog.main:app",
                "--host", "127.0.0.1", "--port", "8002",
            ],
            # 這幾個變數一律用服務自己的預設值覆蓋、不繼承呼叫端 shell 裡的舊值——
            # 跟 start-demo.ps1 同樣的理由：舊 shell 殘留的 ENGINE02_REWRITER=none
            # 這種值很難察覺，卻會讓推薦理由悄悄退化成樣板句。
            "default_env": {
                "ENGINE02_CATALOG": "data/catalog/hm_filled",
                "ENGINE02_DEMO": "1",
                "ENGINE02_PUBLIC_BASE": "http://127.0.0.1:8002/engine02",
                "ENGINE02_REWRITER": "codex",
                "ENGINE02_CODEX_EFFORT": "low",
            },
        },
        "engine01": {
            "port": 8000,
            "health_url": "http://127.0.0.1:8000/health",
            "cwd": ROOT,
            "command": [
                str(engine01_python), "-m", "uvicorn", "backend.engine01_intent.main:app",
                "--host", "127.0.0.1", "--port", "8000",
            ],
            "default_env": {},
        },
        "engine03": {
            "port": 8003,
            "health_url": "http://127.0.0.1:8003/health",
            "cwd": ROOT,
            "command": [
                str(engine01_python), "-m", "uvicorn", "backend.engine03_feedback.main:app",
                "--host", "127.0.0.1", "--port", "8003",
            ],
            "default_env": {},
        },
        "whisper": {
            "port": 9000,
            "health_url": "http://127.0.0.1:9000/health",
            "cwd": ROOT,
            "command": [
                str(engine01_python), "-m", "uvicorn", "backend.whisper_transcription.main:app",
                "--host", "127.0.0.1", "--port", "9000",
            ],
            "default_env": {},
        },
        "virtual-you": {
            "port": 8081,
            "health_url": "http://127.0.0.1:8081/healthz",
            "cwd": ROOT,
            "command": [
                str(engine01_python), "-m", "uvicorn", "backend.virtual_you.main:app",
                "--host", "127.0.0.1", "--port", "8081",
            ],
            "default_env": {"VIRTUAL_TRY_ON_PROVIDER": "codex"},
        },
        "frontend": {
            "port": 3000,
            "health_url": "http://127.0.0.1:3000",
            "cwd": ROOT / "frontend",
            "command": [_find_npm(), "run", "dev", "--", "--hostname", "127.0.0.1", "--port", "3000"],
            "default_env": {},
        },
    }


def _parse_dotenv(path: Path) -> dict[str, str]:
    """極簡的 .env 解析器——只認得 KEY=VALUE，忽略空行／# 開頭的註解，去掉包住
    值的一組引號。不用 python-dotenv 套件，理由跟檔案開頭一樣：不想讓這支
    工具本身也要求額外依賴。"""
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        match = re.match(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$", line)
        if not match or line.strip().startswith("#"):
            continue
        key, value = match.group(1), match.group(2)
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key] = value
    return values


def _build_env(default_env: dict[str, str], cli_overrides: dict[str, str]) -> dict[str, str]:
    """組出要傳給子行程的環境變數，優先順序（高蓋低）：
    1. --env 命令列覆蓋（使用者這次明確要的，例如 Cloudflare Tunnel 流程要換 CORS）
    2. 服務自己的預設值（避免吃到舊 shell 殘留的值）
    3. 呼叫這支腳本當下、繼承自 shell 的環境變數
    4. repo 根目錄的 .env 檔（只補目前還沒有值的 key）
    這個順序跟 start-demo.ps1 的邏輯對齊，差別只在這裡额外加了 --env 這一層。"""
    env = dict(os.environ)
    for key, value in _parse_dotenv(ROOT / ".env").items():
        env.setdefault(key, value)
    env.update(default_env)
    env.update(cli_overrides)
    return env


def _port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    """用最陽春的 TCP 連線測試判斷 port 有沒有人在監聽——跨平台，不需要
    netstat／lsof 這類外部指令，純標準庫就能做。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host, port)) == 0


def _check_health(url: str) -> bool:
    """打健康檢查網址，2xx/3xx 視為活著。frontend 首頁沒有 /health，直接
    GET 根路徑，Next.js dev server activated 之後一定會回一個 HTML 頁面。"""
    try:
        with urllib.request.urlopen(url, timeout=2) as response:
            return 200 <= response.status < 400
    except (urllib.error.URLError, OSError, ValueError):
        return False


def _read_pids() -> dict[str, dict]:
    if not PIDS_FILE.is_file():
        return {}
    try:
        return json.loads(PIDS_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _write_pids(data: dict[str, dict]) -> None:
    PIDS_FILE.parent.mkdir(parents=True, exist_ok=True)
    PIDS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _pid_alive(pid: int) -> bool:
    """檢查一個 PID 是不是還活著——POSIX 用 signal 0（不會真的送信號，只檢查
    行程存不存在／有沒有權限）；Windows 沒有這個機制，改用 tasklist 查詢。"""
    if IS_WINDOWS:
        result = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}"], capture_output=True, text=True,
        )
        return str(pid) in result.stdout
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


def _kill_pid(pid: int) -> None:
    """關掉一個行程。Windows 用 taskkill /F 連子行程（uvicorn/npm 常常會再
    衍生子行程，/T 一併關掉整棵樹）；POSIX 先送 SIGTERM 讓它優雅關閉，
    等一下還活著才升級成 SIGKILL。"""
    if IS_WINDOWS:
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(pid)],
            capture_output=True, text=True,
        )
        return
    try:
        os.kill(pid, signal.SIGTERM)
        for _ in range(10):
            if not _pid_alive(pid):
                return
            time.sleep(0.3)
        os.kill(pid, signal.SIGKILL)
    except (OSError, ProcessLookupError):
        pass


def _find_pid_by_port(port: int) -> Optional[int]:
    """`pids.json` 裡沒有記錄時的備用手段：反查目前是哪個 PID 在監聽這個 port。
    只呼叫作業系統內建指令（netstat／lsof），不额外要求安裝任何東西；
    lsof 在部分精簡版 Linux 上可能沒裝，找不到就放棄、請使用者自己處理，
    不硬猜其他工具。"""
    if IS_WINDOWS:
        result = subprocess.run(["netstat", "-ano"], capture_output=True, text=True)
        for line in result.stdout.splitlines():
            parts = line.split()
            if len(parts) >= 5 and parts[0] == "TCP" and parts[1].endswith(f":{port}") and parts[3] == "LISTENING":
                try:
                    return int(parts[-1])
                except ValueError:
                    continue
        return None
    try:
        result = subprocess.run(
            ["lsof", "-i", f":{port}", "-sTCP:LISTEN", "-t"],
            capture_output=True, text=True,
        )
    except FileNotFoundError:
        return None
    pids = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    return int(pids[0]) if pids else None


def cmd_start(names: list[str], specs: dict[str, dict], cli_overrides: dict[str, str]) -> None:
    pids = _read_pids()
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    for name in names:
        spec = specs[name]
        if _port_in_use(spec["port"]):
            print(f"[{name}] port {spec['port']} 已經有人在監聽，視為重用，不重複啟動。")
            continue

        env = _build_env(spec["default_env"], cli_overrides)
        safe_name = re.sub(r"[^A-Za-z0-9_-]", "-", name)
        stdout_path = LOGS_DIR / f"{safe_name}-{spec['port']}.stdout.log"
        stderr_path = LOGS_DIR / f"{safe_name}-{spec['port']}.stderr.log"
        stdout_file = open(stdout_path, "ab")
        stderr_file = open(stderr_path, "ab")

        # POSIX 上用 start_new_session 讓子行程脫離目前的 session，這樣關掉
        # 啟動這支腳本的終端機不會連帶把服務也砍掉；Windows 預設行為本來
        # 就不會因為父行程結束而砍子行程，不需要额外旗標。
        popen_kwargs: dict = {}
        if not IS_WINDOWS:
            popen_kwargs["start_new_session"] = True

        process = subprocess.Popen(
            spec["command"], cwd=str(spec["cwd"]), env=env,
            stdout=stdout_file, stderr=stderr_file, **popen_kwargs,
        )
        pids[name] = {"pid": process.pid, "port": spec["port"]}
        print(f"[{name}] 已啟動（PID {process.pid}，port {spec['port']}），log 在 {stdout_path}")

    _write_pids(pids)

    print("\n等待健康檢查（最多 45 秒）...")
    deadline = time.time() + 45
    remaining = set(names)
    while remaining and time.time() < deadline:
        for name in list(remaining):
            if _check_health(specs[name]["health_url"]):
                print(f"[{name}] 健康檢查通過")
                remaining.discard(name)
        if remaining:
            time.sleep(1)
    for name in remaining:
        print(f"[{name}] 還沒回應健康檢查，可能還在啟動中，請看 log：{LOGS_DIR}")


def cmd_stop(names: list[str], specs: dict[str, dict]) -> None:
    pids = _read_pids()
    for name in names:
        spec = specs[name]
        recorded = pids.get(name)
        pid = recorded["pid"] if recorded and _pid_alive(recorded["pid"]) else None
        if pid is None and _port_in_use(spec["port"]):
            pid = _find_pid_by_port(spec["port"])
        if pid is None:
            print(f"[{name}] 沒有找到在跑的行程（port {spec['port']} 目前沒人監聽）。")
            pids.pop(name, None)
            continue
        _kill_pid(pid)
        print(f"[{name}] 已關閉（PID {pid}）。")
        pids.pop(name, None)
    _write_pids(pids)


def cmd_restart(names: list[str], specs: dict[str, dict], cli_overrides: dict[str, str]) -> None:
    cmd_stop(names, specs)
    # 關閉後 port 不會馬上釋放（TIME_WAIT），稍微等一下再重新探測，
    # 避免誤判成「還在跑」而跳過啟動。
    for name in names:
        deadline = time.time() + 10
        while _port_in_use(specs[name]["port"]) and time.time() < deadline:
            time.sleep(0.5)
    cmd_start(names, specs, cli_overrides)


def cmd_status(names: list[str], specs: dict[str, dict]) -> None:
    print(f"{'服務':<14}{'Port':<8}{'監聽中':<10}{'健康檢查':<10}")
    for name in names:
        spec = specs[name]
        listening = _port_in_use(spec["port"])
        healthy = _check_health(spec["health_url"]) if listening else False
        print(
            f"{name:<14}{spec['port']:<8}"
            f"{('是' if listening else '否'):<10}{('通過' if healthy else '未通過'):<10}"
        )


def _parse_env_overrides(pairs: list[str]) -> dict[str, str]:
    overrides = {}
    for pair in pairs:
        if "=" not in pair:
            raise SystemExit(f"--env 參數格式錯誤，要是 KEY=VALUE，收到：{pair!r}")
        key, value = pair.split("=", 1)
        overrides[key] = value
    return overrides


def main() -> None:
    # Windows 終端機預設編碼常常是 cp950（繁體中文）而不是 UTF-8，直接 print()
    # 中文字會變亂碼——跟這個專案先前在 subprocess.run(text=True) 踩過的
    # cp950 編碼坑是同一個根因，這裡用同樣的思路顯式修正輸出編碼。
    # reconfigure() 是 Python 3.7+ 才有，用 getattr 保護一下避免舊版直接炸掉。
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")

    specs = _build_service_specs()
    all_names = list(specs.keys())

    parser = argparse.ArgumentParser(
        description="跨平台一鍵啟動／關閉／重啟 demo 服務（等效於 scripts/start-demo.ps1）。",
    )
    subparsers = parser.add_subparsers(dest="action", required=True)

    # 注意：nargs="*" 的 positional 如果同時設 choices 又設一個非空 list 當
    # default，在沒有任何命令列參數時，argparse 會把整個 default list
    # 錯誤地當成單一字串去跟 choices 比對，直接炸 "invalid choice"——
    # 這是實測踩到的 argparse 行為，不是憑空猜測。繞過方式：這裡不設 default
    # （nargs="*" 沒給值時自然是 []），「沒指定＝全部服務」的邏輯留到
    # main() 解析完之後自己判斷 `if args.services else all_names`。
    for action_name in ("start", "restart"):
        sub = subparsers.add_parser(action_name)
        sub.add_argument("services", nargs="*", choices=all_names,
                          metavar="service", help=f"要處理的服務名稱（不指定＝全部）：{', '.join(all_names)}")
        sub.add_argument("--env", action="append", default=[], metavar="KEY=VALUE",
                          help="覆蓋一個環境變數，可重複使用；優先度最高，會蓋過服務自己的預設值")

    sub_stop = subparsers.add_parser("stop")
    sub_stop.add_argument("services", nargs="*", choices=all_names,
                           metavar="service", help=f"要關閉的服務名稱（不指定＝全部）：{', '.join(all_names)}")

    sub_status = subparsers.add_parser("status")
    sub_status.add_argument("services", nargs="*", choices=all_names,
                             metavar="service", help=f"要查詢的服務名稱（不指定＝全部）：{', '.join(all_names)}")

    args = parser.parse_args()
    names = args.services if args.services else all_names

    if args.action == "start":
        cmd_start(names, specs, _parse_env_overrides(args.env))
    elif args.action == "stop":
        cmd_stop(names, specs)
    elif args.action == "restart":
        cmd_restart(names, specs, _parse_env_overrides(args.env))
    elif args.action == "status":
        cmd_status(names, specs)


if __name__ == "__main__":
    main()
