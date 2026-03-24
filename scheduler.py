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

    # All possible directed matches
    matches = [(i, j) for i in teams for j in teams if i != j]

    prob = pulp.LpProblem("FixtureAdjustment", pulp.LpMinimize)

    # Decision variable: team i plays at home vs j in round r
    x = pulp.LpVariable.dicts(
        "match",
        ((i, j, r) for (i, j) in matches for r in range(num_rounds)),
        cat="Binary"
    )

    # -------------------------------
    # OBJECTIVE (optional: keep simple)
    # -------------------------------
    prob += 0

    # -------------------------------
    # CONSTRAINTS
    # -------------------------------

    # 1️⃣ Each pair plays exactly once
    for i in teams:
        for j in teams:
            if i < j:
                prob += pulp.lpSum(
                    x[(i, j, r)] + x[(j, i, r)]
                    for r in range(num_rounds)
                ) == 1

    # 2️⃣ Each team plays exactly once per round
    for team in teams:
        for r in range(num_rounds):
            prob += pulp.lpSum(
                x[(team, opp, r)] + x[(opp, team, r)]
                for opp in teams if opp != team
            ) == 1

    # -------------------------------
    # 3️⃣ HOME/AWAY BALANCE
    # -------------------------------
    total_games = len(teams) - 1
    min_home = total_games // 2
    max_home = min_home + 1

    for team in teams:
        prob += pulp.lpSum(
            x[(team, opp, r)]
            for opp in teams if opp != team
            for r in range(num_rounds)
        ) >= min_home

        prob += pulp.lpSum(
            x[(team, opp, r)]
            for opp in teams if opp != team
            for r in range(num_rounds)
        ) <= max_home

    # -------------------------------
    # 4️⃣ NO 3 CONSECUTIVE HOME/AWAY
    # -------------------------------
    for team in teams:
        for r in range(num_rounds - 2):

            # Home streak
            prob += pulp.lpSum(
                x[(team, opp, rr)]
                for opp in teams if opp != team
                for rr in [r, r+1, r+2]
            ) <= 2

            # Away streak
            prob += pulp.lpSum(
                x[(opp, team, rr)]
                for opp in teams if opp != team
                for rr in [r, r+1, r+2]
            ) <= 2

    # Solve
    prob.solve(pulp.PULP_CBC_CMD(msg=0))

    # -------------------------------
    # BUILD SCHEDULE
    # -------------------------------
    new_rounds = [[] for _ in range(num_rounds)]

    for (i, j) in matches:
        for r in range(num_rounds):
            if pulp.value(x[(i, j, r)]) == 1:
                new_rounds[r].append((i, j))

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