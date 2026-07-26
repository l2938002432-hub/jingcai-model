"""Replay frozen model and local personal tickets against versioned results."""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable, Mapping

from jingcai.domain import (
    Market,
    MatchResult,
    ResultStatus,
    Selection,
    SettlementStatus,
    Ticket,
)
from jingcai.ledger import (
    Ledger,
    LedgerEvent,
    LedgerEventType,
    LedgerKind,
    deterministic_event_id,
)
from jingcai.settlement import settle_ticket


def _canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True)
class ResultRevision:
    match_id: str
    revision: str
    source: str
    source_as_of: datetime
    status: ResultStatus
    home_score: int | None = None
    away_score: int | None = None
    half_home_score: int | None = None
    half_away_score: int | None = None

    def to_record(self) -> dict[str, Any]:
        if self.source_as_of.tzinfo is None or self.source_as_of.utcoffset() is None:
            raise ValueError("result source_as_of must be timezone-aware")
        if not self.match_id or not self.revision or not self.source:
            raise ValueError("result identifiers and source are required")
        result = MatchResult(
            self.match_id, self.status, self.home_score, self.away_score,
            self.half_home_score, self.half_away_score,
        )
        return {
            "match_id": result.match_id,
            "revision": self.revision,
            "source": self.source,
            "source_as_of": self.source_as_of.isoformat(),
            "status": result.status.value,
            "home_score": result.home_score,
            "away_score": result.away_score,
            "half_home_score": result.half_home_score,
            "half_away_score": result.half_away_score,
        }


@dataclass(frozen=True)
class ReplaySummary:
    ledger_kind: LedgerKind
    settled: int
    reversed: int
    pending: tuple[str, ...]
    conflicts: tuple[str, ...]


def parse_result_revisions(rows: Iterable[Mapping[str, Any]]) -> list[ResultRevision]:
    revisions = []
    for row in rows:
        source_as_of = datetime.fromisoformat(str(row["source_as_of"]))
        revisions.append(ResultRevision(
            match_id=str(row["match_id"]),
            revision=str(row["revision"]),
            source=str(row["source"]),
            source_as_of=source_as_of,
            status=ResultStatus(str(row["status"])),
            home_score=row.get("home_score"),
            away_score=row.get("away_score"),
            half_home_score=row.get("half_home_score"),
            half_away_score=row.get("half_away_score"),
        ))
    return revisions


def resolve_latest_results(
    revisions: Iterable[ResultRevision],
) -> tuple[dict[str, ResultRevision], set[str]]:
    """Pure resolution: equal latest revisions must agree or the match conflicts."""
    grouped: dict[str, list[ResultRevision]] = {}
    for result in revisions:
        grouped.setdefault(result.match_id, []).append(result)
    latest: dict[str, ResultRevision] = {}
    conflicts: set[str] = set()
    for match_id, rows in grouped.items():
        newest = max(row.source_as_of for row in rows)
        contenders = [row for row in rows if row.source_as_of == newest]
        payloads = {_canonical(row.to_record()) for row in contenders}
        if len(payloads) != 1:
            conflicts.add(match_id)
        else:
            latest[match_id] = contenders[0]
    return latest, conflicts


def _selection(row: Mapping[str, Any]) -> Selection:
    return Selection(
        prediction_id=str(row["prediction_id"]),
        match_id=str(row["match_id"]),
        market=Market(str(row["market"])),
        outcome=str(row["outcome"]),
        decimal_odds=float(row["decimal_odds"]),
        handicap=None if row.get("handicap") is None else int(row["handicap"]),
    )


def ticket_from_record(row: Mapping[str, Any]) -> Ticket:
    return Ticket(
        ticket_id=str(row["ticket_id"]),
        selections=tuple(_selection(item) for item in row["selections"]),
        stake=float(row["stake"]),
        created_at=datetime.fromisoformat(str(row["created_at"])),
        sale_cutoffs={
            str(key): datetime.fromisoformat(str(value))
            for key, value in row["sale_cutoffs"].items()
        },
    )


def frozen_tickets(events: Iterable[Mapping[str, Any]], kind: LedgerKind) -> dict[str, Ticket]:
    """Pure projection of immutable tickets from the ledger event stream."""
    tickets: dict[str, Ticket] = {}
    for event in events:
        event_type = event.get("event_type")
        payload = event.get("payload", {})
        rows: Iterable[Mapping[str, Any]] = ()
        if kind is LedgerKind.MODEL and event_type == LedgerEventType.RELEASED.value:
            rows = payload.get("manifest", {}).get("tickets", ())
        elif kind is LedgerKind.PERSONAL and event_type == LedgerEventType.PURCHASE_CONFIRMED.value:
            ticket = payload.get("ticket")
            rows = (ticket,) if isinstance(ticket, Mapping) else ()
        for row in rows:
            parsed = ticket_from_record(row)
            existing = tickets.get(parsed.ticket_id)
            if existing is not None and existing != parsed:
                raise ValueError(f"conflicting frozen ticket: {parsed.ticket_id}")
            tickets[parsed.ticket_id] = parsed
    return tickets


