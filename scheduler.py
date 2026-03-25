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

# -- 2. Tiered Clustering Logic --
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
    
    # Process in input order to respect Tier Priority
    for lg in leagues:
        lg_name = lg["name"]
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

# -- 3. Core Solver Logic --
def solve_cluster(
    cluster_leagues: list,
    date_slots: list,
    ground_assignments: dict,
    time_limit_seconds: int,
    max_consecutive: int,
    existing_home_slots: dict 
) -> dict | None:
    model = cp_model.CpModel()
    processed_leagues = []
    for lg in cluster_leagues:
        teams = list(lg["teams"])
        if len(teams) % 2 != 0: teams.append("BYE")
        processed_leagues.append({"name": lg["name"], "teams": teams})

    match_vars = {}
    is_home_vars = {}
    penalties = []
    
    max_rounds_in_cluster = max(2 * (len(lg["teams"]) - 1) for lg in processed_leagues)

    for lg in processed_leagues:
        name, teams = lg["name"], lg["teams"]
        n_teams = len(teams)
        R = 2 * (n_teams - 1)
        match_vars[name] = {}
        is_home_vars[name] = {}
        
        for r in range(R):
            match_vars[name][r] = {(i, j): model.NewBoolVar(f"{name}_r{r}_{i}v{j}") 
                                   for i in range(n_teams) for j in range(n_teams) if i != j}
            is_home_vars[name][r] = {i: model.NewBoolVar(f"{name}_r{r}_{i}_h") 
                                     for i in range(n_teams)}

        # Basic Round Robin Constraints
        for i in range(n_teams):
            for j in range(n_teams):
                if i == j: continue
                model.AddExactlyOne(match_vars[name][r][(i, j)] for r in range(R))
            
            for r in range(R):
                # Channeling match_vars to is_home_vars
                model.Add(is_home_vars[name][r][i] == sum(match_vars[name][r][(i, j)] for j in range(n_teams) if i != j))
                # Each team plays exactly once per round
                model.AddExactlyOne([match_vars[name][r][(i, j)] for j in range(n_teams) if i != j] + 
                                     [match_vars[name][r][(j, i)] for j in range(n_teams) if i != j])

        # Multi-Objective Penalties (Favoring H-A-H-A rhythm)
        for i in range(n_teams):
            if teams[i] == "BYE": continue
            for r in range(R - 1):
                h2, a2 = model.NewBoolVar(f'h2_{name}_{i}_{r}'), model.NewBoolVar(f'a2_{name}_{i}_{r}')
                model.Add(h2 == 1).OnlyEnforceIf([is_home_vars[name][r][i], is_home_vars[name][r+1][i]])
                model.Add(a2 == 1).OnlyEnforceIf([is_home_vars[name][r][i].Not(), is_home_vars[name][r+1][i].Not()])
                penalties.extend([h2, a2])

            # Hard Streak Constraints (The Ladder Step)
            for start_r in range(R - max_consecutive):
                model.Add(sum(is_home_vars[name][r][i] for r in range(start_r, start_r + max_consecutive + 1)) <= max_consecutive)
                model.Add(sum(is_home_vars[name][r][i].Not() for r in range(start_r, start_r + max_consecutive + 1)) <= max_consecutive)

    # Cross-Tier Ground Locking
    for team, venue in ground_assignments.items():
        for lg in processed_leagues:
            if team in lg["teams"]:
                t_idx = lg["teams"].index(team)
                R_div = 2 * (len(lg["teams"]) - 1)
                for r in range(R_div):
                    if existing_home_slots.get(r, {}).get(venue):
                        model.Add(is_home_vars[lg["name"]][r][t_idx] == 0)

    # Within-Cluster Ground Sharing
    venue_map = defaultdict(list)
    for team, venue in ground_assignments.items():
        for lg in processed_leagues:
            if team in lg["teams"]: venue_map[venue].append((lg["name"], lg["teams"].index(team)))
    
    for venue, occupants in venue_map.items():
        if len(occupants) > 1:
            for r in range(max_rounds_in_cluster):
                current_cluster_homes = []
                for div_name, t_idx in occupants:
                    if div_name in is_home_vars and r in is_home_vars[div_name]:
                        current_cluster_homes.append(is_home_vars[div_name][r][t_idx])
                if len(current_cluster_homes) > 1:
                    model.Add(sum(current_cluster_homes) <= 1)

    model.Minimize(sum(penalties))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = float(time_limit_seconds)
    status = solver.Solve(model)

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return None

    # Format Results
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
def schedule_leagues_or_tools(
    leagues: list, 
    start_date: date, 
    blackout_dates: list = [], 
    ground_assignments: dict = {}, 
    time_limit_seconds: int = 300
) -> dict:
    clusters = find_clusters(leagues, ground_assignments)
    
    # Calculate global max rounds to build date slots
    max_total_rounds = 0
    for lg in leagues:
        n = len(lg["teams"])
        if n % 2 != 0: n += 1
        max_total_rounds = max(max_total_rounds, 2 * (n - 1))
        
    date_slots = _build_date_slots(start_date, max_total_rounds, blackout_dates)
    all_schedules = {}
    locked_home_slots = defaultdict(lambda: defaultdict(bool))

    time_per_cluster = time_limit_seconds // len(clusters) if clusters else time_limit_seconds

    for cluster in clusters:
        cluster_names = [l['name'] for l in cluster]
        cluster_result = None
        
        # The Constraint Ladder (Step 1)
        for ladder_limit in [2, 3, 4]:
            cluster_result = solve_cluster(
                cluster, date_slots, ground_assignments, 
                time_per_cluster // 3, ladder_limit, locked_home_slots
            )
            if cluster_result: break
            
        if cluster_result is None:
            raise RuntimeError(f"Infeasible tier: {cluster_names}. Constraints too tight for shared grounds.")
            
        # Update our global "Lock" tracker for the next tier
        for div_name, fixtures in cluster_result.items():
            for g_date, home, away in fixtures:
                r_idx = date_slots.index(g_date)
                venue = ground_assignments.get(home)
                if venue:
                    locked_home_slots[r_idx][venue] = True
                    
        all_schedules.update(cluster_result)

    return {"schedules": all_schedules}