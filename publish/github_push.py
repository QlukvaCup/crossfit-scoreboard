from __future__ import annotations

import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def run(cmd: list[str], *, check: bool = True, capture: bool = False) -> subprocess.CompletedProcess[str]:
    print("$", " ".join(cmd))
    return subprocess.run(
        cmd,
        cwd=REPO_ROOT,
        check=check,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=capture,
    )


def ensure_clean_git_state(repo_root: Path) -> None:
    git_dir = repo_root / ".git"
    blockers = [
        git_dir / "rebase-merge",
        git_dir / "rebase-apply",
        git_dir / "MERGE_HEAD",
        git_dir / "CHERRY_PICK_HEAD",
        git_dir / "REVERT_HEAD",
    ]
    present = [str(p.relative_to(repo_root)) for p in blockers if p.exists()]
    if present:
        raise RuntimeError(
            "В репозитории обнаружен незавершённый merge/rebase. "
            "Сначала заверши или отмени его вручную, потом повтори публикацию. "
            f"Найдены признаки: {', '.join(present)}"
        )



def main() -> None:
    git = shutil.which("git") or r"C:\Program Files\Git\cmd\git.EXE"
    python = sys.executable

    if not Path(git).exists() and shutil.which("git") is None:
        raise RuntimeError("Git не найден в PATH")

    ensure_clean_git_state(REPO_ROOT)

    print("=== BUILD ===")
    run([python, "-m", "publish.build_public"])

    print("\n=== GIT ADD ===")
    run([git, "add", "-A", "docs"])

    print("\n=== STAGED CHECK ===")
    staged = subprocess.run(
        [git, "diff", "--cached", "--quiet"],
        cwd=REPO_ROOT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if staged.returncode == 0:
        print("Нет изменений в docs для публикации")
        return

    print("\n=== GIT STATUS ===")
    status = run([git, "status", "--porcelain"], capture=True)
    if status.stdout:
        print(status.stdout)

    print("\n=== GIT COMMIT ===")
    msg = f"Publish results {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    run([git, "commit", "-m", msg])

    print("\n=== REMOTE CHECK ===")
    remote = run([git, "remote", "get-url", "origin"], capture=True)
    if remote.stdout:
        print(remote.stdout.strip())

    print("\n=== FETCH ===")
    run([git, "fetch", "origin"])

    print("\n=== AHEAD/BEHIND CHECK ===")
    counts = run([git, "rev-list", "--left-right", "--count", "main...origin/main"], capture=True)
    text = counts.stdout.strip()
    print(text)
    parts = text.split()
    local_only = int(parts[0]) if len(parts) == 2 and parts[0].isdigit() else 0
    remote_only = int(parts[1]) if len(parts) == 2 and parts[1].isdigit() else 0

    if remote_only > 0:
        raise RuntimeError(
            "Удалённая ветка origin/main содержит более новые коммиты. "
            "Сначала синхронизируй репозиторий вручную, затем повтори публикацию."
        )

    print("\n=== GIT PUSH ===")
    run([git, "push", "origin", "main"])

    print("\nПубликация завершена")


if __name__ == "__main__":
    main()
