import streamlit as st
from datetime import date
from scheduler import generate_round_robin, assign_dates, reschedule_game, resolve_ground_conflicts
import google.generativeai as genai
from dotenv import load_dotenv
import os
import csv
import io

load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel("gemini-2.5-flash-lite")

st.set_page_config(
    page_title="FixtureAI",
    page_icon="🏏",
    layout="wide"
)

# ── Styles and header omitted for brevity, same as your current app.py ──

# ── Helpers ──────────────────────────────────────────────────────────────────
def detect_shared_grounds(league_configs):
    SUFFIXES = {"1st","2nd","3rd","4th","5th","xi","xii","1sts","2nds","3rds","4ths","a","b","c"}
    def base_name(team: str) -> str:
        words = team.lower().split()
        while words and words[-1] in SUFFIXES:
            words.pop()
        return " ".join(words)

    all_teams = []
    for cfg in league_configs:
        for t in cfg["teams_raw"].split("\n"):
            t = t.strip()
            if t:
                all_teams.append(t)

    from collections import defaultdict
    groups: dict = defaultdict(list)
    for team in all_teams:
        bn = base_name(team)
        if bn:
            groups[bn].append(team)

    pairs = []
    for group in groups.values():
        if len(group) >= 2:
            for i in range(len(group)):
                for j in range(i + 1, len(group)):
                    pairs.append(f"{group[i]}, {group[j]}")

    return "\n".join(pairs)


def resolve_ground_conflicts_global(leagues_data: dict, ground_assignments: dict) -> dict:
    from datetime import timedelta
    from collections import defaultdict

    ground_to_teams: dict = defaultdict(list)
    for team, ground in ground_assignments.items():
        if team not in ground_to_teams[ground]:
            ground_to_teams[ground].append(team)

    max_iterations = 200
    iteration = 0

    while iteration < max_iterations:
        iteration += 1
        conflict_found = False

        for ground, sharing_teams in ground_to_teams.items():
            for i in range(len(sharing_teams)):
                for j in range(i + 1, len(sharing_teams)):
                    team_a = sharing_teams[i]
                    team_b = sharing_teams[j]

                    home_dates_a = set()
                    home_dates_b = set()
                    for league_data in leagues_data.values():
                        for game in league_data["schedule"]:
                            if game[1] == team_a: home_dates_a.add(game[0])
                            if game[1] == team_b: home_dates_b.add(game[0])

                    clashing_dates = home_dates_a & home_dates_b
                    if not clashing_dates:
                        continue

                    conflict_found = True
                    clash_date = sorted(clashing_dates)[0]

                    for league_name, league_data in leagues_data.items():
                        new_schedule = []
                        for game in league_data["schedule"]:
                            if game[1] == team_b and game[0] == clash_date:
                                new_schedule.append((game[0] + timedelta(weeks=1), game[1], game[2]))
                            else:
                                new_schedule.append(game)
                        leagues_data[league_name]["schedule"] = sorted(new_schedule, key=lambda g: g[0])
                    break
                if conflict_found:
                    break
            if conflict_found:
                break
        if not conflict_found:
            break

    return leagues_data


# ── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown('<div class="sidebar-label">Season Settings</div>', unsafe_allow_html=True)
    start_date = st.date_input("Season start date", date(2025, 4, 5))
    st.markdown('<div class="sidebar-label" style="margin-top:1.5rem">Blackout Dates</div>', unsafe_allow_html=True)
    blackout_input = st.text_area("Dates to skip (DD/MM/YYYY)", "19/04/2025\n03/05/2025\n26/05/2025", height=100)
    st.markdown("---")
    st.markdown('<div class="sidebar-label">League Setup</div>', unsafe_allow_html=True)
    num_leagues = st.number_input("Number of leagues", min_value=1, max_value=8, value=2, step=1)

    DEFAULT_LEAGUE_NAMES = ["Division 1", "Division 2"]
    DEFAULT_LEAGUE_TEAMS = [
        ("Burnmoor 1st XI\nSouth Northumberland 1st XI\nCastle Eden 1st XI\n"
         "Felling 1st XI\nChester Le Street 1st XI\nHetton Lyons 1st XI\n"
         "Burnopfield 1st XI\nNewcastle 1st XI\nAshington 1st XI\n"
         "Shotley Bridge 1st XI\nBenwell Hill 1st XI\nSeaham Harbour 1st XI"),
        ("Felling 2nd XI\nNewcastle City CC 2nd XI\nChester Le Street 2nd XI\n"
         "Ashington 2nd XI\nSouth Northumberland 2nd XI\nNewcastle 2nd XI\n"
         "Tynemouth 2nd XI\nBenwell Hill 2nd XI\nTynedale 2nd XI\n"
         "Hetton Lyons 2nd XI\nWhitburn 2nd XI\nCastle Eden 2nd XI"),
    ]

    league_configs = []
    for i in range(int(num_leagues)):
        st.markdown(f'<hr class="league-divider">', unsafe_allow_html=True)
        default_name = DEFAULT_LEAGUE_NAMES[i] if i < len(DEFAULT_LEAGUE_NAMES) else f"Division {i + 1}"
        league_name = st.text_input(f"League {i + 1} name", value=default_name, key=f"league_name_{i}")
        default_teams = DEFAULT_LEAGUE_TEAMS[i] if i < len(DEFAULT_LEAGUE_TEAMS) else ""
        teams_input = st.text_area(f"Teams in {league_name} (one per line)", value=default_teams, height=140, key=f"league_teams_{i}")
        league_configs.append({"name": league_name, "teams_raw": teams_input})

    st.markdown("---")
    st.markdown('<div class="sidebar-label">Ground Sharing</div>', unsafe_allow_html=True)
    ground_conflict_enabled = st.toggle("Prevent shared-ground clashes", value=False, help="Teams sharing a stadium cannot both be home on same weekend.")

    ground_assignments = {}
    if ground_conflict_enabled:
        auto_pairs = detect_shared_grounds(league_configs)
        ground_input = st.text_area("Shared grounds (one pair per line)\nFormat: Team A, Team B", value=auto_pairs if auto_pairs else "Team A, Team B", height=120)
        if auto_pairs:
            st.caption("✅ Auto-detected from team names — edit if needed.")
        for line in ground_input.split("\n"):
            line = line.strip()
            if "," in line:
                sharing_teams = [t.strip() for t in line.split(",")]
                ground_name = " & ".join(sharing_teams)
                for team in sharing_teams:
                    ground_assignments[team] = ground_name

    st.markdown("<br>", unsafe_allow_html=True)
    generate = st.button("Generate Fixtures")

# ── Generation ───────────────────────────────────────────────────────────────
if generate:
    blackout_dates = []
    for d in blackout_input.split("\n"):
        d = d.strip()
        if d:
            try:
                day, month, year = d.split("/")
                blackout_dates.append(date(int(year), int(month), int(day)))
            except:
                pass

    leagues_data = {}
    for cfg in league_configs:
        league_name = cfg["name"]
        teams = [t.strip() for t in cfg["teams_raw"].split("\n") if t.strip()]
        if len(teams) < 2:
            st.warning(f"League '{league_name}' needs at least 2 teams — skipped.")
            continue

        # ✅ Use the verified round-robin & assign_dates
        rounds = generate_round_robin(teams)
        schedule = assign_dates(rounds, start_date, blackout_dates)
        leagues_data[league_name] = {"teams": teams, "schedule": schedule}

    # Handle shared-ground conflicts
    if ground_conflict_enabled and ground_assignments:
        for ln in leagues_data:
            leagues_data[ln]["schedule"] = resolve_ground_conflicts(
                leagues_data[ln]["schedule"], ground_assignments
            )
        leagues_data = resolve_ground_conflicts_global(leagues_data, ground_assignments)

    st.session_state.leagues_data = leagues_data
    st.session_state.ground_assignments = ground_assignments
    st.session_state.chat_history = []

# ── Display ───────────────────────────────────────────────────────────────────
# The display/rendering code (schedules, stats, home/away balance, chat assistant)
# remains unchanged from your current app.py.
