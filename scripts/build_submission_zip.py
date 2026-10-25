"""Create a clean course submission archive without credentials or private inputs."""
from __future__ import annotations

from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output" / "ZentroMart_Capstone_Submission.zip"
INCLUDE = [
    ".env.example", ".gitignore", "README.md", "requirements.txt", "requirements-report.txt",
    "app.py", "run.py", "check_groq.py", "evaluate.py", "evaluate_answers.py",
    "evaluate_conversations.py", "score_answer_comparison.py",
    "src/__init__.py", "src/agent.py", "src/conversation.py", "src/evaluation.py", "src/knowledge.py",
    "scripts/prepare_dataset.py", "scripts/build_report.py", "scripts/build_submission_zip.py",
    "docs/CASE_BRIEF_NOTES.md", "docs/PROJECT_PLAN.md", "docs/SUBMISSION_CHECKLIST.md", "docs/DEMO_RECORDING_SCRIPT.md",
    "data/raw/.gitkeep", "output/pdf/ZentroMart_Capstone_Report.pdf",
    "sample_outputs/upiRefund.json", "sample_outputs/batch_manifest.json", "sample_outputs/upiRefund_reply.wav",
]
FORBIDDEN_PARTS = {".venv", "data/source", "voice_inputs", "reports/drafts", "__pycache__"}
FORBIDDEN_NAMES = {".env", "tickets_created.csv", "upiRefund.m4a"}


def main() -> None:
    missing = [name for name in INCLUDE if not (ROOT / name).is_file()]
    if missing:
        raise SystemExit("Missing required package files: " + ", ".join(missing))
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(OUTPUT, "w", compression=ZIP_DEFLATED, compresslevel=8) as archive:
        for name in INCLUDE:
            path = Path(name)
            normalized = path.as_posix()
            if any(part in normalized for part in FORBIDDEN_PARTS) or path.name in FORBIDDEN_NAMES:
                raise SystemExit(f"Refusing to package a private or excluded path: {name}")
            archive.write(ROOT / path, arcname=normalized)
    with ZipFile(OUTPUT) as archive:
        bad_member = archive.testzip()
        if bad_member:
            raise SystemExit(f"Archive verification failed at: {bad_member}")
        names = set(archive.namelist())
        if any(Path(name).name == ".env" for name in names):
            raise SystemExit("Refusing to include a .env file")
        print(f"Created and verified {OUTPUT}")
        print(f"Included {len(names)} files; course dataset and input recordings are excluded.")


if __name__ == "__main__":
    main()

