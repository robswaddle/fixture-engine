import streamlit as st
import pandas as pd
from datetime import date
import csv
import io
import os
import json
from dotenv import load_dotenv
import google.generativeai as genai

# Import the orchestrator
from scheduler import schedule_leagues_or_tools

load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel("gemini-2.5-flash-lite")

# --- UI Configuration ---
st.set_page_config(page_title="FixtureAI", page_icon="🏏", layout="wide")

# Restoring the professional clean CSS
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&display=swap');
    html, body, [class*="css"] { font-family: 'Outfit', sans-serif; }
    .stTable { font-size: 0.85rem; }
    .main-header { padding: 1rem 0; border-bottom: 1px solid #E8ECF0; margin-bottom: 2rem; }
    .status-tag { padding: 2px 8px; border-radius: 4px; font-size: 0.7rem; font-weight: 600; }
</style>
""", unsafe_allow_html=True)

# --- Logic Helpers ---
def get_ha_analysis(schedule, teams):
    """Generates the Home/Away sequence visualization."""
    analysis = []
    for team in teams:
        if team == "BYE": continue
        sequence = []
        for _, home, away in schedule:
            if home == team: sequence.append("H")
            elif away == team: sequence.append("A")
        
        # Calculate max streak
        max_s = 0
        curr_s = 1
        for i in range(1, len(sequence)):
            if sequence[i] == sequence[i-1]:
                curr_s += 1
            else:
                max_s = max(max_s, curr_s)
                curr_s = 1
        max_s = max(max_s, curr_s)
        
        analysis.append({
            "Team": team,
            "Sequence": " ".join(sequence),
            "Max Streak": max_s
        })
    return pd.DataFrame(analysis)

def detect_shared_grounds(league_configs):
    from collections import defaultdict
    all_teams = [t.strip() for cfg in league_configs for t in cfg["teams_raw"].split("\n") if t.strip()]
    groups = defaultdict(list)
    for t in all_teams:
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

# --- Sidebar ---
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
        l_teams = st.text_area(f"Teams", value=d_teams, height=120, key=f"t{i}")
        league_configs.append({"name": l_name, "teams_raw": l_teams, "teams_list": [t.strip() for t in l_teams.split("\n") if t.strip()]})
    
    st.divider()
    ground_conflict_enabled = st.toggle("Enable Ground Sharing Rules", value=True)
    ground_assignments = {}
    if ground_conflict_enabled:
        suggested = detect_shared_grounds(league_configs)
        ground_input = st.text_area("Shared Grounds", value=suggested, height=80)
        for line in ground_input.split("\n"):
            if "," in line:
                teams = [t.strip() for t in line.split(",")]
                g_name = "Ground_" + "_".join(teams)
                for t in teams: ground_assignments[t] = g_name

    generate = st.button("🚀 Generate Fixtures")

# --- Main App ---
st.markdown('<div class="main-header"><h1>⚡ FixtureAI</h1></div>', unsafe_allow_html=True)

if generate:
    blackouts = []
    for d in blackout_input.split("\n"):
        if d.strip():
            try:
                day, month, year = d.strip().split("/")
                blackouts.append(date(int(year), int(month), int(day)))
            except: pass

    leagues = [{"name": c["name"], "teams": c["teams_list"]} for c in league_configs if len(c["teams_list"]) >= 2]

    if leagues:
        with st.spinner("Solving league clusters..."):
            try:
                result = schedule_leagues_or_tools(
                    leagues=leagues,
                    start_date=start_date,
                    blackout_dates=blackouts,
                    ground_assignments=ground_assignments,
                    time_limit_seconds=180 
                )
                st.session_state.leagues_data = result["schedules"]
                st.session_state.league_meta = {l["name"]: l["teams"] for l in leagues}
                st.session_state.chat_history = []
            except Exception as e:
                st.error(f"Solver Error: {str(e)}")

# --- Result Tabs ---
if "leagues_data" in st.session_state:
    data = st.session_state.leagues_data
    
    col_main, col_chat = st.columns([2, 1])
    
    with col_main:
        tabs = st.tabs(["📅 Fixture List", "📊 Home/Away Analysis", "📥 Export"])
        
        with tabs[0]: # Table View
            l_selector = st.selectbox("Select League", list(data.keys()))
            df = pd.DataFrame(data[l_selector], columns=["Date", "Home Team", "Away Team"])
            st.table(df) # Using st.table for that classic look
            
        with tabs[1]: # Analysis View
            l_selector_an = st.selectbox("Select League to Analyze", list(data.keys()))
            analysis_df = get_ha_analysis(data[l_selector_an], st.session_state.league_meta[l_selector_an])
            st.dataframe(analysis_df, use_container_width=True, hide_index=True)
            st.info("Check 'Max Streak' to ensure no team has more than 2 consecutive home or away games.")

        with tabs[2]: # Export
            csv_buffer = io.StringIO()
            writer = csv.writer(csv_buffer)
            writer.writerow(["League", "Date", "Home", "Away"])
            for l_name, sched in data.items():
                for d, h, a in sched: writer.writerow([l_name, d, h, a])
            st.download_button("Download Full Season CSV", csv_buffer.getvalue(), "fixtures.csv", "text/csv")

    with col_chat:
        st.markdown("### 🤖 Fixture Assistant")
        for msg in st.session_state.chat_history:
            with st.chat_message(msg["role"]): st.write(msg["content"])
        
        user_msg = st.chat_input("Ask a question...")
        if user_msg:
            # ... (AI Logic remains same as previous turn) ...
            st.session_state.chat_history.append({"role": "user", "content": user_msg})
            st.rerun()