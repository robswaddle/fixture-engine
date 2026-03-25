from __future__ import annotations
from collections import defaultdict, deque
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

# -- 2. Clustering Logic --
def find_clusters(leagues: list, ground_assignments: dict) -> list[list[dict]]:
    """Groups leagues into clusters based on shared grounds."""
    # Map every team to their league name
    team_to_league = {}
    for lg in leagues:
        for team in lg["teams"]:
            team_to_league[team] = lg["name"]

    # Build adjacency list: which leagues are linked by shared grounds?
    adj = defaultdict(set)
    # Group teams by ground
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

    # Find connected components
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

# -- 3. Core Solver for a Single Cluster --
def solve_cluster(
    cluster_leagues: list,
    date_slots: list,
    ground_assignments: dict,
    time_limit_seconds: int,
    max_consecutive: int
) -> dict:
    from ortools.sat.python import cp_model
    model = cp_model.CpModel()
    
    processed_leagues = []
    for lg in cluster_leagues:
        teams = list(lg["teams"])
        if len(teams) % 2 != 0:
            teams.append("BYE")
        processed_leagues.append({"name": lg["name"], "teams": teams})

    match_vars = {}
    for lg in processed_leagues:
        name, teams = lg["name"], lg["teams"]
        n, R = len(teams), 2 * (n - 1)
        match_vars[name] = {}
        for r in range(R):
            match_vars[name][r] = {
                (i, j): model.NewBoolVar(f"{name}_r{r}_t{i}v{j}")
                for i in range(n) for j in range(n) if i != j
            }

        # Standard League Constraints
        for i in range(n):
            for j in range(n):
                if i == j: continue
                model.AddExactlyOne(match_vars[name][r][(i, j)] for r in range(R))
            for r in range(R):
                matches = [match_vars[name][r][(i, j)] for j in range(n) if i != j] + \
                          [match_vars[name][r][(j, i)] for j in range(n) if i != j]
                model.AddExactlyOne(matches)
            if teams[i] != "BYE":
                for start_r in range(R - max_consecutive):
                    home_block = [match_vars[name][r][(i, j)] for r in range(start_r, start_r + max_consecutive + 1) for j in range(n) if i != j]
                    away_block = [match_vars[name][r][(j, i)] for r in range(start_r, start_r + max_consecutive + 1) for j in range(n) if i != j]
                    model.Add(sum(home_block) <= max_consecutive)
                    model.Add(sum(away_block) <= max_consecutive)

    # Shared Ground Constraints (Hard)
    venue_map = defaultdict(list)
    for team, venue in ground_assignments.items():
        for lg in processed_leagues:
            if team in lg["teams"]:
                venue_map[venue].append((lg["name"], lg["teams"].index(team)))

    for venue, occupants in venue_map.items():
        if len(occupants) < 2: continue
        # Important: only iterate up to the max rounds available in this cluster
        max_r_in_cluster = max(2 * (len(l["teams"]) - 1) for l in processed_leagues)
        for r in range(max_r_in_cluster):
            home_indicators = []
            for div_name, t_idx in occupants:
                if r in match_vars[div_name]:
                    n_teams = len(next(l["teams"] for l in processed_leagues if l["name"] == div_name))
                    home_indicators.extend([match_vars[div_name][r][(t_idx, j)] for j in range(n_teams) if t_idx != j])
            if len(home_indicators) > 1:
                model.Add(sum(home_indicators) <= 1)

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_seconds
    status = solver.Solve(model)

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return None

    results = {}
    for lg in processed_leagues:
        name, teams = lg["name"], lg["teams"]
        entries = []
        for r, matches in match_vars[name].items():
            for (i, j), var in matches.items():
                if solver.Value(var) == 1:
                    if teams[i] != "BYE" and teams[j] != "BYE":
                        entries.append((date_slots[r], teams[i], teams[j]))
        results[name] = entries
    return results

# -- 4. Orchestrator --
def schedule_leagues_or_tools(
    leagues: list,
    start_date: date,
    blackout_dates: list = [],
    ground_assignments: dict = {},
    time_limit_seconds: int = 300, 
    max_consecutive: int = 2,
) -> dict:
    # 1. Clustering
    clusters = find_clusters(leagues, ground_assignments)
    
    # 2. Preparation
    max_total_rounds = max(2 * (len(lg["teams"]) if len(lg["teams"]) % 2 == 0 else len(lg["teams"]) + 1 - 1) for lg in leagues)
    date_slots = _build_date_slots(start_date, max_total_rounds, blackout_dates)
    
    all_schedules = {}
    
    # 3. Solve each cluster independently
    for i, cluster in enumerate(clusters):
        print(f"Solving cluster {i+1}/{len(clusters)} ({[l['name'] for l in cluster]})")
        # Give each cluster a fair share of the total time limit
        cluster_result = solve_cluster(
            cluster, date_slots, ground_assignments, 
            time_limit_seconds // len(clusters), max_consecutive
        )
        
        if cluster_result is None:
            # If a cluster fails with max_consecutive 2, try 3
            cluster_result = solve_cluster(
                cluster, date_slots, ground_assignments, 
                time_limit_seconds // len(clusters), 3
            )
            
        if cluster_result is None:
            raise RuntimeError(f"Could not find a valid schedule for cluster: {[l['name'] for l in cluster]}")
            
        all_schedules.update(cluster_result)

    return {"schedules": all_schedules, "conflicts": []}