def replay_ledger(
    ledger: Ledger,
    revisions: Iterable[ResultRevision],
    *,
    occurred_at: datetime,
    rules_version: str,
) -> ReplaySummary:
    """Append result/settlement events and safely replay one independent ledger."""
    revision_rows = list(revisions)
    latest, conflicts = resolve_latest_results(revision_rows)
    runtime_conflicts = set(conflicts)

    for result in revision_rows:
        payload = result.to_record()
        key = f"result:{result.match_id}:{result.revision}"
        event = LedgerEvent(
            deterministic_event_id(ledger.kind, LedgerEventType.RESULT_RECORDED, key),
            ledger.kind, LedgerEventType.RESULT_RECORDED, result.match_id,
            result.source_as_of, payload,
        )
        try:
            ledger.append_event(event, idempotency_key=key)
        except ValueError as exc:
            if "idempotency conflict" not in str(exc):
                raise
            runtime_conflicts.add(result.match_id)

    events = ledger.read_events()
    tickets = frozen_tickets(events, ledger.kind)
    latest_settlements: dict[str, Mapping[str, Any]] = {}
    for event in events:
        if event.get("event_type") == LedgerEventType.SETTLED.value:
            latest_settlements[str(event["aggregate_id"])] = event
        elif event.get("event_type") == LedgerEventType.SETTLEMENT_REVERSED.value:
            latest_settlements.pop(str(event["aggregate_id"]), None)

    settled = reversed_count = 0
    pending: list[str] = []
    for ticket_id, ticket in tickets.items():
        match_ids = {selection.match_id for selection in ticket.selections}
        if match_ids & runtime_conflicts or not match_ids <= latest.keys():
            pending.append(ticket_id)
            continue
        result_records = {match_id: latest[match_id].to_record() for match_id in sorted(match_ids)}
        fingerprint = hashlib.sha256(_canonical(result_records).encode("utf-8")).hexdigest()
        prior = latest_settlements.get(ticket_id)
        if prior and prior.get("payload", {}).get("result_fingerprint") == fingerprint:
            continue
        if prior:
            prior_event_id = str(prior["event_id"])
            reversal_key = f"reversal:{ticket_id}:{prior_event_id}:{fingerprint}"
            reversal = LedgerEvent(
                deterministic_event_id(
                    ledger.kind, LedgerEventType.SETTLEMENT_REVERSED, reversal_key
                ),
                ledger.kind, LedgerEventType.SETTLEMENT_REVERSED, ticket_id, occurred_at,
                {"reversed_event_id": prior_event_id, "replacement_fingerprint": fingerprint},
                reason="result revision",
            )
            ledger.append_event(reversal, idempotency_key=reversal_key)
            reversed_count += 1

        domain_results = {
            match_id: MatchResult(
                match_id=result.match_id,
                status=result.status,
                home_score=result.home_score,
                away_score=result.away_score,
                half_home_score=result.half_home_score,
                half_away_score=result.half_away_score,
            )
            for match_id, result in latest.items() if match_id in match_ids
        }
        outcome = settle_ticket(ticket, domain_results)
        if outcome.status is SettlementStatus.PENDING:
            pending.append(ticket_id)
            continue
        settlement_key = f"settlement:{ticket_id}:{fingerprint}:{rules_version}"
        settlement = LedgerEvent(
            deterministic_event_id(ledger.kind, LedgerEventType.SETTLED, settlement_key),
            ledger.kind, LedgerEventType.SETTLED, ticket_id, occurred_at,
            {
                "ticket_id": ticket_id,
                "status": outcome.status.value,
                "payout": outcome.payout,
                "profit": outcome.profit,
                "rules_version": rules_version,
                "result_fingerprint": fingerprint,
                "result_revisions": {
                    match_id: latest[match_id].revision for match_id in sorted(match_ids)
                },
            },
        )
        ledger.append_event(settlement, idempotency_key=settlement_key)
        settled += 1

    return ReplaySummary(
        ledger.kind, settled, reversed_count, tuple(sorted(pending)),
        tuple(sorted(runtime_conflicts)),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--model-ledger", type=Path, default=Path("data/ledgers/model-ledger.jsonl"))
    parser.add_argument(
        "--personal-ledger", type=Path, default=Path("data/private/personal-ledger.jsonl")
    )
    parser.add_argument("--rules-version", default="sporttery-rules-v1")
    args = parser.parse_args()
    raw = json.loads(args.results.read_text(encoding="utf-8"))
    rows = raw["results"] if isinstance(raw, Mapping) else raw
    revisions = parse_result_revisions(rows)
    now = datetime.now(UTC)
    summaries = [
        replay_ledger(
            Ledger(args.model_ledger, LedgerKind.MODEL), revisions,
            occurred_at=now, rules_version=args.rules_version,
        ),
        replay_ledger(
            Ledger(args.personal_ledger, LedgerKind.PERSONAL), revisions,
            occurred_at=now, rules_version=args.rules_version,
        ),
    ]
    print(json.dumps([
        {
            "ledger": row.ledger_kind.value,
            "settled": row.settled,
            "reversed": row.reversed,
            "pending": row.pending,
            "conflicts": row.conflicts,
        }
        for row in summaries
    ], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
