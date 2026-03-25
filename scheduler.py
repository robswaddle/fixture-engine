from __future__ import annotations
from datetime import datetime, timedelta, date  # Ensures 'date' and 'datetime' are defined
from ortools.sat.python import cp_model        # Required for the solver
from collections import defaultdict             # Required for ground grouping

# -- 1. Calendar helper --
def _build_date_slots(start_date, num_rounds):
    """
    Generates Saturdays starting from the chosen start_date.
    Matches the make_dates function logic[cite: 9].
    """
    if isinstance(start_date, date) and not isinstance(start_date, datetime):
        start_date = datetime.combine(start_date, datetime.min.time())
    return [start_date + timedelta(days=7 * r) for r in range(num_rounds)]

# -- 2. Global Solver (Mirrors Trial Code Logic [cite: 12, 32]) --
def schedule_leagues_or_tools(leagues, start_date, blackout_dates=None, ground_assignments=None, time_limit_seconds=600):
    """
    Solves all divisions simultaneously to respect hard ground-sharing rules[cite: 22, 25].
    """
    ROUNDS = 22  # Standard for 12-team double round robin [cite: 12]
    dates = _build_date_slots(start_date, ROUNDS)
    
    # The Ladder: Try max_consecutive 2 [cite: 10], then fallback to 3 [cite: 11]
    for max_streak in [2, 3]:
        model = cp_model.CpModel()
        match_vars = {}
        
        # Build Model Structure for each division [cite: 12, 13]
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

        # Constraint 1: Double Round Robin [cite: 15, 16]
        for lg in leagues:
            div_name, n = lg["name"], len(lg["teams"])
            for i in range(n):
                for j in range(i + 1, n):
                    model.Add(sum(match_vars[div_name][r][(i, j)] for r in range(ROUNDS)) == 1)
                    model.Add(sum(match_vars[div_name][r][(j, i)] for r in range(ROUNDS)) == 1)

        # Constraint 2: Exactly one match per round [cite: 17, 18]
        for lg in leagues:
            div_name, n = lg["name"], len(lg["teams"])
            for r in range(ROUNDS):
                for i in range(n):
                    model.Add(
                        sum(match_vars[div_name][r][(i, j)] for j in range(n) if i != j) +
                        sum(match_vars[div_name][r][(j, i)] for j in range(n) if i != j) == 1
                    )

        # Constraint 3: Max Consecutive Home/Away Games [cite: 19, 21]
        block_size = max_streak + 1
        for lg in leagues:
            div_name, n = lg["name"], len(lg["teams"])
            for i in range(n):
                for start_r in range(ROUNDS - block_size + 1):
                    home_block = [sum(match_vars[div_name][r][(i, j)] for j in range(n) if i != j) for r in range(start_r, start_r + block_size)]
                    away_block = [sum(match_vars[div_name][r][(j, i)] for j in range(n) if i != j) for r in range(start_r, start_r + block_size)]
                    model.Add(sum(home_block) <= max_streak)
                    model.Add(sum(away_block) <= max_streak)

        # Constraint 4: Hard Shared-Ground Rule [cite: 22, 25]
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
                        # Fetch the division size dynamically from input
                        div_data = next(l for l in leagues if l["name"] == div)
                        n_div = len(div_data["teams"])
                        # Calculate home status based on match_vars 
                        home_trackers.append(sum(match_vars[div][r][(idx, j)] for j in range(n_div) if j != idx))
                    # Linked teams cannot both be at home [cite: 25]
                    model.Add(sum(home_trackers) <= 1)

        # Solve with parameters from Trial Code [cite: 25]
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
                            # Map round index to dates [cite: 27, 28]
                            entries.append((dates[r], teams[i], teams[j]))
                res_schedules[div_name] = entries
            return {"schedules": res_schedules, "max_consecutive": max_streak}

    # If status is INFEASIBLE or UNKNOWN after ladder [cite: 26, 34]
    raise RuntimeError("No solution found even with max 3 consecutive games.")