import streamlit as st
from datetime import date
from scheduler import schedule_leagues_or_tools
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

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&family=DM+Sans:ital,wght@0,300;0,400;0,500;1,300&display=swap');

html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; color: #1A1A2E; }
.stApp { background-color: #F7F8FA; }
header[data-testid="stHeader"] { background-color: #FFFFFF; border-bottom: 1px solid #E8ECF0; }
h1, h2, h3 { font-family: 'Outfit', sans-serif; font-weight: 600; }
.main-header { background: #FFFFFF; padding: 2rem 2.5rem 1.5rem 2.5rem; border-bottom: 1px solid #E8ECF0; margin: -1rem -1rem 2rem -1rem; }
.main-header h1 { font-family: 'Outfit', sans-serif; font-size: 1.8rem; font-weight: 700; color: #1A1A2E; margin: 0; letter-spacing: -0.5px; }
.main-header p { color: #6B7280; font-size: 0.9rem; margin: 0.3rem 0 0 0; font-weight: 300; }
.accent { color: #1B4332; }
.card { background: #FFFFFF; border: 1px solid #E8ECF0; border-radius: 12px; padding: 1.5rem; margin-bottom: 1rem; box-shadow: 0 1px 3px rgba(0,0,0,0.04); }
.league-header { font-family: 'Outfit', sans-serif; font-size: 1rem; font-weight: 700; color: #1B4332; margin: 1.5rem 0 0.75rem 0; padding-bottom: 0.5rem; border-bottom: 2px solid #1B4332; display: flex; align-items: center; gap: 0.5rem; }
.round-header { font-family: 'Outfit', sans-serif; font-size: 0.75rem; font-weight: 600; text-transform: uppercase; letter-spacing: 1.2px; color: #1B4332; margin-bottom: 0.75rem; padding-bottom: 0.75rem; border-bottom: 1px solid #E8ECF0; }
.fixture-row { display: flex; align-items: center; justify-content: space-between; padding: 0.6rem 0; border-bottom: 1px solid #F3F4F6; }
.fixture-row:last-child { border-bottom: none; padding-bottom: 0; }
.team-name { font-weight: 500; font-size: 0.95rem; color: #1A1A2E; flex: 1; }
.team-name.away { text-align: right; }
.vs-badge { background: #F3F4F6; color: #6B7280; font-size: 0.7rem; font-weight: 600; padding: 0.2rem 0.6rem; border-radius: 20px; margin: 0 1rem; letter-spacing: 0.5px; }
.metric-card { background: #FFFFFF; border: 1px solid #E8ECF0; border-radius: 12px; padding: 1.2rem 1.5rem; text-align: center; box-shadow: 0 1px 3px rgba(0,0,0,0.04); }
.metric-value { font-family: 'Outfit', sans-serif; font-size: 2rem; font-weight: 700; color: #1B4332; line-height: 1; }
.metric-label { font-size: 0.8rem; color: #6B7280; margin-top: 0.3rem; font-weight: 400; }
.balance-row { display: flex; align-items: center; justify-content: space-between; padding: 0.6rem 0; border-bottom: 1px solid #F3F4F6; font-size: 0.9rem; }
.balance-row:last-child { border-bottom: none; }
.balance-team { font-weight: 500; color: #1A1A2E; }
.balance-stats { color: #6B7280; font-size: 0.85rem; }
.balance-pill { background: #D1FAE5; color: #1B4332; font-size: 0.75rem; font-weight: 600; padding: 0.15rem 0.6rem; border-radius: 20px; }
.balance-league-label { font-family: 'Outfit', sans-serif; font-size: 0.7rem; font-weight: 600; text-transform: uppercase; letter-spacing: 1px; color: #9CA3AF; padding: 0.4rem 0 0.2rem 0; }
.section-title { font-family: 'Outfit', sans-serif; font-size: 1.1rem; font-weight: 600; color: #1A1A2E; margin-bottom: 1rem; display: flex; align-items: center; gap: 0.5rem; }
.stButton > button { background-color: #1B4332 !important; color: white !important; border: none !important; border-radius: 8px !important; padding: 0.6rem 1.5rem !important; font-family: 'Outfit', sans-serif !important; font-weight: 500 !important; font-size: 0.9rem !important; letter-spacing: 0.3px !important; transition: all 0.2s ease !important; width: 100% !important; }
.stButton > button:hover { background-color: #2D6A4F !important; box-shadow: 0 4px 12px rgba(27,67,50,0.25) !important; }
.stTextArea textarea, .stDateInput input, .stTextInput input { border-radius: 8px !important; border-color: #E8ECF0 !important; font-family: 'DM Sans', sans-serif !important; font-size: 0.9rem !important; }
.stTextArea textarea:focus, .stDateInput input:focus, .stTextInput input:focus { border-color: #1B4332 !important; box-shadow: 0 0 0 2px rgba(27,67,50,0.1) !important; }
label { font-family: 'DM Sans', sans-serif !important; font-weight: 500 !important; font-size: 0.85rem !important; color: #374151 !important; }
.stChatMessage { background: #FFFFFF !important; border: 1px solid #E8ECF0 !important; border-radius: 12px !important; }
.empty-state { text-align: center; padding: 3rem; color: #9CA3AF; }
.empty-state h3 { font-family: 'Outfit', sans-serif; font-size: 1rem; font-weight: 500; color: #6B7280; margin-bottom: 0.5rem; }
.empty-state p { font-size: 0.85rem; font-weight: 300; }
div[data-testid="stSidebar"] { background-color: #FFFFFF; border-right: 1px solid #E8ECF0; }
.sidebar-section { margin-bottom: 1.5rem; }
.sidebar-label { font-family: 'Outfit', sans-serif; font-size: 0.7rem; font-weight: 600; text-transform: uppercase; letter-spacing: 1px; color: #9CA3AF; margin-bottom: 0.75rem; }
.league-divider { border: none; border-top: 1px dashed #E8ECF0; margin: 1rem 0; }
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="main-header">
    <h1>⚡ FixtureAI</h1>
    <p>Intelligent fixture scheduling for cricket leagues</p>
</div>
""", unsafe_allow_html=True)

# ── Helpers ──────────────────────────────────────────────────────────────────
def detect_shared_grounds(league_configs):
    SUFFIXES = {"1st", "2nd", "3rd", "4th", "5th", "xi", "xii", "1sts", "2nds", "3rds", "4ths", "a", "b", "c"}

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

def reschedule_game(schedule, home_team, away_team, new_date):
    updated, rescheduled = [], False
    for game in schedule:
        if (game[1].lower() == home_team.lower() and game[2].lower() == away_team.lower()):
            updated.append((new_date, game[1], game[2]))
            rescheduled = True
        else:
            updated.append(game)
    updated.sort(key=lambda x: x[0])
    return updated, rescheduled

# ── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown('<div class="sidebar-label">Season Settings</div>', unsafe_allow_html=True)

    start_date = st.date_input("Season start date", date(2025, 4, 5))

    st.markdown('<div class="sidebar-label" style="margin-top:1.5rem">Blackout Dates</div>', unsafe_allow_html=True)
    blackout_input = st.text_area(
        "Dates to skip (DD/MM/YYYY)",
        "19/04/2025\n03/05/2025\n26/05/2025",
        height=100
    )

    st.markdown("---")
    st.markdown('<div class="sidebar-label">League Setup</div>', unsafe_allow_html=True)

    num_leagues = st.number_input("Number of leagues", min_value=1, max_value=8, value=2, step=1)

    DEFAULT_LEAGUE_NAMES = ["Division 1", "Division 2"]
    DEFAULT_LEAGUE_TEAMS = [
        ("Burnmoor 1st XI\nSouth Northumberland 1st XI\nCastle Eden 1st XI\nFelling 1st XI\nChester Le Street 1st XI\nHetton Lyons 1st XI\nBurnopfield 1st XI\nNewcastle 1st XI\nAshington 1st XI\nShotley Bridge 1st XI\nBenwell Hill 1st XI\nSeaham Harbour 1st XI"),
        ("Felling 2nd XI\nNewcastle City CC 2nd XI\nChester Le Street 2nd XI\nAshington 2nd XI\nSouth Northumberland 2nd XI\nNewcastle 2nd XI\nTynemouth 2nd XI\nBenwell Hill 2nd XI\nTynedale 2nd XI\nHetton Lyons 2nd XI\nWhitburn 2nd XI\nCastle Eden 2nd XI"),
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

    ground_conflict_enabled = st.toggle(
        "Prevent shared-ground clashes",
        value=False,
        help="When on, teams sharing a stadium cannot both be at home on the same weekend."
    )

    ground_assignments = {}
    if ground_conflict_enabled:
        auto_pairs = detect_shared_grounds(league_configs)
        ground_input = st.text_area(
            "Shared grounds (one pair per line)\nFormat: Team A, Team B",
            value=auto_pairs if auto_pairs else "Team A, Team B",
            height=120
        )
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

    formatted_leagues = []
    for cfg in league_configs:
        teams = [t.strip() for t in cfg["teams_raw"].split("\n") if t.strip()]
        if len(teams) >= 2:
            formatted_leagues.append({"name": cfg["name"], "teams": teams})
        else:
            st.warning(f"League '{cfg['name']}' needs at least 2 teams — skipped.")

    if formatted_leagues:
        with st.spinner("🤖 Solving fixtures with AI... This might take a minute for complex constraints."):
            try:
                # Call the new unified CP-SAT solver
                result = schedule_leagues_or_tools(
                    leagues=formatted_leagues,
                    start_date=start_date,
                    blackout_dates=blackout_dates,
                    ground_assignments=ground_assignments if ground_conflict_enabled else {},
                    time_limit_seconds=120,  # 2 minutes web UI limit
                    max_consecutive=2
                )

                leagues_data = {}
                for lg in formatted_leagues:
                    lname = lg["name"]
                    leagues_data[lname] = {
                        "teams": lg["teams"],
                        "schedule": result["schedules"].get(lname, [])
                    }

                st.session_state.leagues_data = leagues_data
                st.session_state.ground_assignments = ground_assignments
                st.session_state.remaining_conflicts = result.get("conflicts", [])
                st.session_state.chat_history = []
            except Exception as e:
                st.error(f"Failed to generate schedule: {str(e)}")

# ── Display ───────────────────────────────────────────────────────────────────
if "leagues_data" in st.session_state and st.session_state.leagues_data:
    leagues_data = st.session_state.leagues_data

    col1, col2 = st.columns([3, 2])

    conflicts = st.session_state.get("remaining_conflicts", [])
    if conflicts:
        with st.expander(f"⚠️ {len(conflicts)} unresolvable ground conflict{'s' if len(conflicts)>1 else ''} — click to review", expanded=False):
            st.markdown(
                "<small>These shared-ground clashes could not be eliminated while keeping "
                "full rounds every week. You may wish to manually swap one fixture in each "
                "case.</small>", unsafe_allow_html=True
            )
            rows = ""
            for c in conflicts:
                rows += (
                    f"<tr><td>{c['date'].strftime('%d %b %Y')}</td>"
                    f"<td>{c['ground']}</td>"
                    f"<td>{c['team1']} <span style='color:#9CA3AF'>({c['league1']})</span></td>"
                    f"<td>{c['team2']} <span style='color:#9CA3AF'>({c['league2']})</span></td></tr>"
                )
            st.markdown(
                f"<table style='font-size:0.82rem;width:100%'>"
                f"<thead><tr><th>Date</th><th>Ground</th><th>Home team 1</th><th>Home team 2</th></tr></thead>"
                f"<tbody>{rows}</tbody></table>",
                unsafe_allow_html=True,
            )

    with col1:
        st.markdown('<div class="section-title">📅 Season Schedule</div>', unsafe_allow_html=True)
        all_leagues = list(leagues_data.keys())
        tabs = [None] if len(all_leagues) == 1 else st.tabs(all_leagues)

        def render_schedule(schedule):
            current_date, round_number = None, 1
            round_fixtures_html, rounds_html = "", ""
            for game in schedule:
                if game[0] != current_date:
                    if round_fixtures_html:
                        rounds_html += f'<div class="card"><div class="round-header">Round {round_number - 1} &nbsp;·&nbsp; {current_date.strftime("%A %d %B %Y")}</div>{round_fixtures_html}</div>'
                        round_fixtures_html = ""
                    current_date = game[0]
                    round_number += 1
                round_fixtures_html += f'<div class="fixture-row"><span class="team-name">{game[1]}</span><span class="vs-badge">VS</span><span class="team-name away">{game[2]}</span></div>'

            if round_fixtures_html:
                rounds_html += f'<div class="card"><div class="round-header">Round {round_number - 1} &nbsp;·&nbsp; {current_date.strftime("%A %d %B %Y")}</div>{round_fixtures_html}</div>'
            st.markdown(rounds_html, unsafe_allow_html=True)

        if len(all_leagues) == 1:
            render_schedule(leagues_data[all_leagues[0]]["schedule"])
        else:
            for tab, league_name in zip(tabs, all_leagues):
                with tab:
                    render_schedule(leagues_data[league_name]["schedule"])

    with col2:
        all_schedules = [d["schedule"] for d in leagues_data.values()]
        flat_schedule = [game for sched in all_schedules for game in sched]
        total_rounds = sum(len(set(g[0] for g in d["schedule"])) for d in leagues_data.values())
        total_fixtures = len(flat_schedule)

        st.markdown('<div class="section-title">📊 Season Overview</div>', unsafe_allow_html=True)

        def generate_csv(leagues_data):
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(["League", "Date", "Home Team", "Away Team"])
            for league_name, data in leagues_data.items():
                for game in data["schedule"]:
                    writer.writerow([league_name, game[0].strftime("%d/%m/%Y"), game[1], game[2]])
            return output.getvalue()

        csv_data = generate_csv(st.session_state.leagues_data)
        st.download_button(label="⬇️ Download Fixtures CSV", data=csv_data, file_name="fixtures.csv", mime="text/csv")

        st.markdown("<br>", unsafe_allow_html=True)
        m1, m2, m3 = st.columns(3)
        with m1: st.markdown(f'<div class="metric-card"><div class="metric-value">{len(leagues_data)}</div><div class="metric-label">Leagues</div></div>', unsafe_allow_html=True)
        with m2: st.markdown(f'<div class="metric-card"><div class="metric-value">{total_rounds}</div><div class="metric-label">Rounds</div></div>', unsafe_allow_html=True)
        with m3: st.markdown(f'<div class="metric-card"><div class="metric-value">{total_fixtures}</div><div class="metric-label">Fixtures</div></div>', unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown('<div class="section-title">⚖️ Home / Away Balance</div>', unsafe_allow_html=True)
        pat_tab, bal_tab = st.tabs(["Pattern", "Summary"])

        with bal_tab:
            balance_html = '<div class="card">'
            for league_name, data in leagues_data.items():
                if len(leagues_data) > 1: balance_html += f'<div class="balance-league-label">🏆 {league_name}</div>'
                for team in data["teams"]:
                    schedule = data["schedule"]
                    home = sum(1 for g in schedule if g[1] == team)
                    away = sum(1 for g in schedule if g[2] == team)
                    balance_html += f'<div class="balance-row"><span class="balance-team">{team}</span><span class="balance-stats">{home}H &nbsp; {away}A</span><span class="balance-pill">Balanced</span></div>'
            balance_html += "</div>"
            st.markdown(balance_html, unsafe_allow_html=True)

        with pat_tab:
            pattern_html = """
            <style>
            .pat-grid { display: flex; flex-direction: column; gap: 0.55rem; padding: 0.25rem 0; }
            .pat-row  { display: flex; align-items: center; gap: 0.5rem; }
            .pat-name { font-size: 0.78rem; font-weight: 500; color: #1A1A2E; min-width: 130px; max-width: 130px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
            .pat-squares { display: flex; gap: 3px; flex-wrap: wrap; }
            .sq { width: 16px; height: 16px; border-radius: 3px; display: inline-flex; align-items: center; justify-content: center; font-size: 0.55rem; font-weight: 700; color: white; cursor: default; flex-shrink: 0; }
            .sq-h { background: #1B4332; }
            .sq-a { background: #D1FAE5; color: #1B4332; }
            .pat-league-label { font-family: 'Outfit', sans-serif; font-size: 0.68rem; font-weight: 600; text-transform: uppercase; letter-spacing: 1px; color: #9CA3AF; padding: 0.6rem 0 0.2rem 0; }
            .pat-legend { display: flex; gap: 1rem; align-items: center; font-size: 0.75rem; color: #6B7280; margin-bottom: 0.75rem; }
            .pat-legend-item { display: flex; align-items: center; gap: 4px; }
            </style>
            <div class="card"><div class="pat-legend"><div class="pat-legend-item"><div class="sq sq-h">H</div> Home</div><div class="pat-legend-item"><div class="sq sq-a">A</div> Away</div></div><div class="pat-grid">
            """
            all_dates = sorted(set(g[0] for data in leagues_data.values() for g in data["schedule"]))
            date_to_round = {d: i + 1 for i, d in enumerate(all_dates)}

            for league_name, data in leagues_data.items():
                if len(leagues_data) > 1: pattern_html += f'<div class="pat-league-label">🏆 {league_name}</div>'
                for team in data["teams"]:
                    team_games = sorted([g for g in data["schedule"] if g[1] == team or g[2] == team], key=lambda g: g[0])
                    squares = ""
                    for game in team_games:
                        rnd = date_to_round[game[0]]
                        label, css = ("H", "sq-h") if game[1] == team else ("A", "sq-a")
                        tip = f"Rd {rnd} · {game[0].strftime('%d %b')} · {'Home' if label == 'H' else 'Away'}"
                        squares += f'<div class="sq {css}" title="{tip}">{label}</div>'
                    pattern_html += f'<div class="pat-row"><span class="pat-name" title="{team}">{team}</span><div class="pat-squares">{squares}</div></div>'
            pattern_html += "</div></div>"
            st.markdown(pattern_html, unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown('<div class="section-title">🤖 Fixture Assistant</div>', unsafe_allow_html=True)

        if "chat_history" not in st.session_state: st.session_state.chat_history = []
        if not st.session_state.chat_history:
            st.markdown('<div class="card empty-state"><h3>Ask me anything</h3><p>Try "Show me Ashington CC\'s fixtures" or "Which teams play on 5th April?"</p></div>', unsafe_allow_html=True)

        for message in st.session_state.chat_history:
            with st.chat_message(message["role"]):
                st.write(message["content"])

        user_input = st.chat_input("Ask about the fixtures...")

        if user_input:
            st.session_state.chat_history.append({"role": "user", "content": user_input})
            schedule_text = "\n".join(f"[{league_name}] {game[0].strftime('%d/%m/%Y')} — {game[1]} vs {game[2]}" for league_name, data in leagues_data.items() for game in data["schedule"])

            prompt = f"""You are a cricket fixture scheduling assistant managing multiple leagues.
Here is the current fixture schedule:
{schedule_text}

The user asks: {user_input}

If the user wants to reschedule a fixture, respond ONLY with a JSON object in exactly this format:
{{"action": "reschedule", "league": "League Name", "home_team": "Team Name", "away_team": "Team Name", "new_date": "DD/MM/YYYY"}}

If the user is just asking a question, answer helpfully and concisely in plain English.
Do not return JSON for questions, only for reschedule requests."""

            response = model.generate_content(prompt)
            reply = response.text.strip()
            import json
            try:
                clean = reply.replace("```json", "").replace("```", "").strip()
                data = json.loads(clean)
                if data.get("action") == "reschedule":
                    day, month, year = data["new_date"].split("/")
                    new_date = date(int(year), int(month), int(day))
                    league_name = data.get("league", list(leagues_data.keys())[0])

                    if league_name in st.session_state.leagues_data:
                        updated_schedule, success = reschedule_game(st.session_state.leagues_data[league_name]["schedule"], data["home_team"], data["away_team"], new_date)
                        if success:
                            st.session_state.leagues_data[league_name]["schedule"] = updated_schedule
                            reply = f"Done — {data['home_team']} vs {data['away_team']} ({league_name}) moved to {data['new_date']}."
                        else:
                            reply = f"I couldn't find that fixture in {league_name}. Please check the team names and try again."
                    else:
                        reply = f"I couldn't identify the league '{league_name}'. Please try again."
            except: pass

            st.session_state.chat_history.append({"role": "assistant", "content": reply})
            st.rerun()

else:
    st.markdown("""
    <div style="text-align:center; padding: 5rem 2rem;">
        <div style="font-size: 3rem; margin-bottom: 1rem;">🏏</div>
        <h2 style="font-family: 'Outfit', sans-serif; color: #1A1A2E; font-weight: 600;">Ready to schedule</h2>
        <p style="color: #6B7280; font-size: 0.95rem; font-weight: 300;">Enter your leagues and settings in the sidebar, then click Generate Fixtures</p>
    </div>
    """, unsafe_allow_html=True)