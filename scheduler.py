"""
Fixture Scheduling Engine — OR-Tools CP-SAT (match-level model)
===============================================================

Why this is better than the old "round-assignment" model
---------------------------------------------------------
The old scheduler pre-built pairings with the circle method, then used CP-SAT
only to shuffle which *date* each pre-built round fell on.  That forced the
ground-sharing constraint to be *soft* (minimised but never guaranteed zero).

This version uses the same full match-level model as the Trial_Code that was
proven to work.  CP-SAT has complete freedom to decide who plays who in which
round, and every constraint — including "shared-ground teams never both home
on the same matchday" — is **hard**.  Violations are structurally impossible.

Model variables
---------------
  match_vars[division][round][(home_idx, away_idx)]  ∈ {0, 1}
  = 1  iff  teams[home_idx] hosts teams[away_idx] in that round

Constraints (all HARD)
-----------------------
  C1  Each ordered pair (i→j) plays exactly once across all rounds
  C2  Each team plays exactly once per round (full rounds guaranteed)
  C3  No more than `max_consecutive` consecutive home or away games
  C4  Shared-ground pair never both at home in the same round

Calendar
--------
Rounds are numbered 0 … R-1.  Calendar dates are built from start_date
by skipping blackout dates; round r always maps to the (r+1)-th available
Saturday.  Because all divisions run in lockstep (same round index = same
matchday), the C4 cross-division constraint is trivially correct.

Fallback
--------
If no solution is found with max_consecutive=2, the solver automatically
retries with max_consecutive=3 before raising an error.

Output
------
Returns the same dict that app.py already expects:
  {
    "schedules":  { league_name: [(date, home_team, away_team), …] },
    "conflicts":  []   # always empty — ground conflicts are impossible
  }
"""

from __future__ import annotations

import csv
from collections import defaultdict
from datetime import date, timedelta


# ── 1. Calendar helper ────────────────────────────────────────────────────────

def _build_date_slots(
    start_date: date,
    num_slots: int,
    blackout_dates: list,
) -> list:
    """Return the first `num_slots` weekly dates from start_date, skipping blackouts."""
    blackout_set = set(blackout_dates)
    slots, d = [], start_date
    while len(slots) < num_slots:
        if d not in blackout_set:
            slots.append(d)
        d += timedelta(days=7)
    return slots


# ── 2. Main CP-SAT solver ─────────────────────────────────────────────────────

