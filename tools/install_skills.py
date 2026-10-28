"""Install the repository's shared skills for Codex and Claude Code."""

import argparse
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
DESTINATIONS = {"codex": ".agents/skills", "claude": ".claude/skills"}


def install_skills(project, agent="both"):
    project = Path(project).resolve()
    if not project.is_dir():
        raise ValueError("Project directory does not exist: " + str(project))
    skills = sorted(
        path
        for path in (ROOT / "skills").iterdir()
        if path.is_dir() and (path / "SKILL.md").is_file()
    )
    if not skills:
        raise ValueError("No skill packages found in " + str(ROOT / "skills"))
    agents = list(DESTINATIONS) if agent == "both" else [agent]
    targets = []
    for name in agents:
        for skill in skills:
            target = project / DESTINATIONS[name] / skill.name
            if not target.resolve().is_relative_to(project):
                raise ValueError(
                    "Skill destination resolves outside the project: " + str(target)
                )
            if target.is_symlink():
                raise ValueError("Skill destination is a symlink: " + str(target))
            targets.append((skill, target))
    for source, target in targets:
        shutil.copytree(
            source,
            target,
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
        print("Installed {0}: {1}".format(source.name, target))
    return [target for _, target in targets]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--project",
        type=Path,
        default=ROOT,
        help="target project (default: this checkout)",
    )
    parser.add_argument("--agent", choices=("both", "codex", "claude"), default="both")
    args = parser.parse_args()
    try:
        install_skills(args.project, args.agent)
    except (OSError, ValueError) as error:
        print("install-skills: " + str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
