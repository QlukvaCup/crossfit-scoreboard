import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
import shutil

from publish.build_public import build_all


def find_git_exe():
    git = shutil.which("git")
    if git:
        return git
    candidates = [
        r"C:\Program Files\Git\cmd\git.exe",
        r"C:\Program Files\Git\bin\git.exe",
        r"C:\Program Files (x86)\Git\cmd\git.exe",
        r"C:\Program Files (x86)\Git\bin\git.exe",
    ]
    for c in candidates:
        if Path(c).exists():
            return c
    raise RuntimeError("Git не найден. Установи Git for Windows.")


def run(cmd, check=True):
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    print(f"$ {' '.join(str(x) for x in cmd)}")
    if proc.stdout.strip():
        print(proc.stdout.strip())
    if proc.stderr.strip():
        print(proc.stderr.strip())
    if check and proc.returncode != 0:
        raise RuntimeError(f"Команда завершилась с кодом {proc.returncode}: {' '.join(str(x) for x in cmd)}")
    return proc


def main():
    git = find_git_exe()
    print("=== BUILD ===")
    build_all()

    print("=== GIT ADD ===")
    run([git, "add", "docs/results.json", "docs/flags", "docs/index.html", "docs/mobile.html"])

    print("=== GIT STATUS ===")
    status = run([git, "status", "--porcelain"], check=False)
    has_changes = bool(status.stdout.strip())

    if has_changes:
        msg = f"Publish results {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        print("=== GIT COMMIT ===")
        run([git, "commit", "-m", msg])
    else:
        print("Изменений для commit нет. Пропускаю commit.")

    print("=== REMOTE CHECK ===")
    remote = run([git, "remote", "get-url", "origin"], check=False)
    if remote.returncode != 0:
        raise RuntimeError(
            "Remote origin не настроен.\n"
            "Выполни в PowerShell:\n"
            "git remote add origin https://github.com/GabuIgor/crossfit-scoreboard.git\n"
            "git push -u origin main"
        )

    print("=== GIT PUSH ===")
    last_error = None
    for attempt in range(1, 3):
        try:
            run([git, "push"])
            print("✅ Publish OK")
            return
        except Exception as e:
            last_error = e
            print(f"Push attempt {attempt} failed: {e}")
            if attempt < 2:
                time.sleep(2)
    raise last_error


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n❌ {e}")
        sys.exit(1)
