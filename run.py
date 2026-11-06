"""Commands for replaying predictions and explicitly refreshing evidence."""

import argparse
import importlib
import subprocess
import sys
from pathlib import Path

from src.data import ROOT

COLLECTORS = {
    "director-roles": "fetch_director_roles",
    "board-facts": "fetch_board_facts",
    "position-papers": "fetch_position_papers",
}


def predict(output_dir: Path) -> None:
    from src.outputs import write_outputs
    from src.pipeline import general_decisions

    general = general_decisions()
    write_outputs(general, output_dir)


def main() -> None:
    parser = argparse.ArgumentParser(description="NBIM voting decision support")
    commands = parser.add_subparsers(dest="command", required=True)
    prediction = commands.add_parser("predict", help="Replay saved inputs without network access")
    prediction.add_argument("--output-dir", type=Path, default=Path(ROOT) / "data/outputs")
    commands.add_parser("dashboard", help="Open the Norwegian Streamlit dashboard")
    refresh = commands.add_parser(
        "refresh", help="Refresh one source; may contact SEC or hosted models"
    )
    refresh.add_argument(
        "target", choices=sorted([*COLLECTORS, "guidelines", "rule-checks", "judge"])
    )
    refresh.add_argument(
        "arguments", nargs=argparse.REMAINDER, help="Collector options, such as --limit 8"
    )
    args = parser.parse_args()
    if args.command == "predict":
        predict(args.output_dir)
    elif args.command == "dashboard":
        script = Path(ROOT) / "src" / "dashboard.py"
        raise SystemExit(
            subprocess.call([sys.executable, "-m", "streamlit", "run", str(script)], cwd=ROOT)
        )
    else:
        refresh_source(args.target, args.arguments)


def refresh_source(target: str, arguments: list[str]) -> None:
    if target in COLLECTORS:
        # Retain the collectors' existing limit options and parsing.
        module = importlib.import_module("src.evidence." + COLLECTORS[target])
        previous = sys.argv
        try:
            sys.argv = [target, *arguments]
            module.main()
        finally:
            sys.argv = previous
        return
    parser = argparse.ArgumentParser(prog="refresh " + target)
    if target == "judge":
        parser.add_argument("--through-year", type=int, default=2026)
    options = parser.parse_args(arguments)
    if target == "guidelines":
        from src.evidence.policy import refresh

        refresh()
    elif target == "judge":
        from src.evidence.judge import fill

        fill(options.through_year)
    else:
        from src.evidence import rule_check as rc
        from src.models.history import read_votes

        rows = read_votes(rc.VOTES)
        sections = rc.load_guidelines()
        candidates = rc.candidate_sections(rows, sections)
        rc.fill_cache(
            [
                rc.build_request(r, candidates[r["proposal_type"]], sections)
                for r in rows
                if r["meeting_date"][:4] in {"2025", "2026"}
            ],
            rc.load_cache(),
        )


if __name__ == "__main__":
    main()
