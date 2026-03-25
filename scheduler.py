"""
Fixture Scheduling Engine — Double Round-Robin + OR-Tools CP-SAT
================================================================
Pipeline (per the design document):
  1. generate_double_round_robin()   — pure structure, no dates assigned
  2. schedule_leagues_or_tools()     — CP-SAT assigns rounds to dates

Constraints
-----------
  C1  Each round on exactly one date                         (hard)
  C2  At most one round per league per date                  (hard)
  C4  No team plays more than 2 consecutive home or away     (hard)
  C3  Shared-venue teams cannot both be home same date       (soft - minimised)

Full rounds and streak-balance are guaranteed.
Ground conflicts are minimised; any unavoidable residual ones are
returned alongside the schedule so the caller can surface them.
"""

from datetime import date, timedelta
from collections import defaultdict
import csv


# ── 1. Double Round-Robin Generator ─────────────────────────────────────────

def generate_double_round_robin(teams: list) -> list:
    """Return all matches for a double round-robin using the circle method.

    Returns a list of match dicts:
        {"id": int, "home": str, "away": str, "round": int}

    Total rounds = 2 * (n-1).  Every round has exactly n//2 fixtures.
    Second half is the home/away inverse of the first half.
    """
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
            matches.append({
                "id":    match_id,
                "home":  m["away"],
                "away":  m["home"],
                "round": r_idx + offset,
            })
            match_id += 1

    return matches


# ── 2. OR-Tools CP-SAT Scheduler ────────────────────────────────────────────

def schedule_leagues_or_tools(
    leagues: list,
    start_date,
    blackout_dates: list = [],
    ground_assignments: dict = {},
    time_limit_seconds: int = 60,
) -> dict:
    """Assign rounds to dates across multiple leagues using CP-SAT.

    Parameters
    ----------
    leagues            : list of {"name": str, "teams": list[str]}
    start_date         : datetime.date
    blackout_dates     : list of datetime.date  -- weeks to skip
    ground_assignments : dict  team_name -> venue_name
    time_limit_seconds : int

    Returns
    -------
    dict {
        "schedules":  {league_name: [(date, home, away), ...]},
        "conflicts":  [{"date", "ground", "team1", "league1",
                        "team2", "league2"}, ...]
    }
    """
    from ortools.sat.python import cp_model

    # Step 1: Generate all matches
    all_matches, league_num_rounds = [], {}
    match_id = 0
    for li, league in enumerate(leagues):
        raw    = generate_double_round_robin(league["teams"])
        n_rnds = max(m["round"] for m in raw) + 1
        league_num_rounds[league["name"]] = n_rnds
        for m in raw:
            all_matches.append({**m, "id": match_id,
                                 "league": league["name"], "league_idx": li})
            match_id += 1

    # Step 2: Build exactly max_rounds non-blackout date slots.
    # Providing exactly this many slots forces every slot to be used so
    # consecutive slot index == consecutive game -- required for C4.
    blackout_set = set(blackout_dates)
    max_rounds   = max(league_num_rounds.values())
    slots, d     = [], start_date
    while len(slots) < max_rounds:
        if d not in blackout_set:
            slots.append(d)
        d += timedelta(days=7)
    ND = len(slots)

    # Step 3: Precompute lookup tables
    round_home_teams = defaultdict(list)
    for m in all_matches:
        round_home_teams[(m["league"], m["round"])].append(m["home"])

    ground_to_teams = defaultdict(list)
    for team, venue in ground_assignments.items():
        if team not in ground_to_teams[venue]:
            ground_to_teams[venue].append(team)
    shared_groups = {v: t for v, t in ground_to_teams.items() if len(t) >= 2}

    team_home_rounds = defaultdict(list)
    team_away_rounds = defaultdict(list)
    for m in all_matches:
        team_home_rounds[m["home"]].append((m["league"], m["round"]))
        team_away_rounds[m["away"]].append((m["league"], m["round"]))

    all_team_list = [t for lg in leagues for t in lg["teams"]]

    # Step 4: Build CP-SAT model
    model = cp_model.CpModel()

    # Decision variables: y[(league, round, date_idx)] in {0, 1}
    y = {}
    for league in leagues:
        name = league["name"]
        for r in range(league_num_rounds[name]):
            for di in range(ND):
                y[(name, r, di)] = model.NewBoolVar(f"y_{name}_{r}_{di}")

    # C1 -- Each round assigned to exactly one date
    for league in leagues:
        name = league["name"]
        for r in range(league_num_rounds[name]):
            model.AddExactlyOne(y[(name, r, di)] for di in range(ND))

    # C2 -- At most one round per league per date (guarantees full rounds)
    for league in leagues:
        name = league["name"]
        for di in range(ND):
            model.AddAtMostOne(y[(name, r, di)] for r in range(league_num_rounds[name]))

    # C4 -- Streak constraint (HARD): no team plays 3+ consecutive home or away.
    # Correct because all slots are used with no gaps, so slot index == game position.
    for team in all_team_list:
        h_rounds = team_home_rounds[team]
        a_rounds = team_away_rounds[team]
        for di in range(ND - 2):
            model.Add(sum(
                y[(lg, r, di)] + y[(lg, r, di+1)] + y[(lg, r, di+2)]
                for lg, r in h_rounds
            ) <= 2)
            model.Add(sum(
                y[(lg, r, di)] + y[(lg, r, di+1)] + y[(lg, r, di+2)]
                for lg, r in a_rounds
            ) <= 2)

    # C3 -- Shared-venue constraint (SOFT): minimised in objective.
    # Cannot always be fully satisfied alongside C4, so violations are
    # minimised and surfaced as warnings rather than causing infeasibility.
    conflict_vars = []
    for venue, group_teams in shared_groups.items():
        group_set = set(group_teams)
        for di in range(ND):
            terms = []
            for league in leagues:
                name = league["name"]
                for r in range(league_num_rounds[name]):
                    cnt = sum(1 for t in round_home_teams[(name, r)] if t in group_set)
                    if cnt > 0:
                        terms.append(y[(name, r, di)] * cnt)
            if terms:
                pv = model.NewBoolVar(f"conf_{venue}_{di}")
                model.Add(sum(terms) - 1 <= len(terms) * pv)
                conflict_vars.append(pv)

    if conflict_vars:
        model.Minimize(sum(conflict_vars))

    # Step 5: Solve
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_seconds
    solver.parameters.num_workers         = 8
    solver.parameters.log_search_progress = False

    status = solver.Solve(model)

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        raise RuntimeError(
            "OR-Tools could not find a feasible schedule. "
            "Try adjusting blackout dates or team counts."
        )

    # Step 6: Extract schedule
    round_to_date = {}
    for league in leagues:
        name = league["name"]
        for r in range(league_num_rounds[name]):
            for di in range(ND):
                if solver.Value(y[(name, r, di)]) == 1:
                    round_to_date[(name, r)] = slots[di]
                    break

    schedules = {league["name"]: [] for league in leagues}
    for m in all_matches:
        assigned = round_to_date[(m["league"], m["round"])]
        schedules[m["league"]].append((assigned, m["home"], m["away"]))

    for name in schedules:
        schedules[name].sort(key=lambda g: g[0])

    # Step 7: Detect residual ground conflicts
    all_home_by_date = defaultdict(list)
    for name, sched in schedules.items():
        for d_game, home, away in sched:
            all_home_by_date[d_game].append((home, name))

    remaining_conflicts = []
    for d_game, entries in sorted(all_home_by_date.items()):
        seen_grounds = {}
        for team, lg_name in entries:
            g = ground_assignments.get(team)
            if g:
                if g in seen_grounds:
                    remaining_conflicts.append({
                        "date":    d_game,
                        "ground":  g,
                        "team1":   seen_grounds[g][0],
                        "league1": seen_grounds[g][1],
                        "team2":   team,
                        "league2": lg_name,
                    })
                else:
                    seen_grounds[g] = (team, lg_name)

    return {"schedules": schedules, "conflicts": remaining_conflicts}