def schedule_leagues_or_tools(
    leagues: list,
    start_date: date,
    blackout_dates: list = [],
    ground_assignments: dict = {},
    time_limit_seconds: int = 60,
    max_consecutive: int = 2,
) -> dict:
    """Schedule a double round-robin for each league using CP-SAT.

    Parameters
    ----------
    leagues : list of {"name": str, "teams": list[str]}
    start_date : date
    blackout_dates : list of date — matchdays to skip in the calendar
    ground_assignments : dict {team_name: venue_name}
        Teams with the same venue name will never both be at home
        on the same matchday (hard constraint, guaranteed zero violations).
    time_limit_seconds : CP-SAT wall-clock limit per solve attempt
    max_consecutive : max consecutive home *or* away allowed (default 2)

    Returns
    -------
    {
        "schedules": {league_name: [(date, home_team, away_team), ...]},
        "conflicts": []
    }
    """
    try:
        from ortools.sat.python import cp_model
    except ImportError as exc:
        raise ImportError(
            "ortools is required.  Install it with:  pip install ortools"
        ) from exc

    if not leagues:
        return {"schedules": {}, "conflicts": []}

    # Pad odd-team leagues with a BYE
    leagues = [
        {**lg, "teams": list(lg["teams"]) + (["BYE"] if len(lg["teams"]) % 2 else [])}
        for lg in leagues
    ]

    # Double round-robin: R = 2*(n-1) rounds per division
    rounds_per_league = {lg["name"]: 2 * (len(lg["teams"]) - 1) for lg in leagues}
    max_rounds = max(rounds_per_league.values())
    date_slots = _build_date_slots(start_date, max_rounds, blackout_dates)

    # Team-index maps per division
    team_index = {lg["name"]: {t: i for i, t in enumerate(lg["teams"])} for lg in leagues}

    # ── Build model ───────────────────────────────────────────────────────────
    model = cp_model.CpModel()

    # match_vars[div_name][round][(i, j)]
    match_vars: dict = {}
    for lg in leagues:
        name, teams = lg["name"], lg["teams"]
        n = len(teams)
        R = rounds_per_league[name]
        match_vars[name] = {
            r: {
                (i, j): model.new_bool_var(f"m__{name}__r{r}__{i}v{j}")
                for i in range(n) for j in range(n) if i != j
            }
            for r in range(R)
        }

    # C1 — Each ordered pair plays exactly once
    for lg in leagues:
        name, teams = lg["name"], lg["teams"]
        n = len(teams)
        R = rounds_per_league[name]
        for i in range(n):
            for j in range(n):
                if i == j:
                    continue
                model.add_exactly_one(match_vars[name][r][(i, j)] for r in range(R))

    # C2 — Each team plays exactly once per round
    for lg in leagues:
        name, teams = lg["name"], lg["teams"]
        n = len(teams)
        R = rounds_per_league[name]
        for r in range(R):
            for i in range(n):
                appearances = (
                    [match_vars[name][r][(i, j)] for j in range(n) if j != i]  # home
                    + [match_vars[name][r][(j, i)] for j in range(n) if j != i]  # away
                )
                model.add_exactly_one(appearances)

    # C3 — Streak constraint: no more than max_consecutive consecutive H or A
    block = max_consecutive + 1
    for lg in leagues:
        name, teams = lg["name"], lg["teams"]
        n = len(teams)
        R = rounds_per_league[name]
        for i in range(n):
            if teams[i] == "BYE":
                continue
            for start_r in range(R - block + 1):
                # Home games in window
                home_terms = [
                    match_vars[name][r][(i, j)]
                    for r in range(start_r, start_r + block)
                    for j in range(n) if j != i
                ]
                # Away games in window
                away_terms = [
                    match_vars[name][r][(j, i)]
                    for r in range(start_r, start_r + block)
                    for j in range(n) if j != i
                ]
                model.add(sum(home_terms) <= max_consecutive)
                model.add(sum(away_terms) <= max_consecutive)

    # C4 — Shared-ground hard constraint
    # Build: venue -> list of (div_name, team_idx)
    venue_occupants: dict = defaultdict(list)
    for team, venue in ground_assignments.items():
        if team == "BYE":
            continue
        for lg in leagues:
            if team in team_index[lg["name"]]:
                venue_occupants[venue].append((lg["name"], team_index[lg["name"]][team]))
                break  # each team is in exactly one league

    for venue, occupants in venue_occupants.items():
        if len(occupants) < 2:
            continue
        all_R = max(rounds_per_league[div] for div, _ in occupants)
        for r in range(all_R):
            home_indicators = []
            for div_name, team_idx in occupants:
                R = rounds_per_league[div_name]
                if r >= R:
                    continue
                n = len(next(lg["teams"] for lg in leagues if lg["name"] == div_name))
                home_indicators.extend(
                    match_vars[div_name][r][(team_idx, j)]
                    for j in range(n) if j != team_idx
                )
            if len(home_indicators) >= 2:
                model.add(sum(home_indicators) <= 1)

    # ── Solve ─────────────────────────────────────────────────────────────────
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_seconds
    solver.parameters.log_search_progress = False
    # num_workers API name changed between ortools versions — try both
    for param_name in ("num_workers", "num_search_workers"):
        try:
            setattr(solver.parameters, param_name, 8)
            break
        except AttributeError:
            continue

    status = solver.solve(model)

    # Automatic fallback: relax streak by 1 and retry once
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        if max_consecutive < 3:
            return schedule_leagues_or_tools(
                [{**lg, "teams": [t for t in lg["teams"] if t != "BYE"]} for lg in leagues],
                start_date,
                blackout_dates,
                ground_assignments,
                time_limit_seconds,
                max_consecutive=max_consecutive + 1,
            )
        raise RuntimeError(
            "OR-Tools could not find a feasible schedule within the time limit. "
            "Try increasing time_limit_seconds or adjusting blackout dates."
        )

    # ── Extract results ───────────────────────────────────────────────────────
    schedules: dict = {}
    for lg in leagues:
        name, teams = lg["name"], lg["teams"]
        n = len(teams)
        R = rounds_per_league[name]
        entries = []
        for r in range(R):
            match_date = date_slots[r] if r < len(date_slots) else date_slots[-1]
            for i in range(n):
                for j in range(n):
                    if i == j:
                        continue
                    if solver.value(match_vars[name][r][(i, j)]) == 1:
                        home, away = teams[i], teams[j]
                        if home != "BYE" and away != "BYE":
                            entries.append((match_date, home, away))
        entries.sort(key=lambda x: x[0])
        schedules[name] = entries

    return {"schedules": schedules, "conflicts": []}


