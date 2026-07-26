from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from typing import Any, Iterable, Mapping

from jingcai.identity import TeamAliases
from jingcai.pipeline import build_paper_candidates


class DailyLiveError(RuntimeError):
    """Raised when a live report cannot be produced safely."""


def parse_official_update(payload: Mapping[str, Any]) -> datetime:
    value = payload.get("value")
    raw = value.get("lastUpdateTime") if isinstance(value, Mapping) else None
    if not isinstance(raw, str) or not raw.strip():
        raise DailyLiveError("官方数据缺少 lastUpdateTime，无法判断新鲜度")
    try:
        parsed = datetime.fromisoformat(raw.strip())
    except ValueError as exc:
        raise DailyLiveError(f"官方更新时间格式无法识别: {raw!r}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone(timedelta(hours=8)))
    return parsed.astimezone(UTC)


def validate_freshness(
    source_as_of: datetime, *, now: datetime | None = None,
    max_age: timedelta = timedelta(minutes=30),
) -> None:
    current = now or datetime.now(UTC)
    if current.tzinfo is None or source_as_of.tzinfo is None:
        raise DailyLiveError("新鲜度校验必须使用带时区的时间")
    age = current - source_as_of
    if age < -timedelta(minutes=2):
        raise DailyLiveError("官方更新时间晚于本机时间，请检查系统时钟")
    if age > max_age:
        raise DailyLiveError(
            f"官方奖金数据已过期（{age.total_seconds() / 60:.0f} 分钟，"
            f"限制 {max_age.total_seconds() / 60:.0f} 分钟）"
        )


def canonicalize_teams(
    history: Iterable[Mapping[str, Any]], fixtures: Iterable[Mapping[str, Any]],
    aliases: Mapping[str, Iterable[str]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    resolver = TeamAliases(aliases)
    history_rows = [dict(row) for row in history]
    fixture_rows = [dict(row) for row in fixtures]
    for rows in (history_rows, fixture_rows):
        for row in rows:
            row.setdefault("display_home_team", str(row["home_team"]))
            row.setdefault("display_away_team", str(row["away_team"]))
            row["home_team"] = resolver.canonical(str(row["home_team"]))
            row["away_team"] = resolver.canonical(str(row["away_team"]))
    return history_rows, fixture_rows


def unknown_fixture_teams(
    history: Iterable[Mapping[str, Any]], fixtures: Iterable[Mapping[str, Any]]
) -> list[str]:
    trained = {str(row[field]) for row in history for field in ("home_team", "away_team")}
    return sorted({
        str(fixture[field]) for fixture in fixtures for field in ("home_team", "away_team")
        if str(fixture[field]) not in trained
    })


def build_live_candidates(
    history: Iterable[Mapping[str, Any]], fixtures: Iterable[Mapping[str, Any]], *,
    source_as_of: datetime, now: datetime | None = None,
    max_age_minutes: int = 30, safety_margin: float = 0.03,
) -> list[dict[str, Any]]:
    rows, fixture_rows = list(history), list(fixtures)
    current = now or datetime.now(UTC)
    validate_freshness(source_as_of, now=current, max_age=timedelta(minutes=max_age_minutes))
    if not fixture_rows:
        raise DailyLiveError("官方数据中没有正在销售的比赛")
    trained = {str(row[field]) for row in rows for field in ("home_team", "away_team")}
    supported = [
        row for row in fixture_rows
        if str(row["home_team"]) in trained and str(row["away_team"]) in trained
    ]
    if not supported:
        raise DailyLiveError("当天比赛均缺少可信历史训练覆盖")
    return build_paper_candidates(
        rows, supported, safety_margin=safety_margin, prediction_time=current
    )