# ── Legacy shims ──────────────────────────────────────────────────────────────

def generate_round_robin(teams):
    matches  = generate_double_round_robin(teams)
    n_rounds = max(m["round"] for m in matches) + 1
    rounds   = [[] for _ in range(n_rounds)]
    for m in matches:
        rounds[m["round"]].append((m["home"], m["away"]))
    return rounds

def group_into_rounds(fixtures, teams):
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
    updated = list(schedule)
    for match_date in sorted(set(g[0] for g in updated)):
        grounds_used = {}
        for game in [g for g in updated if g[0] == match_date]:
            ground = ground_assignments.get(game[1])
            if ground:
                if ground in grounds_used:
                    idx = updated.index(game)
                    updated[idx] = (match_date + timedelta(days=7), game[1], game[2])
                else:
                    grounds_used[ground] = game[1]
    updated.sort(key=lambda x: x[0])
    return updated


# ── CLI helpers ───────────────────────────────────────────────────────────────

def check_home_away_balance(schedule, teams):
    print("\n--- Home/Away Balance ---")
    for team in teams:
        h = sum(1 for g in schedule if g[1] == team)
        a = sum(1 for g in schedule if g[2] == team)
        print(f"  {team}: {h}H {a}A")

def print_schedule_by_round(schedule, teams):
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


# ── CLI entry point ───────────────────────────────────────────────────────────

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

    print("Solving with OR-Tools CP-SAT...")
    result = schedule_leagues_or_tools(
        leagues, date(2025, 4, 5), blackout_dates, ground_assignments
    )

    for league in leagues:
        name = league["name"]
        print(f"\n{'='*55}\n{name}\n{'='*55}")
        print_schedule_by_round(result["schedules"][name], league["teams"])
        check_home_away_balance(result["schedules"][name], league["teams"])
        export_to_csv(result["schedules"][name], f"{name.lower().replace(' ','_')}.csv")

    if result["conflicts"]:
        print(f"\nWARNING: {len(result['conflicts'])} unavoidable ground conflict(s):")
        for c in result["conflicts"]:
            print(f"  {c['date']} -- {c['ground']}: "
                  f"{c['team1']} ({c['league1']}) & {c['team2']} ({c['league2']})")
    else:
        print("\nNo ground conflicts")
