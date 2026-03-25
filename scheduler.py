from __future__ import annotations
from datetime import datetime, timedelta
from ortools.sat.python import cp_model
from collections import defaultdict  # Added missing import

# -- 1. Calendar helper --
def _build_date_slots(start_date, num_rounds):
    """Generates Saturdays starting from the chosen start_date[cite: 9]."""
    # Ensure start_date is a datetime object for timedelta math
    if isinstance(start_date, date) and not isinstance(start_date, datetime):
        start_date = datetime.combine(start_date, datetime.min.time())
    return [start_date + timedelta(days=7 * r) for r in range(num_rounds)]

# -- 2. Global Solver (Mirrors Trial Code Logic) --
def schedule_leagues_or_tools(leagues, start_date, blackout_dates=None, ground_assignments=None, time_limit_seconds=600):
    """
    Solves all divisions simultaneously to respect hard ground-sharing rules[cite: 22, 25].
    """
    ROUNDS = 22  # 12 teams double round robin [cite: 9]
    dates = _build_date_slots(start_date, ROUNDS)
    
    # The Ladder: Try max_consecutive 2, then fallback to 3 [cite: 10, 11, 33]
    for max_streak in [2, 3]:
        model = cp_model.CpModel()
        match_vars = {}
        
        # Build Model Structure [cite: 12, 13]
        for lg in leagues:
            div_name = lg["name"]
            teams = lg["teams"]
            n = len(teams)
            match_vars[div_name] = {}
            for r in range(ROUNDS):
                match_vars[div_name][r] = {}
                for i in range(n):
                    for j in range(n):
                        if i != j:
                            match_vars[div_name][r][(i, j)] = model.NewBoolVar(f"m_{div_name}_r{r}_{i}_{j}")

        # Constraint 1: Double Round Robin (Each pair plays twice: one home, one away) [cite: 14, 15, 16]
        for lg in leagues:
            div_name, n = lg["name"], len(lg["teams"])
            for i in range(n):
                for j in range(i + 1, n):
                    model.Add(sum(match_vars[div_name][r][(i, j)] for r in range(ROUNDS)) == 1)
                    model.Add(sum(match_vars[div_name][r][(j, i)] for r in range(ROUNDS)) == 1)

        # Constraint 2: Each team plays exactly one match in each round [cite: 17, 18]
        for lg in leagues:
            div_name, n = lg["name"], len(lg["teams"])
            for r in range(ROUNDS):
                for i in range(n):
                    model.Add(
                        sum(match_vars[div_name][r][(i, j)] for j in range(n) if i != j) +
                        sum(match_vars[div_name][r][(j, i)] for j in range(n) if i != j) == 1
                    )

        # Constraint 3: No team has more than max_consecutive consecutive home or away games [cite: 19, 20, 21]
        block_size = max_streak + 1
        for lg in leagues:
            div_name, n = lg["name"], len(lg["teams"])
            for i in range(n):
                for start_r in range(ROUNDS - block_size + 1):
                    home_block = [sum(match_vars[div_name][r][(i, j)] for j in range(n) if i != j) for r in range(start_r, start_r + block_size)]
                    away_block = [sum(match_vars[div_name][r][(j, i)] for j in range(n) if i != j) for r in range(start_r, start_r + block_size)]
                    model.Add(sum(home_block) <= max_streak)
                    model.Add(sum(away_block) <= max_streak)

        # Constraint 4: Hard Shared-Ground Rule [cite: 22, 23, 24, 25]
        # Groups teams by ground and ensures only one is at home per round
        venue_map = defaultdict(list)
        for lg in leagues:
            for i, t_name in enumerate(lg["teams"]):
                v = ground_assignments.get(t_name)
                if v: venue_map[v].append((lg["name"], i))
        
        for venue, occupants in venue_map.items():
            if len(occupants) > 1:
                for r in range(ROUNDS):
                    home_trackers = []
                    for div, idx in occupants:
                        # Find the correct division's team count
                        div_teams = next(l["teams"] for l in leagues if l["name"] == div)
                        n_div = len(div_teams)
                        home_trackers.append(sum(match_vars[div][r][(idx, j)] for j in range(n_div) if j != idx))
                    model.Add(sum(home_trackers) <= 1)

        # Solve [cite: 31, 32]
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = float(time_limit_seconds)
        solver.parameters.num_search_workers = 8
        status = solver.Solve(model)

        if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            res_schedules = {}
            for lg in leagues:
                div_name, teams = lg["name"], lg["teams"]
                entries = []
                for r in range(ROUNDS):
                    for (i, j), var in match_vars[div_name][r].items():
                        if solver.Value(var) == 1:
                            entries.append((dates[r], teams[i], teams[j]))
                res_schedules[div_name] = entries
            return {"schedules": res_schedules, "max_consecutive": max_streak}

    raise RuntimeError("No solution found even with max 3 consecutive games[cite: 34].")