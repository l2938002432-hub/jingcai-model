from __future__ import annotations

import argparse
import json
from pathlib import Path

from jingcai.data_integrity import reconcile_with_schedule
from jingcai.identity import TeamAliases
from jingcai.pipeline import walk_forward_1x2
from jingcai.providers.club_history import load_club_history_csv
from jingcai.providers.openfootball_mls import load_mls_matches


def main() -> int:
    parser = argparse.ArgumentParser(description="Cross-check MLS dates and run a frozen lockbox validation")
    parser.add_argument("history_csv")
    parser.add_argument("reference_dir")
    parser.add_argument("--aliases", default="config/team-aliases.json")
    parser.add_argument("--lockbox", type=int, default=250)
    args = parser.parse_args()

    aliases = TeamAliases(json.loads(Path(args.aliases).read_text(encoding="utf-8")))
    history = list(load_club_history_csv(args.history_csv, divisions={"USA"}, since="2012-01-01"))
    references: list[dict[str, object]] = []
    for path in sorted(Path(args.reference_dir).glob("*_mls.txt")):
        references.extend(load_mls_matches(path, season=path.stem[:4]))
    reconciled = reconcile_with_schedule(history, references, aliases=aliases)
    rows = list(reconciled.corrected)
    if len(rows) <= args.lockbox:
        raise RuntimeError("not enough reconciled matches for requested lockbox")
    result = walk_forward_1x2(rows, min_train=len(rows) - args.lockbox).to_dict()
    result.update(
        history_matches=len(history),
        reference_matches=len(references),
        reconciled_matches=len(rows),
        quarantined_matches=len(reconciled.quarantined),
        log_loss_improvement=(result["baseline_log_loss"] - result["model_log_loss"])
        / result["baseline_log_loss"],
        brier_improvement=(result["baseline_brier"] - result["model_brier"])
        / result["baseline_brier"],
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
