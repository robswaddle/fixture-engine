from datetime import date, timedelta
import csv


def generate_round_robin(teams):
    """Return a list of rounds using the circle/polygon algorithm.

    Each round is a list of (home, away) tuples.  Every round is guaranteed
    to be full (n//2 fixtures) — no team appears twice in the same round.
    A double round-robin is produced: the second half mirrors the first with
    home/away swapped so every pair meets twice, once at each ground.

    If the number of teams is odd a BYE is inserted temporarily and removed
    from the output.
    """
    team_list = list(teams)
    bye_inserted = False
    if len(team_list) % 2 == 1:
        team_list.append("BYE")
        bye_inserted = True

    n = len(team_list)
    first_half = []

    # Fix the last team; rotate the rest clockwise each round
    for round_idx in range(n - 1):
        round_fixtures = []
        for i in range(n // 2):
            home = team_list[i]
            away = team_list[n - 1 - i]
            # Alternate which side gets home advantage each round for the
            # fixed-slot pair so the BYE (if any) is easy to filter
            if home != "BYE" and away != "BYE":
                round_fixtures.append((home, away))
        first_half.append(round_fixtures)
        # Rotate: index 0 is fixed, rotate positions 1..n-1
        team_list = [team_list[0]] + [team_list[-1]] + team_list[1:-1]

    # Second half: swap home/away for every fixture
    second_half = [[(away, home) for home, away in rnd] for rnd in first_half]

    return first_half + second_half


def group_into_rounds(fixtures, teams):
    """Pass-through: generate_round_robin already returns full rounds.

    Kept for backwards-compatibility — fixtures is expected to already be a
    list of rounds (list of lists) as returned by generate_round_robin.
    """
    return fixtures


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

    fixtures = generate_round_robin(teams)
    rounds = group_into_rounds(fixtures, teams)
    start = date(2025, 4, 5)
    schedule = assign_dates(rounds, start, blackout_dates)

    print_schedule_by_round(schedule, teams)
    check_home_away_balance(schedule, teams)
    export_to_csv(schedule)