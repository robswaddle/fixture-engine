from __future__ import annotations
from collections import defaultdict, deque
from datetime import date, timedelta
from ortools.sat.python import cp_model

# -- 1. Calendar helper --
def _build_date_slots(start_date: date, num_slots: int, blackout_dates: list) -> list:
    blackout_set = set(blackout_dates)
    slots, d = [], start_date
    while len(slots) < num_slots:
        if d not in blackout_set:
            slots.append(d)
        d += timedelta(days=7)
    return slots

# -- 2. Clustering Logic --
def find_clusters(leagues: list, ground_assignments: dict) -> list[list[dict]]:
    team_to_league = {}
    for lg in leagues:
        for team in lg["teams"]:
            team_to_league[team] = lg["name"]

    adj = defaultdict(set)
    ground_to_teams = defaultdict(list)
    for team, ground in ground_assignments.items():
        ground_to_teams[ground].append(team)

    for teams_at_ground in ground_to_teams.values():
        for i in range(len(teams_at_ground)):
            for j in range(i + 1, len(teams_at_ground)):
                lg1 = team_to_league.get(teams_at_ground[i])
                lg2 = team_to_league.get(teams_at_ground[j])
                if lg1 and lg2 and lg1 != lg2:
                    adj[lg1].add(lg2)
                    adj[lg2].add(lg1)

    visited = set()
    clusters = []
    league_map = {lg["name"]: lg for lg in leagues}
    
    for lg_name in league_map:
        if lg_name not in visited:
            component = []
            queue = deque([lg_name])
            visited.add(lg_name)
            while queue:
                curr = queue.popleft()
                component.append(league_map[curr])
                for neighbor in adj[curr]:
                    if neighbor not in visited:
                        visited.add(neighbor)
                        queue.append(neighbor)
            clusters.append(component)
    return clusters

# -- 3. Core Solver with Multi-Objective Penalties --
def solve_cluster(
    cluster_leagues: list,
    date_slots: list,
    ground_assignments: dict,
    time_limit_seconds: int,
    max_consecutive: int
) -> dict | None:
    model = cp_model.CpModel()
    processed_leagues = []
    for lg in cluster_leagues:
        teams = list(lg["teams"])
        if len(teams) % 2 != 0: teams.append("BYE")
        processed_leagues.append({"name": lg["name"], "teams": teams})

    match_vars = {}
    penalties = [] # List to hold all "rhythm break" penalty variables
    max_cluster_rounds = max(2 * (len(lg["teams"]) - 1) for lg in processed_leagues)

    for lg in processed_leagues:
        name, teams = lg["name"], lg["teams"]
        n_teams = len(teams)
        R = 2 * (n_teams - 1)
        match_vars[name] = {}
        
        for r in range(R):
            match_vars[name][r] = {
                (i, j): model.NewBoolVar(f"{name}_r{r}_t{i}v{j}")
                for i in range(n_teams) for j in range(n_teams) if i != j
            }

        # C1 & C2: Standard Round Robin Constraints
        for i in range(n_teams):
            for j in range(n_teams):
                if i == j: continue
                model.AddExactlyOne(match_vars[name][r][(i, j)] for r in range(R))
        for r in range(R):
            for i in range(n_teams):
                matches = [match_vars[name][r][(i, j)] for j in range(n_teams) if i != j] + \
                          [match_vars[name][r][(j, i)] for j in range(n_teams) if i != j]
                model.AddExactlyOne(matches)

        # C3: Hard Max Consecutive Constraints
        # Plus soft penalty for any consecutive H/A to encourage perfect alternation (H, A, H, A)
        for i in range(n_teams):
            if teams[i] == "BYE": continue
            for r in range(R - 1):
                # Penalty for two Home games in a row
                h2 = model.NewBoolVar(f"h2_{name}_t{i}_r{r}")
                model.Add(h2 == 1).OnlyEnforceIf([
                    sum(match_vars[name][r][(i, j)] for j in range(n_teams) if i != j),
                    sum(match_vars[name][r+1][(i, j)] for j in range(n_teams) if i != j)
                ])
                penalties.append(h2)

                # Penalty for two Away games in a row
                a2 = model.NewBoolVar(f"a2_{name}_t{i}_r{r}")
                model.Add(a2 == 1).OnlyEnforceIf([
                    sum(match_vars[name][r][(j, i)] for j in range(n_teams) if i != j),
                    sum(match_vars[name][r+1][(j, i)] for j in range(n_teams) if i != j)
                ])
                penalties.append(a2)

            # Hard constraints (the "Ladder" limit)
            for start_r in range(R - max_consecutive):
                home_block = [match_vars[name][r][(i, j)] for r in range(start_r, start_r + max_consecutive + 1) for j in range(n_teams) if i != j]
                away_block = [match_vars[name][r][(j, i)] for r in range(start_r, start_r + max_consecutive + 1) for j in range(n_teams) if i != j]
                model.Add(sum(home_block) <= max_consecutive)
                model.Add(sum(away_block) <= max_consecutive)

    # --- Shared Ground Constraints ---
    # (Remains exactly the same as previous turn)
    venue_map = defaultdict(list)
    for team, venue in ground_assignments.items():
        for lg in processed_leagues:
            if team in lg["teams"]: venue_map[venue].append((lg["name"], lg["teams"].index(team)))

    for venue, occupants in venue_map.items():
        if len(occupants) < 2: continue
        for r in range(max_cluster_rounds):
            home_indicators = []
            for div_name, t_idx in occupants:
                if div_name in match_vars and r in match_vars[div_name]:
                    div_teams = next(l["teams"] for l in processed_leagues if l["name"] == div_name)
                    home_indicators.extend([match_vars[div_name][r][(t_idx, j)] for j in range(len(div_teams)) if t_idx != j])
            if len(home_indicators) > 1: model.Add(sum(home_indicators) <= 1)

    # --- OBJECTIVE FUNCTION ---
    # Minimize the total number of consecutive H/A streaks
    model.Minimize(sum(penalties))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = float(time_limit_seconds)
    status = solver.Solve(model)

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE): return None

    results = {}
    for lg in processed_leagues:
        name, teams = lg["name"], lg["teams"]
        entries = []
        for r in sorted(match_vars[name].keys()):
            for (i, j), var in match_vars[name][r].items():
                if solver.Value(var) == 1:
                    if teams[i] != "BYE" and teams[j] != "BYE":
                        entries.append((date_slots[r], teams[i], teams[j]))
        results[name] = entries
    return results

# -- 4. Orchestrator --
# (Remains same as previous turn)
def schedule_leagues_or_tools(leagues, start_date, blackout_dates=[], ground_assignments={}, time_limit_seconds=300, max_consecutive=2):
    # ... same orchestrator logic as before ...
    return {"schedules": all_schedules, "conflicts": []}