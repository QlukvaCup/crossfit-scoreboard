from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = REPO_ROOT / "docs"


def run(cmd: list[str], cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess:
    workdir = cwd or REPO_ROOT
    print(f"$ {' '.join(cmd)}")
    completed = subprocess.run(
        cmd,
        cwd=workdir,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
    )

    if completed.stdout:
        print(completed.stdout.rstrip())
    if completed.stderr:
        print(completed.stderr.rstrip())

    if check and completed.returncode != 0:
        raise RuntimeError(f"Command failed with exit code {completed.returncode}: {' '.join(cmd)}")

    return completed


def git(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return run(["git", *args], cwd=REPO_ROOT, check=check)


def python_cmd(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return run([sys.executable, *args], cwd=REPO_ROOT, check=check)


def ensure_repo_exists() -> None:
    if not (REPO_ROOT / ".git").exists():
        raise RuntimeError(f"Папка {REPO_ROOT} не является git-репозиторием (.git не найден).")


def ensure_docs_exists() -> None:
    if not DOCS_DIR.exists():
        raise RuntimeError(f"Папка docs не найдена: {DOCS_DIR}")


def ensure_no_in_progress_git_operation(repo_root: Path) -> None:
    git_dir = repo_root / ".git"
    markers = [
        git_dir / "rebase-merge",
        git_dir / "rebase-apply",
        git_dir / "MERGE_HEAD",
        git_dir / "CHERRY_PICK_HEAD",
        git_dir / "REVERT_HEAD",
        git_dir / "BISECT_LOG",
    ]

    found = [p for p in markers if p.exists()]
    if found:
        found_text = "\n".join(f" - {p.relative_to(repo_root)}" for p in found)
        raise RuntimeError(
            "В репозитории обнаружена незавершённая операция Git.\n"
            "Сначала нужно завершить или отменить её вручную.\n\n"
            "Найдено:\n"
            f"{found_text}\n\n"
            "Что обычно помогает:\n"
            " - rebase: git rebase --continue  или  git rebase --abort\n"
            " - merge:  git merge --abort\n"
            " - cherry-pick: git cherry-pick --abort"
        )


def get_status_lines() -> list[str]:
    result = git("status", "--porcelain", check=True)
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    return lines


def split_status_lines(lines: list[str]) -> tuple[list[str], list[str]]:
    docs_changes: list[str] = []
    other_changes: list[str] = []

    for line in lines:
        path_part = line[3:] if len(line) > 3 else line
        normalized = path_part.replace("\\", "/")
        if normalized == "docs" or normalized.startswith("docs/"):
            docs_changes.append(line)
        else:
            other_changes.append(line)

    return docs_changes, other_changes


def ensure_no_non_docs_changes() -> None:
    lines = get_status_lines()
    _, other_changes = split_status_lines(lines)
    if other_changes:
        formatted = "\n".join(f" - {line}" for line in other_changes)
        raise RuntimeError(
            "В репозитории есть незакоммиченные изменения вне папки docs.\n"
            "Публикация остановлена, чтобы не смешивать рабочие правки с publish-коммитом.\n\n"
            "Изменения:\n"
            f"{formatted}\n\n"
            "Сначала закоммить, убери в stash или откати эти файлы."
        )


def has_staged_changes() -> bool:
    result = git("diff", "--cached", "--quiet", check=False)
    return result.returncode != 0


def ensure_remote_exists() -> None:
    result = git("remote", "get-url", "origin", check=False)
    if result.returncode != 0:
        raise RuntimeError(
            "У репозитория не настроен remote 'origin'.\n"
            "Добавь origin перед публикацией."
        )


def build_public() -> None:
    print("=== BUILD ===")
    python_cmd("-m", "publish.build_public")


def stage_docs() -> None:
    print("\n=== GIT ADD ===")
    git("add", "-A", "docs")


def show_status() -> None:
    print("\n=== GIT STATUS ===")
    git("status", "--porcelain")


def commit_docs_if_needed() -> bool:
    print("\n=== STAGED CHECK ===")
    if not has_staged_changes():
        print("Нет изменений в docs — коммит не требуется.")
        return False

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    message = f"Publish results {timestamp}"

    show_status()

    print("\n=== GIT COMMIT ===")
    git("commit", "-m", message)
    return True


def sync_with_remote() -> None:
    print("\n=== REMOTE CHECK ===")
    ensure_remote_exists()
    git("remote", "get-url", "origin")

    print("\n=== GIT PULL ===")
    git("pull", "--rebase", "--autostash", "origin", "main")

    print("\n=== GIT PUSH ===")
    git("push", "origin", "main")


def main() -> None:
    try:
        ensure_repo_exists()
        ensure_docs_exists()
        ensure_no_in_progress_git_operation(REPO_ROOT)

        # До сборки убеждаемся, что вне docs нет грязных файлов
        ensure_no_non_docs_changes()

        build_public()
        stage_docs()
        committed = commit_docs_if_needed()

        if committed:
            sync_with_remote()
            print("\nПубликация завершена")
        else:
            print("\nПубликовать нечего")
    except Exception as exc:
        print(f"\nОШИБКА: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()