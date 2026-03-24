from datetime import date, timedelta
import csv
import itertools
import pulp


# -------------------------------
# BERGER (unchanged)
# -------------------------------
def generate_round_robin(teams):
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

    interleaved = []
    for f, s in zip(first_half, second_half):
        interleaved.append(f)
        interleaved.append(s)

    return interleaved


# -------------------------------
# ILP ADJUSTMENT ENGINE
# -------------------------------
def adjust_schedule_with_ilp(rounds, teams):
    """
    SAFE ILP:
    - Keeps Berger structure
    - Balances home/away (linear)
    - Prevents 3 consecutive home/away
    """

    import pulp

    num_rounds = len(rounds)

    prob = pulp.LpProblem("HomeAwayBalancing", pulp.LpMinimize)

    # Flip per round (0 = original, 1 = flipped)
    flip = pulp.LpVariable.dicts(
        "flip",
        range(num_rounds),
        cat="Binary"
    )

    # Track home games
    home_count = {team: [] for team in teams}

    for r, rnd in enumerate(rounds):
        for (h, a) in rnd:
            home_count[h].append(1 - flip[r])
            home_count[a].append(flip[r])

    # -------------------------------
    # LINEAR BALANCING (no squares)
    # -------------------------------
    total_games = len(teams) - 1
    target_home = total_games / 2

    deviation = {}

    for team in teams:
        deviation[team] = pulp.LpVariable(f"dev_{team}", lowBound=0)

        prob += pulp.lpSum(home_count[team]) - target_home <= deviation[team]
        prob += target_home - pulp.lpSum(home_count[team]) <= deviation[team]

    # Objective: minimize total deviation
    prob += pulp.lpSum(deviation[team] for team in teams)

    # -------------------------------
    # NO 3 CONSECUTIVE HOME/AWAY
    # -------------------------------
    for team in teams:
        for r in range(num_rounds - 2):

            # Home streak
            prob += (
                home_count[team][r] +
                home_count[team][r + 1] +
                home_count[team][r + 2]
            ) <= 2

            # Away streak
            prob += (
                (1 - home_count[team][r]) +
                (1 - home_count[team][r + 1]) +
                (1 - home_count[team][r + 2])
            ) <= 2

    # Solve
    prob.solve(pulp.PULP_CBC_CMD(msg=0))

    # -------------------------------
    # APPLY RESULTS
    # -------------------------------
    new_rounds = []

    for r, rnd in enumerate(rounds):
        new_rnd = []
        for (h, a) in rnd:
            if pulp.value(flip[r]) == 1:
                new_rnd.append((a, h))
            else:
                new_rnd.append((h, a))
        new_rounds.append(new_rnd)

    return new_rounds


# -------------------------------
# EXISTING FUNCTIONS (unchanged)
# -------------------------------
def assign_dates(rounds, start_date, blackout_dates=[], interval_days=7):
    schedule = []
    current_date = start_date

    for round_fixtures in rounds:
        while current_date in blackout_dates:
            current_date += timedelta(days=interval_days)

        for fixture in round_fixtures:
            schedule.append((current_date, fixture[0], fixture[1]))

        current_date += timedelta(days=interval_days)

    return schedule


def check_home_away_balance(schedule, teams):
    print("\n--- Home/Away Balance Report ---")
    for team in teams:
        home_games = sum(1 for game in schedule if game[1] == team)
        away_games = sum(1 for game in schedule if game[2] == team)
        print(f"{team}: {home_games} home, {away_games} away")


def print_schedule_by_round(schedule, teams):
    print("\n--- Full Season Schedule ---")
    current_date = None
    round_number = 1

    for game in schedule:
        if game[0] != current_date:
            current_date = game[0]
            print(f"\nRound {round_number} — {current_date.strftime('%A %d %B %Y')}")
            round_number += 1
        print(f"  {game[1]} vs {game[2]}")


def export_to_csv(schedule, filename="fixtures.csv"):
    with open(filename, "w", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(["Date", "Home Team", "Away Team"])
        for game in schedule:
            writer.writerow([game[0].strftime("%d/%m/%Y"), game[1], game[2]])
    print(f"\nSchedule exported to {filename}")

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

# -------------------------------
# MAIN
# -------------------------------
if __name__ == "__main__":
    teams = [
        "Ashington CC",
        "Blyth CC",
        "Morpeth CC",
        "Alnwick CC",
        "Tynemouth CC",
        "Bedlington CC"
    ]

    blackout_dates = [
        date(2025, 4, 19),
        date(2025, 5, 3),
        date(2025, 5, 26),
    ]

    # Step 1: Berger
    berger_rounds = generate_round_robin(teams)

    # Step 2: ILP adjustment
    rounds = adjust_schedule_with_ilp(berger_rounds, teams)

    # Step 3: Assign dates
    start = date(2025, 4, 5)
    schedule = assign_dates(rounds, start, blackout_dates)

    # Output
    print_schedule_by_round(schedule, teams)
    check_home_away_balance(schedule, teams)
    export_to_csv(schedule)