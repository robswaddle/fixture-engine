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

# -- 2. Clustering Logic (Group Leagues that share grounds) --
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
                lg1, lg2 = team_to_league.get(teams_at_ground[i]), team_to_league.get(teams_at_ground[j])
                if lg1 and lg2 and lg1 != lg2:
                    adj[lg1].add(lg2)
                    adj[lg2].add(lg1)

    visited = set()
    clusters = []
    league_map = {lg["name"]: lg for lg in leagues}
    for lg in leagues:
        name = lg["name"]
        if name not in visited:
            component = []
            queue = deque([name])
            visited.add(name)
            while queue:
                curr = queue.popleft()
                component.append(league_map[curr])
                for neighbor in adj[curr]:
                    if neighbor not in visited:
                        visited.add(neighbor)
                        queue.append(neighbor)
            clusters.append(component)
    return clusters

# -- 3. The Core Solver (With Soft Tier-Locking) --
def solve_cluster(
    cluster_leagues: list,
    date_slots: list,
    ground_assignments: dict,
    time_limit: int,
    max_consecutive: int,
    existing_locks: dict
) -> dict | None:
    model = cp_model.CpModel()
    processed = []
    for lg in cluster_leagues:
        ts = list(lg["teams"])
        if len(ts) % 2 != 0: ts.append("BYE")
        processed.append({"name": lg["name"], "teams": ts})

    match_vars = {}
    is_home_vars = {}
    penalties = []

    # Initialize Variables
    for lg in processed:
        name, teams = lg["name"], lg["teams"]
        R = 2 * (len(teams) - 1)
        match_vars[name] = {}
        is_home_vars[name] = {}
        
        for r in range(R):
            match_vars[name][r] = {(i, j): model.NewBoolVar(f"{name}_r{r}_{i}v{j}") 
                                   for i in range(len(teams)) for j in range(len(teams)) if i != j}
            is_home_vars[name][r] = {i: model.NewBoolVar(f"{name}_r{r}_{i}_h") for i in range(len(teams))}

        # Constraints: Round Robin & One Match Per Round
        for i in range(len(teams)):
            for j in range(len(teams)):
                if i != j: model.AddExactlyOne(match_vars[name][r][(i, j)] for r in range(R))
            
            for r in range(R):
                model.Add(is_home_vars[name][r][i] == sum(match_vars[name][r][(i, j)] for j in range(len(teams)) if i != j))
                model.AddExactlyOne([match_vars[name][r][(i, j)] for j in range(len(teams)) if i != j] + 
                                     [match_vars[name][r][(j, i)] for j in range(len(teams)) if i != j])

        # Rhythm Penalties & Streak Limits
        for i in range(len(teams)):
            if teams[i] == "BYE": continue
            for r in range(R - 1):
                h2, a2 = model.NewBoolVar(f'h2_{name}_{i}_{r}'), model.NewBoolVar(f'a2_{name}_{i}_{r}')
                model.Add(h2 == 1).OnlyEnforceIf([is_home_vars[name][r][i], is_home_vars[name][r+1][i]])
                model.Add(a2 == 1).OnlyEnforceIf([is_home_vars[name][r][i].Not(), is_home_vars[name][r+1][i].Not()])
                penalties.extend([h2, a2])

            for start_r in range(R - max_consecutive):
                model.Add(sum(is_home_vars[name][r][i] for r in range(start_r, start_r + max_consecutive + 1)) <= max_consecutive)
                model.Add(sum(is_home_vars[name][r][i].Not() for r in range(start_r, start_r + max_consecutive + 1)) <= max_consecutive)

    # --- Robust Ground Logic (Tier Awareness) ---
    venue_teams = defaultdict(list)
    for t, v in ground_assignments.items():
        for lg in processed:
            if t in lg["teams"]: venue_teams[v].append((lg["name"], lg["teams"].index(t)))

    for v, occupants in venue_teams.items():
        max_r = max(2 * (len(l["teams"]) - 1) for l in processed)
        for r in range(max_r):
            active_homes = [is_home_vars[div][r][idx] for div, idx in occupants if r in is_home_vars[div]]
            
            # If a higher tier "Locked" this ground, we apply a massive penalty for using it
            if existing_locks.get(r, {}).get(v):
                tier_conflict = model.NewBoolVar(f'conflict_{v}_{r}')
                model.Add(sum(active_homes) >= 1).OnlyEnforceIf(tier_conflict)
                penalties.append(tier_conflict * 1000) 
            
            if len(active_homes) > 1:
                model.Add(sum(active_homes) <= 1)

    # Solve
    model.Minimize(sum(penalties))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = float(time_limit)
    status = solver.Solve(model)

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return None

    # Result Formatting
    res = {}
    for lg in processed:
        name, ts, entries = lg["name"], lg["teams"], []
        for r in sorted(match_vars[name].keys()):
            for (i, j), var in match_vars[name][r].items():
                if solver.Value(var) == 1 and ts[i] != "BYE" and ts[j] != "BYE":
                    entries.append((date_slots[r], ts[i], ts[j]))
        res[name] = entries
    return res

# -- 4. Orchestrator --
def schedule_leagues_or_tools(leagues, start_date, blackout_dates=[], ground_assignments={}, time_limit_seconds=300):
    clusters = find_clusters(leagues, ground_assignments)
    # Calculate global max rounds across all leagues
    max_rounds = 0
    for lg in leagues:
        n = len(lg["teams"])
        if n % 2 != 0: n += 1
        max_rounds = max(max_rounds, 2 * (n - 1))
        
    date_slots = _build_date_slots(start_date, max_rounds, blackout_dates)
    all_scheds = {}
    locked_grounds = defaultdict(lambda: defaultdict(bool))

    for cluster in clusters:
        cluster_res = None
        # The Ladder: Try progressively easier constraints
        for ladder in [2, 3, 4, 5]:
            cluster_res = solve_cluster(cluster, date_slots, ground_assignments, 45, ladder, locked_grounds)
            if cluster_res: break
        
        if not cluster_res:
            raise RuntimeError(f"Cluster {[l['name'] for l in cluster]} is mathematically impossible with current ground sharing.")
        
        # Lock in the results for lower tiers
        for div, fixtures in cluster_res.items():
            for d, h, a in fixtures:
                r_idx = date_slots.index(d)
                v = ground_assignments.get(h)
                if v: locked_grounds[r_idx][v] = True
        all_scheds.update(cluster_res)
        
    return {"schedules": all_scheds}