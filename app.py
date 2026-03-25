import streamlit as st
import pandas as pd
from datetime import date
import csv
import io
import os
from collections import defaultdict
from dotenv import load_dotenv
import google.generativeai as genai

# Import the orchestrator from scheduler.py
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
    
    /* Round Header Styling */
    .round-container {
        background-color: #FFFFFF;
        border: 1px solid #E8ECF0;
        border-radius: 8px;
        margin-bottom: 1.5rem;
        overflow: hidden;
        box-shadow: 0 2px 4px rgba(0,0,0,0.02);
    }
    .round-header {
        background-color: #F8FAFC;
        padding: 12px 20px;
        border-bottom: 1px solid #E8ECF0;
        font-family: 'Outfit', sans-serif;
        font-weight: 600;
        color: #1E293B;
        display: flex;
        justify-content: space-between;
    }
    .fixture-row {
        display: grid;
        grid-template-columns: 1fr 50px 1fr;
        padding: 12px 20px;
        border-bottom: 1px solid #F1F5F9;
        align-items: center;
    }
    .fixture-row:last-child { border-bottom: none; }
    .vs-badge {
        text-align: center;
        font-size: 0.75rem;
        font-weight: 700;
        color: #64748B;
        background: #F1F5F9;
        padding: 4px 8px;
        border-radius: 6px;
    }
    .team-home { text-align: right; font-weight: 500; font-size: 1rem; }
    .team-away { text-align: left; font-weight: 500; font-size: 1rem; }
