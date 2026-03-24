from datetime import date, timedelta
import csv
import pulp

def generate_round_robin(teams):
    """Berger rotation (circle method)"""
    team_list = list(teams)
    if len(team_list) % 2 == 1:
        team_list.append("BYE")
    n = len(team_list)
    first_half = []
    for _ in range(n - 1):
        rnd = []
        for i in range(n // 2):
            home = team_list[i]
            away = team_list[n - 1 - i]
            if home != "BYE" and away != "BYE":
                rnd.append((home, away))
        first_half.append(rnd)
        team_list = [team_list[0]] + [team_list[-1]] + team_list[1:-1]
    second_half = [[(away, home) for home, away in rnd] for rnd in first_half]
    # Interleave
    interleaved = []
    for f, s in zip(first_half, second_half):
        interleaved.append(f)
        interleaved.append(s)
    return interleaved

def assign_dates_ilp(rounds, start_date, blackout_dates=[], interval_days=7):
    """
    Assign rounds to dates using ILP so that:
    - Each team plays max 1 game per day
    - All rounds are scheduled
    - Rounds are spaced by interval_days and skip blackout_dates
    """

    teams = set()
    for rnd in rounds:
        for h, a in rnd:
            teams.add(h)
            teams.add(a)
    teams = list(teams)

    num_rounds = len(rounds)
    # Generate candidate dates
    dates = []
    current = start_date
    while len(dates) < num_rounds * 2:  # overestimate
        if current not in blackout_dates:
            dates.append(current)
        current += timedelta(days=interval_days)
    dates = dates[:num_rounds]  # only need as many as rounds

    # ILP variables: x[r, d] = 1 if round r is on date d
    x = pulp.LpVariable.dicts(
        "x",
        ((r, d) for r in range(num_rounds) for d in dates),
        cat="Binary"
    )

    prob = pulp.LpProblem("ScheduleRounds", pulp.LpMinimize)
    # Objective: arbitrary (we just need feasible)
    prob += 0

    # Each round is scheduled exactly once
    for r in range(num_rounds):
        prob += pulp.lpSum(x[r, d] for d in dates) == 1

    # Each team plays max 1 game per day
    for d in dates:
        for team in teams:
            prob += pulp.lpSum(
                x[r, d] for r, rnd in enumerate(rounds)
                if any(team in match for match in rnd)
            ) <= 1

    prob.solve(pulp.PULP_CBC_CMD(msg=0))

    # Map rounds to dates
    schedule = []
    for r, rnd in enumerate(rounds):
        for d in dates:
            if pulp.value(x[r, d]) == 1:
                schedule.append((d, rnd))
                break
    schedule.sort(key=lambda x: x[0])
    return schedule

def flip_home_away(schedule):
    """
    Flip home/away to balance and prevent 3 consecutive H/A.
    Linear ILP approximation
    """
    # Flatten rounds
    rounds = [rnd for _, rnd in schedule]
    teams = set()
    for rnd in rounds:
        for h, a in rnd:
            teams.add(h)
            teams.add(a)
    teams = list(teams)

    num_rounds = len(rounds)
    prob = pulp.LpProblem("HomeAwayBalancing", pulp.LpMinimize)

    flip = pulp.LpVariable.dicts("flip", range(num_rounds), cat="Binary")
    home_count = {t: [] for t in teams}
    for r, rnd in enumerate(rounds):
        for h, a in rnd:
            home_count[h].append(1 - flip[r])
            home_count[a].append(flip[r])

    total_games = len(teams) - 1
    target_home = total_games / 2
    deviation = {}
    for t in teams:
        deviation[t] = pulp.LpVariable(f"dev_{t}", lowBound=0)
        prob += pulp.lpSum(home_count[t]) - target_home <= deviation[t]
        prob += target_home - pulp.lpSum(home_count[t]) <= deviation[t]

    # No 3 consecutive home/away
    for t in teams:
        for r in range(num_rounds - 2):
            prob += home_count[t][r] + home_count[t][r+1] + home_count[t][r+2] <= 2
            prob += (1 - home_count[t][r]) + (1 - home_count[t][r+1]) + (1 - home_count[t][r+2]) <= 2

    prob += pulp.lpSum(deviation[t] for t in teams)
    prob.solve(pulp.PULP_CBC_CMD(msg=0))

    # Apply flips
    new_schedule = []
    for (d, rnd), r in zip(schedule, range(num_rounds)):
        if pulp.value(flip[r]) == 1:
            new_rnd = [(a, h) for h, a in rnd]
        else:
            new_rnd = rnd
        new_schedule.append((d, new_rnd))
    return new_schedule

def assign_dates(rounds, start_date, blackout_dates=[], interval_days=7):
    schedule = assign_dates_ilp(rounds, start_date, blackout_dates, interval_days)
    schedule = flip_home_away(schedule)
    # Flatten into (date, home, away) tuples
    flat_schedule = []
    for d, rnd in schedule:
        for h, a in rnd:
            flat_schedule.append((d, h, a))
    flat_schedule.sort(key=lambda x: x[0])
    return flat_schedule

def reschedule_game(schedule, home_team, away_team, new_date):
    updated_schedule = []
    rescheduled = False
    for game in schedule:
        if game[1].lower() == home_team.lower() and game[2].lower() == away_team.lower():
            updated_schedule.append((new_date, game[1], game[2]))
            rescheduled = True
        else:
            updated_schedule.append(game)
    updated_schedule.sort(key=lambda x: x[0])
    return updated_schedule, rescheduled

def resolve_ground_conflicts(schedule, ground_assignments):
    updated_schedule = list(schedule)
    dates = sorted(set(game[0] for game in updated_schedule))
    for match_date in dates:
        games_on_date = [g for g in updated_schedule if g[0] == match_date]
        grounds_used = {}
        for game in games_on_date:
            home_team = game[1]
            ground = ground_assignments.get(home_team)
            if ground:
                if ground in grounds_used:
                    idx = updated_schedule.index(game)
                    next_date = match_date + timedelta(days=7)
                    updated_schedule[idx] = (next_date, game[1], game[2])
                else:
                    grounds_used[ground] = home_team
    updated_schedule.sort(key=lambda x: x[0])
    return updated_schedule