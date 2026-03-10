from __future__ import annotations

import subprocess
import sys
from datetime import datetime
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]


def safe_print(text: str) -> None:
    if not text:
        return
    try:
        print(text, end="")
    except UnicodeEncodeError:
        enc = sys.stdout.encoding or "cp1251"
        print(text.encode(enc, errors="replace").decode(enc, errors="replace"), end="")


def run(cmd: list[str], cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess:
    cwd = cwd or ROOT_DIR
    print(f"$ {' '.join(str(x) for x in cmd)}")

    proc = subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    if proc.stdout:
        safe_print(proc.stdout)

    if proc.stderr:
        safe_print(proc.stderr)

    if check and proc.returncode != 0:
        raise RuntimeError(
            f"Command failed with code {proc.returncode}: {' '.join(str(x) for x in cmd)}"
        )

    return proc


def main() -> None:
    git = r"C:\Program Files\Git\cmd\git.EXE"

    print("=== BUILD ===")
    run([sys.executable, "-m", "publish.build_public"])

    print("=== GIT ADD ===")
    run([git, "add", "-A", "docs"])

    print("=== STAGED CHECK ===")
    staged = run([git, "diff", "--cached", "--quiet"], check=False)

    print("=== GIT STATUS ===")
    run([git, "status", "--porcelain"])

    if staged.returncode == 1:
        print("=== GIT COMMIT ===")
        msg = f"Publish results {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        run([git, "commit", "-m", msg])
    else:
        print("=== GIT COMMIT ===")
        print("No staged docs changes to commit.")

    print("=== REMOTE CHECK ===")
    run([git, "remote", "get-url", "origin"])

    print("=== GIT PUSH ===")
    run([git, "push", "origin", "main"])


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\nERROR: {e}")
        raise