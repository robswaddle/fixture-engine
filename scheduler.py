from __future__ import annotations
import csv
from collections import defaultdict
from datetime import date, timedelta

# -- 1. Calendar helper --
def _build_date_slots(start_date: date, num_slots: int, blackout_dates: list) -> list:
    blackout_set = set(blackout_dates)
    slots, d = [], start_date
    while len(slots) < num_slots:
        if d not in blackout_set:
            slots.append(d)
        d += timedelta(days=7)
    return slots

# -- 2. Main CP-SAT solver --
def schedule_leagues_or_tools(
    leagues: list,
    start_date: date,
    blackout_dates: list = [],
    ground_assignments: dict = {}, # Map team -> Ground Name
    time_limit_seconds: int = 600, # Increased to match Trial Code
    max_consecutive: int = 2,
) -> dict:
    try:
        from ortools.sat.python import cp_model
    except ImportError:
        raise ImportError("ortools is required. Install it with: pip install ortools")

    if not leagues:
        return {"schedules": {}, "conflicts": []}

    # Standardize teams (add BYEs)
    processed_leagues = []
    for lg in leagues:
        teams = list(lg["teams"])
        if len(teams) % 2 != 0:
            teams.append("BYE")
        processed_leagues.append({"name": lg["name"], "teams": teams})

    # Total rounds is based on the largest league
    num_rounds = max(2 * (len(lg["teams"]) - 1) for lg in processed_leagues)
    date_slots = _build_date_slots(start_date, num_rounds, blackout_dates)

    model = cp_model.CpModel()
    match_vars = {}

    # Build Variables for all leagues in ONE model (Unified approach)
    for lg in processed_leagues:
        name, teams = lg["name"], lg["teams"]
        n = len(teams)
        R = 2 * (n - 1)
        match_vars[name] = {}
        for r in range(R):
            match_vars[name][r] = {
                (i, j): model.NewBoolVar(f"{name}_r{r}_t{i}v{j}")
                for i in range(n) for j in range(n) if i != j
            }

    # Constraints (C1: Play twice, C2: Once per round, C3: Streaks)
    for lg in processed_leagues:
        name, teams = lg["name"], lg["teams"]
        n, R = len(teams), 2 * (n - 1)
        
        for i in range(n):
            for j in range(n):
                if i == j: continue
                # C1: Each pair plays exactly once at each venue
                model.AddExactlyOne(match_vars[name][r][(i, j)] for r in range(R))
            
            for r in range(R):
                # C2: Each team plays exactly once per round
                matches = [match_vars[name][r][(i, j)] for j in range(n) if i != j] + \
                          [match_vars[name][r][(j, i)] for j in range(n) if i != j]
                model.AddExactlyOne(matches)

            # C3: Consecutive Home/Away (skip for BYE)
            if teams[i] != "BYE":
                for start_r in range(R - max_consecutive):
                    home_block = [match_vars[name][r][(i, j)] for r in range(start_r, start_r + max_consecutive + 1) for j in range(n) if i != j]
                    away_block = [match_vars[name][r][(j, i)] for r in range(start_r, start_r + max_consecutive + 1) for j in range(n) if i != j]
                    model.Add(sum(home_block) <= max_consecutive)
                    model.Add(sum(away_block) <= max_consecutive)

    # C4: Shared Ground Constraint (The "Secret Sauce")
    venue_map = defaultdict(list)
    for team, venue in ground_assignments.items():
        for lg in processed_leagues:
            if team in lg["teams"]:
                venue_map[venue].append((lg["name"], lg["teams"].index(team)))

    for venue, occupants in venue_map.items():
        if len(occupants) < 2: continue
        for r in range(num_rounds):
            home_indicators = []
            for div_name, t_idx in occupants:
                # Only check if the league actually has a match this round
                if r in match_vars[div_name]:
                    n_teams = len(next(l["teams"] for l in processed_leagues if l["name"] == div_name))
                    home_indicators.extend([match_vars[div_name][r][(t_idx, j)] for j in range(n_teams) if t_idx != j])
            if len(home_indicators) > 1:
                model.Add(sum(home_indicators) <= 1)

    # Solve
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_seconds
    solver.parameters.num_search_workers = 8
    status = solver.Solve(model)

    # Fallback to max_consecutive 3 if 2 fails
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE) and max_consecutive < 3:
        print("Retrying with max_consecutive=3...")
        return schedule_leagues_or_tools(leagues, start_date, blackout_dates, ground_assignments, time_limit_seconds, 3)

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        raise RuntimeError("No feasible schedule found. Try more time or fewer constraints.")

    # Results extraction
    final_schedules = {}
    for lg in processed_leagues:
        name, teams = lg["name"], lg["teams"]
        entries = []
        for r, matches in match_vars[name].items():
            for (i, j), var in matches.items():
                if solver.Value(var) == 1:
                    if teams[i] != "BYE" and teams[j] != "BYE":
                        entries.append((date_slots[r], teams[i], teams[j]))
        entries.sort(key=lambda x: x[0])
        final_schedules[name] = entries

    return {"schedules": final_schedules, "conflicts": []}