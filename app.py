import streamlit as st
from datetime import date
import csv
import io
import os
import json
from dotenv import load_dotenv
import google.generativeai as genai

# Import the orchestrator from your scheduler.py
from scheduler import schedule_leagues_or_tools

load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel("gemini-2.5-flash-lite")

# --- UI Configuration ---
st.set_page_config(page_title="FixtureAI", page_icon="🏏", layout="wide")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&family=DM+Sans:wght@400;500&display=swap');
html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; color: #1A1A2E; }
.stApp { background-color: #F7F8FA; }
.main-header { background: #FFFFFF; padding: 2rem; border-bottom: 1px solid #E8ECF0; margin: -1rem -1rem 2rem -1rem; }
.main-header h1 { font-family: 'Outfit', sans-serif; font-size: 1.8rem; font-weight: 700; color: #1A1A2E; margin: 0; }
.card { background: #FFFFFF; border: 1px solid #E8ECF0; border-radius: 12px; padding: 1.5rem; margin-bottom: 1rem; box-shadow: 0 1px 3px rgba(0,0,0,0.04); }
.round-header { font-family: 'Outfit', sans-serif; font-size: 0.8rem; font-weight: 600; text-transform: uppercase; color: #1B4332; border-bottom: 1px solid #EEE; padding-bottom: 5px; margin-bottom: 10px; }
.fixture-row { display: flex; justify-content: space-between; padding: 5px 0; border-bottom: 1px solid #F9F9F9; }
.vs-badge { background: #F3F4F6; font-size: 0.7rem; padding: 2px 8px; border-radius: 10px; color: #6B7280; }
</style>
""", unsafe_allow_html=True)

# --- Logic Helpers ---
def reschedule_game(schedule, home_team, away_team, new_date):
    updated, found = [], False
    for game in schedule:
        if game[1].lower() == home_team.lower() and game[2].lower() == away_team.lower():
            updated.append((new_date, game[1], game[2]))
            found = True
        else:
            updated.append(game)
    updated.sort(key=lambda x: x[0])
    return updated, found

def detect_shared_grounds(league_configs):
    from collections import defaultdict
    all_teams = [t.strip() for cfg in league_configs for t in cfg["teams_raw"].split("\n") if t.strip()]
    groups = defaultdict(list)
    for t in all_teams:
        # Simple split logic to find common club names
        base = t.split(' 1st')[0].split(' 2nd')[0].split(' 3rd')[0].strip()
        groups[base].append(t)
    
    pairs = []
    for g in groups.values():
        if len(g) > 1:
            for i in range(len(g)):
                for j in range(i+1, len(g)):
                    pairs.append(f"{g[i]}, {g[j]}")
    return "\n".join(pairs)

# --- Dummy Data ---
DEFAULT_NAMES = ["Division 1", "Division 2"]
DEFAULT_TEAMS = [
    "Burnmoor 1st XI\nSouth Northumberland 1st XI\nCastle Eden 1st XI\nFelling 1st XI\nChester Le Street 1st XI\nHetton Lyons 1st XI\nBurnopfield 1st XI\nNewcastle 1st XI\nAshington 1st XI\nShotley Bridge 1st XI\nBenwell Hill 1st XI\nSeaham Harbour 1st XI",
    "Felling 2nd XI\nNewcastle City CC 2nd XI\nChester Le Street 2nd XI\nAshington 2nd XI\nSouth Northumberland 2nd XI\nNewcastle 2nd XI\nTynemouth 2nd XI\nBenwell Hill 2nd XI\nTynedale 2nd XI\nHetton Lyons 2nd XI\nWhitburn 2nd XI\nCastle Eden 2nd XI"
]

# --- Sidebar Inputs ---
with st.sidebar:
    st.header("Season Setup")
    start_date = st.date_input("First Saturday", date(2025, 4, 5))
    blackout_input = st.text_area("Blackout Dates (DD/MM/YYYY)", "19/04/2025\n03/05/2025\n26/05/2025")
    
    num_leagues = st.number_input("Number of Leagues", 1, 15, 2)
    league_configs = []
    for i in range(int(num_leagues)):
        st.divider()
        d_name = DEFAULT_NAMES[i] if i < len(DEFAULT_NAMES) else f"Division {i+1}"
        d_teams = DEFAULT_TEAMS[i] if i < len(DEFAULT_TEAMS) else ""
        
        l_name = st.text_input(f"League {i+1} Name", value=d_name)
        l_teams = st.text_area(f"Teams in {l_name}", value=d_teams, height=150, key=f"t{i}")
        league_configs.append({"name": l_name, "teams_raw": l_teams})
    
    st.divider()
    ground_conflict_enabled = st.toggle("Enable Ground Sharing Rules", value=True)
    ground_assignments = {}
    if ground_conflict_enabled:
        suggested = detect_shared_grounds(league_configs)
        ground_input = st.text_area("Shared Grounds (Team A, Team B)", value=suggested, height=100)
        for line in ground_input.split("\n"):
            if "," in line:
                teams = [t.strip() for t in line.split(",")]
                g_name = "Ground_" + "_".join(teams)
                for t in teams: ground_assignments[t] = g_name

    generate = st.button("🚀 Generate Optimized Schedule")

# --- Main App Execution ---
st.markdown('<div class="main-header"><h1>⚡ FixtureAI</h1><p>Clustered Dependency Engine for Multi-League Scheduling</p></div>', unsafe_allow_html=True)

if generate:
    blackouts = []
    for d in blackout_input.split("\n"):
        if d.strip():
            try:
                day, month, year = d.strip().split("/")
                blackouts.append(date(int(year), int(month), int(day)))
            except: pass

    leagues = []
    for cfg in league_configs:
        teams = [t.strip() for t in cfg["teams_raw"].split("\n") if t.strip()]
        if len(teams) >= 2:
            leagues.append({"name": cfg["name"], "teams": teams})

    if leagues:
        with st.spinner("Analyzing league clusters and solving..."):
            try:
                result = schedule_leagues_or_tools(
                    leagues=leagues,
                    start_date=start_date,
                    blackout_dates=blackouts,
                    ground_assignments=ground_assignments,
                    time_limit_seconds=180 
                )
                st.session_state.leagues_data = result["schedules"]
                st.session_state.chat_history = []
            except Exception as e:
                st.error(f"Solver Error: {str(e)}")

# --- Result Display ---
if "leagues_data" in st.session_state:
    data = st.session_state.leagues_data
    col_left, col_right = st.columns([3, 2])
    
    with col_left:
        st.subheader("📅 Fixtures")
        l_tabs = st.tabs(list(data.keys()))
        for i, (l_name, schedule) in enumerate(data.items()):
            with l_tabs[i]:
                current_date = None
                for game_date, home, away in schedule:
                    if game_date != current_date:
                        if current_date is not None: st.markdown('</div>', unsafe_allow_html=True)
                        st.markdown(f'<div class="card"><div class="round-header">{game_date.strftime("%d %B %Y")}</div>', unsafe_allow_html=True)
                        current_date = game_date
                    st.markdown(f'<div class="fixture-row"><span>{home}</span><span class="vs-badge">VS</span><span>{away}</span></div>', unsafe_allow_html=True)
                st.markdown('</div>', unsafe_allow_html=True)

    with col_right:
        st.subheader("📊 Actions & Tools")
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["League", "Date", "Home", "Away"])
        for l_name, sched in data.items():
            for d, h, a in sched: writer.writerow([l_name, d, h, a])
        st.download_button("📥 Download CSV", output.getvalue(), "fixtures.csv", "text/csv")
        
        st.divider()
        st.markdown("**🤖 Fixture Assistant**")
        for msg in st.session_state.chat_history:
            with st.chat_message(msg["role"]): st.write(msg["content"])
        
        user_msg = st.chat_input("Ask about the fixtures...")
        if user_msg:
            st.session_state.chat_history.append({"role": "user", "content": user_msg})
            all_txt = "\n".join([f"{l}: {g[1]} v {g[2]} on {g[0]}" for l, s in data.items() for g in s])
            prompt = f"Schedule:\n{all_txt}\nUser: {user_msg}\nIf rescheduling, return JSON: {{\"action\":\"reschedule\",\"league\":\"...\",\"home_team\":\"...\",\"away_team\":\"...\",\"new_date\":\"DD/MM/YYYY\"}}. Otherwise, plain text."
            
            response = model.generate_content(prompt).text
            try:
                clean_json = response.strip('`json \n')
                action_data = json.loads(clean_json)
                if action_data.get("action") == "reschedule":
                    l_target = action_data["league"]
                    d_str = action_data["new_date"]
                    day, month, year = d_str.split("/")
                    new_d = date(int(year), int(month), int(day))
                    
                    new_sched, success = reschedule_game(data[l_target], action_data["home_team"], action_data["away_team"], new_d)
                    if success:
                        st.session_state.leagues_data[l_target] = new_sched
                        response = f"✅ Updated: {action_data['home_team']} vs {action_data['away_team']} moved to {d_str}."
            except: pass
            
            st.session_state.chat_history.append({"role": "assistant", "content": response})
            st.rerun()