</style>
""", unsafe_allow_html=True)

# --- Logic Helpers ---
def get_ha_analysis(schedule, teams):
    """Generates the Home/Away sequence visualization for the Analysis tab."""
    analysis = []
    for team in teams:
        if team == "BYE": continue
        sequence = []
        # Sort schedule by date for accurate sequence
        sorted_sched = sorted(schedule, key=lambda x: x[0])
        for _, home, away in sorted_sched:
            if home == team: sequence.append("H")
            elif away == team: sequence.append("A")
        
        # Calculate max streak
        max_s = 0
        curr_s = 1 if sequence else 0
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

# --- Dummy Data Setup ---
DEFAULT_DATA = {
    "North East Premier League": [
        "Burnmoor 1st XI", "South Northumberland 1st XI", "Castle Eden 1st XI", "Felling 1st XI",
        "Chester Le Street 1st XI", "Hetton Lyons 1st XI", "Burnopfield 1st XI", "Newcastle 1st XI",
        "Ashington 1st XI", "Shotley Bridge 1st XI", "Benwell Hill 1st XI", "Seaham Harbour 1st XI"
    ],
    "Division 1": [
        "Tynemouth 1st XI", "Sunderland 1st XI", "Newcastle City 1st XI", "Gateshead Fell 1st XI",
        "Whitburn 1st XI", "Lanchester 1st XI", "Willington 1st XI", "Philadelphia 1st XI",
        "Sacriston 1st XI", "Tynedale 1st XI", "Seaham Park 1st XI", "Boldon 1st XI"
    ],
    "Division 2": [
        "Felling 2nd XI", "Newcastle City 2nd XI", "Chester Le Street 2nd XI", "Ashington 2nd XI",
        "South Northumberland 2nd XI", "Newcastle 2nd XI", "Tynemouth 2nd XI", "Benwell Hill 2nd XI",
        "Tynedale 2nd XI", "Hetton Lyons 2nd XI", "Whitburn 2nd XI", "Castle Eden 2nd XI"
    ],
    "Division 3": [
        "Sacriston 2nd XI", "Seaham Harbour 2nd XI", "Boldon 2nd XI", "Burnmoor 2nd XI",
        "Lanchester 2nd XI", "Burnopfield 2nd XI", "Seaham Park 2nd XI", "Shotley Bridge 2nd XI",
        "Philadelphia 2nd XI", "Willington 2nd XI", "Sunderland 2nd XI", "Gateshead 2nd XI"
    ]
}

# --- Sidebar ---
with st.sidebar:
    st.header("Season Setup")
    start_date = st.date_input("First Saturday", date(2025, 4, 5))
    blackout_input = st.text_area("Blackout Dates (DD/MM/YYYY)", "19/04/2025\n03/05/2025\n26/05/2025")
    
    num_leagues = st.number_input("Number of Leagues", 1, 15, 4)
    league_configs = []
    
    keys = list(DEFAULT_DATA.keys())
    for i in range(int(num_leagues)):
        st.divider()
        d_name = keys[i] if i < len(keys) else f"Division {i+1}"
        d_teams = "\n".join(DEFAULT_DATA[d_name]) if d_name in DEFAULT_DATA else ""
        
        l_name = st.text_input(f"League {i+1} Name", value=d_name)
        l_teams = st.text_area(f"Teams in {l_name}", value=d_teams, height=150, key=f"t{i}")
        league_configs.append({
            "name": l_name, 
            "teams_list": [t.strip() for t in l_teams.split("\n") if t.strip()]
        })
    
    st.divider()
    ground_conflict_enabled = st.toggle("Enable Ground Sharing Rules", value=True)
    ground_assignments = {}
    if ground_conflict_enabled:
        all_teams = [t for cfg in league_configs for t in cfg["teams_list"]]
        groups = defaultdict(list)
        for t in all_teams:
            base = t.split(' 1st')[0].split(' 2nd')[0].strip()
            groups[base].append(t)
        
        suggested_pairs = [", ".join(m) for m in groups.values() if len(m) > 1]
        ground_input = st.text_area("Shared Grounds", value="\n".join(suggested_pairs), height=100)
        for line in ground_input.split("\n"):
            if "," in line:
                teams = [t.strip() for t in line.split(",")]
                g_name = f"Ground_{teams[0].replace(' ', '_')}"
                for t in teams: ground_assignments[t] = g_name

    generate = st.button("🚀 Generate Fixtures")

# --- Main App ---
st.markdown('<div style="padding: 1rem 0; border-bottom: 1px solid #E8ECF0; margin-bottom: 2rem;"><h1>⚡ FixtureAI</h1></div>', unsafe_allow_html=True)

if generate:
    # Parse Blackouts
    blackouts = []
    for d in blackout_input.split("\n"):
        if d.strip():
            try:
                day, month, year = d.strip().split("/")
                blackouts.append(date(int(year), int(month), int(day)))
            except: pass

    leagues = [{"name": c["name"], "teams": c["teams_list"]} for c in league_configs if len(c["teams_list"]) >= 2]

    if leagues:
        with st.spinner("Solving tiers with Multi-Objective CP-SAT..."):
            try:
                result = schedule_leagues_or_tools(
                    leagues=leagues,
                    start_date=start_date,
                    blackout_dates=blackouts,
                    ground_assignments=ground_assignments
                )
                st.session_state.leagues_data = result["schedules"]
                st.session_state.league_meta = {l["name"]: l["teams"] for l in leagues}
            except Exception as e:
                st.error(f"Solver Error: {str(e)}")

# --- Results Area ---
if "leagues_data" in st.session_state:
    data = st.session_state.leagues_data
    
    col_main, col_chat = st.columns([2.5, 1])
    
    with col_main:
        tabs = st.tabs(["📅 Fixture List", "📊 Home/Away Analysis", "📥 Export"])
        
        with tabs[0]:
            l_selector = st.selectbox("Select Division to View", list(data.keys()))
            league_fixtures = data[l_selector]
            
            # Rendering Round-by-Round
            current_date = None
            for g_date, home, away in league_fixtures:
                if g_date != current_date:
                    if current_date is not None: st.markdown('</div>', unsafe_allow_html=True)
                    st.markdown(f'''
                        <div class="round-container">
                            <div class="round-header">
                                <span>Saturday</span>
                                <span>{g_date.strftime("%d %B %Y")}</span>
                            </div>
                    ''', unsafe_allow_html=True)
                    current_date = g_date
                
                st.markdown(f'''
                    <div class="fixture-row">
                        <div class="team-home">{home}</div>
                        <div class="vs-badge">VS</div>
                        <div class="team-away">{away}</div>
                    </div>
                ''', unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)
            
        with tabs[1]:
            l_selector_an = st.selectbox("Analyze League Balance", list(data.keys()))
            analysis_df = get_ha_analysis(data[l_selector_an], st.session_state.league_meta[l_selector_an])
            st.dataframe(analysis_df, use_container_width=True, hide_index=True)
            st.info("The solver prioritizes a Max Streak of 2. If a ground conflict is impossible to solve, it relaxes to 3.")

        with tabs[2]:
            csv_buffer = io.StringIO()
            writer = csv.writer(csv_buffer)
            writer.writerow(["League", "Date", "Home", "Away"])
            for l_name, sched in data.items():
                for d, h, a in sched: writer.writerow([l_name, d, h, a])
            st.download_button("Download Full CSV", csv_buffer.getvalue(), "fixtures.csv", "text/csv")

    with col_chat:
        st.subheader("🤖 Fixture Assistant")
        st.info("I can help you review the schedule or find specific dates. Try asking: 'Are there any dates where Felling 1st and 2nd XI both play at home?'")