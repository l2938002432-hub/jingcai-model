"""Run a no-storage connectivity probe suitable for a Gitee Go trial."""

from __future__ import annotations

import json

from jingcai.connectivity_probe import probe


def main() -> int:
    exit_code, result = probe()
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
