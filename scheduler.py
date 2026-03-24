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
    num_rounds = len(rounds)
    matches = list(itertools.combinations(teams, 2))

    def normalize(m):
        return tuple(sorted(m))

    # Map Berger baseline
    berger_map = {}
    for r, rnd in enumerate(rounds):
        for (h, a) in rnd:
            berger_map[(normalize((h, a)), r)] = (h, a)

    prob = pulp.LpProblem("FixtureAdjustment", pulp.LpMinimize)

    # Decision variables
    x = pulp.LpVariable.dicts(
        "match",
        ((i, j, r) for (i, j) in matches for r in range(num_rounds)),
        cat="Binary"
    )

    # Home indicator
    home = pulp.LpVariable.dicts(
        "home",
        ((team, r) for team in teams for r in range(num_rounds)),
        cat="Binary"
    )

    # -------------------------------
    # OBJECTIVE: stay close to Berger
    # -------------------------------
    prob += pulp.lpSum(
        0 if berger_map.get((normalize((i, j)), r)) else 1 * x[(i, j, r)]
        for (i, j) in matches
        for r in range(num_rounds)
    )

    # -------------------------------
    # CONSTRAINTS
    # -------------------------------

    # Each pair plays once
    for (i, j) in matches:
        prob += pulp.lpSum(x[(i, j, r)] for r in range(num_rounds)) == 1

    # Each team plays once per round
    for team in teams:
        for r in range(num_rounds):
            prob += pulp.lpSum(
                x[(i, j, r)]
                for (i, j) in matches
                if i == team or j == team
            ) == 1

    # Link match → home variable
    for r in range(num_rounds):
        for team in teams:
            prob += home[(team, r)] == pulp.lpSum(
                x[(i, j, r)] if i == team else 0
                for (i, j) in matches
            )

    # -------------------------------
    # 1️⃣ HOME/AWAY BALANCING
    # -------------------------------
    total_games = len(teams) - 1  # single round robin
    min_home = total_games // 2
    max_home = min_home + 1

    for team in teams:
        prob += pulp.lpSum(home[(team, r)] for r in range(num_rounds)) >= min_home
        prob += pulp.lpSum(home[(team, r)] for r in range(num_rounds)) <= max_home

    # -------------------------------
    # 2️⃣ NO 3 CONSECUTIVE HOME/AWAY
    # -------------------------------
    for team in teams:
        for r in range(num_rounds - 2):
            # No 3 home in a row
            prob += (
                home[(team, r)] +
                home[(team, r + 1)] +
                home[(team, r + 2)]
            ) <= 2

            # No 3 away in a row
            prob += (
                (1 - home[(team, r)]) +
                (1 - home[(team, r + 1)]) +
                (1 - home[(team, r + 2)])
            ) <= 2

    # Solve
    prob.solve(pulp.PULP_CBC_CMD(msg=0))

    # -------------------------------
    # BUILD NEW SCHEDULE
    # -------------------------------
    new_rounds = [[] for _ in range(num_rounds)]

    for (i, j) in matches:
        for r in range(num_rounds):
            if pulp.value(x[(i, j, r)]) == 1:
                # Assign home/away based on variable
                if pulp.value(home[(i, r)]) == 1:
                    new_rounds[r].append((i, j))
                else:
                    new_rounds[r].append((j, i))

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