# ── 3. Legacy API shims ────────────────────────────────────────────────────────
# These keep app.py working with zero changes.

def generate_double_round_robin(teams: list) -> list:
    """Circle-method double round-robin — kept for backwards compatibility."""
    team_list = list(teams)
    if len(team_list) % 2 == 1:
        team_list.append("BYE")
    n = len(team_list)
    matches, match_id, first_half = [], 0, []
    for round_idx in range(n - 1):
        rnd = []
        for i in range(n // 2):
            home, away = team_list[i], team_list[n - 1 - i]
            if home != "BYE" and away != "BYE":
                m = {"id": match_id, "home": home, "away": away, "round": round_idx}
                matches.append(m)
                rnd.append(m)
                match_id += 1
        first_half.append(rnd)
        team_list = [team_list[0]] + [team_list[-1]] + team_list[1:-1]
    offset = n - 1
    for r_idx, rnd in enumerate(first_half):
        for m in rnd:
            matches.append({"id": match_id, "home": m["away"], "away": m["home"],
                             "round": r_idx + offset})
            match_id += 1
    return matches


def generate_round_robin(teams: list) -> list:
    matches  = generate_double_round_robin(teams)
    n_rounds = max(m["round"] for m in matches) + 1
    rounds   = [[] for _ in range(n_rounds)]
    for m in matches:
        rounds[m["round"]].append((m["home"], m["away"]))
    return rounds


def group_into_rounds(fixtures, teams):
    """No-op shim kept for backwards compatibility."""
    return fixtures


def assign_dates(rounds, start_date, blackout_dates=[], interval_days=7):
    schedule, current_date = [], start_date
    blackout_set = set(blackout_dates)
    for rnd in rounds:
        while current_date in blackout_set:
            current_date += timedelta(days=interval_days)
        for home, away in rnd:
            schedule.append((current_date, home, away))
        current_date += timedelta(days=interval_days)
    return schedule


def reschedule_game(schedule, home_team, away_team, new_date):
    updated, rescheduled = [], False
    for game in schedule:
        if (game[1].lower() == home_team.lower()
                and game[2].lower() == away_team.lower()):
            updated.append((new_date, game[1], game[2]))
            rescheduled = True
        else:
            updated.append(game)
    updated.sort(key=lambda x: x[0])
    return updated, rescheduled


def resolve_ground_conflicts(schedule, ground_assignments):
    """Legacy shim — ground conflicts are structurally impossible with the
    CP-SAT model, so this is a no-op.  Kept so app.py needs no changes."""
    return schedule


# ── 4. CLI helpers ─────────────────────────────────────────────────────────────

def check_home_away_balance(schedule, teams):
    print("\n--- Home/Away Balance ---")
    for team in teams:
        h = sum(1 for g in schedule if g[1] == team)
        a = sum(1 for g in schedule if g[2] == team)
        print(f"  {team}: {h}H {a}A")


def print_schedule_by_round(schedule, teams=None):
    print("\n--- Schedule ---")
    current_date, rn = None, 1
    for game in schedule:
        if game[0] != current_date:
            current_date = game[0]
            print(f"\nRound {rn} -- {current_date.strftime('%A %d %B %Y')}")
            rn += 1
        print(f"  {game[1]} vs {game[2]}")


def export_to_csv(schedule, filename="fixtures.csv"):
    with open(filename, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Date", "Home Team", "Away Team"])
        for game in schedule:
            writer.writerow([game[0].strftime("%d/%m/%Y"), game[1], game[2]])
    print(f"Exported to {filename}")


# ── 5. CLI demo ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    division_1 = [
        "Burnmoor 1st XI", "South Northumberland 1st XI", "Castle Eden 1st XI",
        "Felling 1st XI", "Chester Le Street 1st XI", "Hetton Lyons 1st XI",
        "Burnopfield 1st XI", "Newcastle 1st XI", "Ashington 1st XI",
        "Shotley Bridge 1st XI", "Benwell Hill 1st XI", "Seaham Harbour 1st XI",
    ]
    division_2 = [
        "Felling 2nd XI", "Newcastle City CC 2nd XI", "Chester Le Street 2nd XI",
        "Ashington 2nd XI", "South Northumberland 2nd XI", "Newcastle 2nd XI",
        "Tynemouth 2nd XI", "Benwell Hill 2nd XI", "Tynedale 2nd XI",
        "Hetton Lyons 2nd XI", "Whitburn 2nd XI", "Castle Eden 2nd XI",
    ]
    ground_assignments = {
        "Newcastle 1st XI":            "Newcastle",
        "Newcastle 2nd XI":            "Newcastle",
        "Benwell Hill 1st XI":         "Benwell Hill",
        "Benwell Hill 2nd XI":         "Benwell Hill",
        "Chester Le Street 1st XI":    "Chester Le Street",
        "Chester Le Street 2nd XI":    "Chester Le Street",
        "Ashington 1st XI":            "Ashington",
        "Ashington 2nd XI":            "Ashington",
        "South Northumberland 1st XI": "South Northumberland",
        "South Northumberland 2nd XI": "South Northumberland",
        "Hetton Lyons 1st XI":         "Hetton Lyons",
        "Hetton Lyons 2nd XI":         "Hetton Lyons",
        "Felling 1st XI":              "Felling",
        "Felling 2nd XI":              "Felling",
        "Castle Eden 1st XI":          "Castle Eden",
        "Castle Eden 2nd XI":          "Castle Eden",
    }
    blackout_dates = [date(2025, 4, 19), date(2025, 5, 3), date(2025, 5, 26)]
    leagues = [
        {"name": "Division 1", "teams": division_1},
        {"name": "Division 2", "teams": division_2},
    ]

    print("Solving with OR-Tools CP-SAT (match-level model)…")
    result = schedule_leagues_or_tools(
        leagues, date(2025, 4, 5), blackout_dates, ground_assignments,
        time_limit_seconds=60,
    )

    for league in leagues:
        name = league["name"]
        print(f"\n{'='*55}\n{name}\n{'='*55}")
        print_schedule_by_round(result["schedules"][name])
        check_home_away_balance(result["schedules"][name], league["teams"])
        export_to_csv(result["schedules"][name], f"{name.lower().replace(' ', '_')}.csv")

    if result["conflicts"]:
        print(f"\nWARNING: {len(result['conflicts'])} ground conflict(s) remain:")
        for c in result["conflicts"]:
            print(f"  {c['date']} — {c['ground']}: {c['team1']} & {c['team2']}")
    else:
        print("\n✓ No ground conflicts.")
