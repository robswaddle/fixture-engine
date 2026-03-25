from datetime import date, timedelta
import csv


def generate_round_robin(teams):
    """Return a balanced list of rounds using the circle/polygon algorithm.

    Rounds are interleaved (first-half round 1, second-half round 1, etc.)
    so that home/away alternates as evenly as possible — no team will ever
    have more than 2 consecutive home or away games.

    Every round is guaranteed to be full (n//2 fixtures).
    """
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

    # Interleave first and second halves so H/A alternates cleanly
    interleaved = []
    for f, s in zip(first_half, second_half):
        interleaved.append(f)
        interleaved.append(s)
    return interleaved


def group_into_rounds(fixtures, teams):
    """Pass-through kept for backwards-compatibility.

    generate_round_robin now returns fully balanced rounds directly.
    """
    return fixtures


def assign_dates(rounds, start_date, blackout_dates=[], interval_days=7):
    """Single-league date assignment (used when ground sharing is off)."""
    schedule = []
    current_date = start_date

    for round_fixtures in rounds:
        while current_date in blackout_dates:
            current_date += timedelta(days=interval_days)
        for fixture in round_fixtures:
            schedule.append((current_date, fixture[0], fixture[1]))
        current_date += timedelta(days=interval_days)

    return schedule


def assign_dates_multi_league(leagues_rounds, start_date, blackout_dates=[],
                               ground_assignments={}, interval_days=7):
    """Assign dates to rounds across multiple leagues simultaneously.

    Uses the linear assignment algorithm to find the globally optimal pairing
    of rounds across leagues before touching dates, so full rounds are always
    preserved and cross-league ground conflicts are minimised.

    leagues_rounds : list of (league_name, rounds)
    Returns        : dict {league_name: [(date, home, away), ...]}
    """
    from collections import defaultdict

    def combo_conflicts(rounds_combo):
        """Ground conflicts when these rounds all fall on the same date."""
        home_teams = [home for rnd in rounds_combo for home, _ in rnd]
        conflicts = 0
        for i in range(len(home_teams)):
            gi = ground_assignments.get(home_teams[i])
            if not gi:
                continue
            for j in range(i + 1, len(home_teams)):
                if ground_assignments.get(home_teams[j]) == gi:
                    conflicts += 1
        return conflicts

    league_names = [name for name, _ in leagues_rounds]
    all_rounds   = [list(rounds) for _, rounds in leagues_rounds]
    n_leagues    = len(leagues_rounds)

    # ── For exactly 2 leagues use the linear assignment algorithm ──────────
    # Build a conflict cost matrix: cost[i][j] = conflicts if league-0 round i
    # is paired with league-1 round j on the same date.  Then find the
    # minimum-cost perfect assignment and order paired rounds chronologically.
    if n_leagues == 2:
        try:
            import numpy as np
            from scipy.optimize import linear_sum_assignment

            r0, r1 = all_rounds[0], all_rounds[1]
            n = max(len(r0), len(r1))

            # Pad shorter list with empty rounds so the matrix is square
            r0_padded = r0 + [[]] * (n - len(r0))
            r1_padded = r1 + [[]] * (n - len(r1))

            cost = np.zeros((n, n), dtype=int)
            for i, rnd0 in enumerate(r0_padded):
                for j, rnd1 in enumerate(r1_padded):
                    cost[i, j] = combo_conflicts([rnd0, rnd1]) if rnd0 and rnd1 else 0

            row_ind, col_ind = linear_sum_assignment(cost)

            # Reorder both leagues' rounds according to the optimal assignment
            ordered0 = [r0_padded[i] for i in row_ind if r0_padded[i]]
            ordered1 = [r1_padded[col_ind[k]] for k, i in enumerate(row_ind)
                        if r0_padded[i]]  # match ordering of ordered0
            # Any r1 rounds that ended up paired with empty r0 slots go at the end
            used1 = set(col_ind)
            leftover1 = [r1_padded[j] for j in range(n)
                         if j not in used1 and r1_padded[j]]
            ordered1 += leftover1

            paired = list(zip(ordered0, ordered1))
            extra0 = ordered0[len(paired):]
            extra1 = ordered1[len(paired):]

            # Assign dates to paired rounds
            schedules = {name: [] for name in league_names}
            current_date = start_date
            for rnd0, rnd1 in paired:
                while current_date in blackout_dates:
                    current_date += timedelta(days=interval_days)
                for home, away in rnd0:
                    schedules[league_names[0]].append((current_date, home, away))
                for home, away in rnd1:
                    schedules[league_names[1]].append((current_date, home, away))
                current_date += timedelta(days=interval_days)
            # Any leftover rounds (unequal league lengths) get tacked on
            for rnd in extra0:
                while current_date in blackout_dates:
                    current_date += timedelta(days=interval_days)
                for home, away in rnd:
                    schedules[league_names[0]].append((current_date, home, away))
                current_date += timedelta(days=interval_days)
            for rnd in extra1:
                while current_date in blackout_dates:
                    current_date += timedelta(days=interval_days)
                for home, away in rnd:
                    schedules[league_names[1]].append((current_date, home, away))
                current_date += timedelta(days=interval_days)
            return schedules

        except ImportError:
            pass  # fall through to greedy below

    # ── Greedy fallback for 3+ leagues (or if scipy not installed) ─────────
    import itertools
    remaining    = [list(rounds) for rounds in all_rounds]
    schedules    = {name: [] for name in league_names}
    current_date = start_date

    while any(rem for rem in remaining):
        while current_date in blackout_dates:
            current_date += timedelta(days=interval_days)

        active = [i for i in range(n_leagues) if remaining[i]]
        best_combo_indices = None
        best_score = float("inf")

        if len(active) <= 3:
            for idx_tuple in itertools.product(*[range(len(remaining[i])) for i in active]):
                rounds_combo = [remaining[active[k]][idx_tuple[k]] for k in range(len(active))]
                score = combo_conflicts(rounds_combo)
                if score < best_score:
                    best_score = score
                    best_combo_indices = idx_tuple
                if best_score == 0:
                    break
        else:
            chosen_rounds  = []
            chosen_indices = []
            for i in active:
                best_idx   = 0
                best_local = float("inf")
                for idx, candidate in enumerate(remaining[i]):
                    score = combo_conflicts(chosen_rounds + [candidate])
                    if score < best_local:
                        best_local = score
                        best_idx   = idx
                    if best_local == 0:
                        break
                chosen_rounds.append(remaining[i][best_idx])
                chosen_indices.append(best_idx)
            best_combo_indices = tuple(chosen_indices)

        for k, i in enumerate(active):
            chosen_round = remaining[i][best_combo_indices[k]]
            for home, away in chosen_round:
                schedules[league_names[i]].append((current_date, home, away))
            remaining[i].remove(chosen_round)

        current_date += timedelta(days=interval_days)

    return schedules

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
    division_1 = [
        "Burnmoor 1st XI",
        "South Northumberland 1st XI",
        "Castle Eden 1st XI",
        "Felling 1st XI",
        "Chester Le Street 1st XI",
        "Hetton Lyons 1st XI",
        "Burnopfield 1st XI",
        "Newcastle 1st XI",
        "Ashington 1st XI",
        "Shotley Bridge 1st XI",
        "Benwell Hill 1st XI",
        "Seaham Harbour 1st XI",
    ]

    division_2 = [
        "Felling 2nd XI",
        "Newcastle City CC 2nd XI",
        "Chester Le Street 2nd XI",
        "Ashington 2nd XI",
        "South Northumberland 2nd XI",
        "Newcastle 2nd XI",
        "Tynemouth 2nd XI",
        "Benwell Hill 2nd XI",
        "Tynedale 2nd XI",
        "Hetton Lyons 2nd XI",
        "Whitburn 2nd XI",
        "Castle Eden 2nd XI",
    ]

    blackout_dates = [
        date(2025, 4, 19),
        date(2025, 5, 3),
        date(2025, 5, 26),
    ]

    start = date(2025, 4, 5)

    for name, teams in [("Division 1", division_1), ("Division 2", division_2)]:
        print(f"\n{'='*50}\n{name}\n{'='*50}")
        fixtures = generate_round_robin(teams)
        rounds = group_into_rounds(fixtures, teams)
        schedule = assign_dates(rounds, start, blackout_dates)
        print_schedule_by_round(schedule, teams)
        check_home_away_balance(schedule, teams)
        export_to_csv(schedule, filename=f"{name.lower().replace(' ', '_')}_fixtures.csv")
