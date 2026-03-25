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

# -- 3. Core Solver for a Single Cluster --
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
        if len(teams) % 2 != 0:
            teams.append("BYE")
        processed_leagues.append({"name": lg["name"], "teams": teams})

    match_vars = {}
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

        # C1: Each pair plays exactly once (i hosts j)
        for i in range(n_teams):
            for j in range(n_teams):
                if i == j: continue
                model.AddExactlyOne(match_vars[name][r][(i, j)] for r in range(R))

        # C2: Each team plays exactly once per round
        for r in range(R):
            for i in range(n_teams):
                matches = [match_vars[name][r][(i, j)] for j in range(n_teams) if i != j] + \
                          [match_vars[name][r][(j, i)] for j in range(n_teams) if i != j]
                model.AddExactlyOne(matches)

        # C3: Home/Away Streak Constraint (Using the current ladder step)
        for i in range(n_teams):
            if teams[i] == "BYE": continue
            # If max_consecutive is 2, we limit blocks of 3. If 3, we limit blocks of 4.
            for start_r in range(R - max_consecutive):
                home_block = [match_vars[name][r][(i, j)] for r in range(start_r, start_r + max_consecutive + 1) for j in range(n_teams) if i != j]
                away_block = [match_vars[name][r][(j, i)] for r in range(start_r, start_r + max_consecutive + 1) for j in range(n_teams) if i != j]
                model.Add(sum(home_block) <= max_consecutive)
                model.Add(sum(away_block) <= max_consecutive)

    # --- Shared Ground Constraints (Hard) ---
    venue_map = defaultdict(list)
    for team, venue in ground_assignments.items():
        for lg in processed_leagues:
            if team in lg["teams"]:
                venue_map[venue].append((lg["name"], lg["teams"].index(team)))

    for venue, occupants in venue_map.items():
        if len(occupants) < 2: continue
        for r in range(max_cluster_rounds):
            home_indicators = []
            for div_name, t_idx in occupants:
                if div_name in match_vars and r in match_vars[div_name]:
                    div_teams = next(l["teams"] for l in processed_leagues if l["name"] == div_name)
                    n_div = len(div_teams)
                    home_indicators.extend([match_vars[div_name][r][(t_idx, j)] for j in range(n_div) if t_idx != j])
            if len(home_indicators) > 1:
                model.Add(sum(home_indicators) <= 1)

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = float(time_limit_seconds)
    status = solver.Solve(model)

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return None

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

# -- 4. Orchestrator with Constraint Ladder --
def schedule_leagues_or_tools(
    leagues: list,
    start_date: date,
    blackout_dates: list = [],
    ground_assignments: dict = {},
    time_limit_seconds: int = 300, 
    max_consecutive: int = 2,
) -> dict:
    clusters = find_clusters(leagues, ground_assignments)
    
    max_total_rounds = 0
    for lg in leagues:
        n = len(lg["teams"])
        if n % 2 != 0: n += 1
        max_total_rounds = max(max_total_rounds, 2 * (n - 1))
        
    date_slots = _build_date_slots(start_date, max_total_rounds, blackout_dates)
    all_schedules = {}
    
    time_per_cluster = time_limit_seconds // len(clusters) if clusters else time_limit_seconds

    for cluster in clusters:
        cluster_names = [l['name'] for l in cluster]
        
        # STEP 1: Try with Ideal Constraints (max_consecutive=2)
        print(f"Solving cluster {cluster_names} with max_consecutive=2...")
        cluster_result = solve_cluster(
            cluster, date_slots, ground_assignments, 
            time_per_cluster // 2, 2
        )
        
        # STEP 2: Relaxation - If Step 1 failed, try max_consecutive=3
        if cluster_result is None:
            print(f"Relaxing cluster {cluster_names} to max_consecutive=3...")
            cluster_result = solve_cluster(
                cluster, date_slots, ground_assignments, 
                time_per_cluster // 2, 3
            )
            
        # STEP 3: Final Relaxation - Try max_consecutive=4
        if cluster_result is None:
            print(f"Final relaxation for cluster {cluster_names} (max_consecutive=4)...")
            cluster_result = solve_cluster(
                cluster, date_slots, ground_assignments, 
                time_per_cluster // 2, 4
            )
            
        if cluster_result is None:
            raise RuntimeError(f"Could not find a valid schedule for cluster: {cluster_names} even with relaxed constraints.")
            
        all_schedules.update(cluster_result)

    return {"schedules": all_schedules, "conflicts": []}