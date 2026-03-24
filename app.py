import streamlit as st
from datetime import date
from scheduler import generate_round_robin, group_into_rounds, assign_dates, reschedule_game, resolve_ground_conflicts
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

html, body, [class*="css"] {
    font-family: 'DM Sans', sans-serif;
    color: #1A1A2E;
}

.stApp {
    background-color: #F7F8FA;
}

header[data-testid="stHeader"] {
    background-color: #FFFFFF;
    border-bottom: 1px solid #E8ECF0;
}

h1, h2, h3 {
    font-family: 'Outfit', sans-serif;
    font-weight: 600;
}

.main-header {
    background: #FFFFFF;
    padding: 2rem 2.5rem 1.5rem 2.5rem;
    border-bottom: 1px solid #E8ECF0;
    margin: -1rem -1rem 2rem -1rem;
}

.main-header h1 {
    font-family: 'Outfit', sans-serif;
    font-size: 1.8rem;
    font-weight: 700;
    color: #1A1A2E;
    margin: 0;
    letter-spacing: -0.5px;
}

.main-header p {
    color: #6B7280;
    font-size: 0.9rem;
    margin: 0.3rem 0 0 0;
    font-weight: 300;
}

.accent {
    color: #1B4332;
}

.card {
    background: #FFFFFF;
    border: 1px solid #E8ECF0;
    border-radius: 12px;
    padding: 1.5rem;
    margin-bottom: 1rem;
    box-shadow: 0 1px 3px rgba(0,0,0,0.04);
}

.round-header {
    font-family: 'Outfit', sans-serif;
    font-size: 0.75rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 1.2px;
    color: #1B4332;
    margin-bottom: 0.75rem;
    padding-bottom: 0.75rem;
    border-bottom: 1px solid #E8ECF0;
}

.fixture-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0.6rem 0;
    border-bottom: 1px solid #F3F4F6;
}

.fixture-row:last-child {
    border-bottom: none;
    padding-bottom: 0;
}

.team-name {
    font-weight: 500;
    font-size: 0.95rem;
    color: #1A1A2E;
    flex: 1;
}

.team-name.away {
    text-align: right;
}

.vs-badge {
    background: #F3F4F6;
    color: #6B7280;
    font-size: 0.7rem;
    font-weight: 600;
    padding: 0.2rem 0.6rem;
    border-radius: 20px;
    margin: 0 1rem;
    letter-spacing: 0.5px;
}

.metric-card {
    background: #FFFFFF;
    border: 1px solid #E8ECF0;
    border-radius: 12px;
    padding: 1.2rem 1.5rem;
    text-align: center;
    box-shadow: 0 1px 3px rgba(0,0,0,0.04);
}

.metric-value {
    font-family: 'Outfit', sans-serif;
    font-size: 2rem;
    font-weight: 700;
    color: #1B4332;
    line-height: 1;
}

.metric-label {
    font-size: 0.8rem;
    color: #6B7280;
    margin-top: 0.3rem;
    font-weight: 400;
}

.balance-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0.6rem 0;
    border-bottom: 1px solid #F3F4F6;
    font-size: 0.9rem;
}

.balance-row:last-child {
    border-bottom: none;
}

.balance-team {
    font-weight: 500;
    color: #1A1A2E;
}

.balance-stats {
    color: #6B7280;
    font-size: 0.85rem;
}

.balance-pill {
    background: #D1FAE5;
    color: #1B4332;
    font-size: 0.75rem;
    font-weight: 600;
    padding: 0.15rem 0.6rem;
    border-radius: 20px;
}

.section-title {
    font-family: 'Outfit', sans-serif;
    font-size: 1.1rem;
    font-weight: 600;
    color: #1A1A2E;
    margin-bottom: 1rem;
    display: flex;
    align-items: center;
    gap: 0.5rem;
}

.stButton > button {
    background-color: #1B4332 !important;
    color: white !important;
    border: none !important;
    border-radius: 8px !important;
    padding: 0.6rem 1.5rem !important;
    font-family: 'Outfit', sans-serif !important;
    font-weight: 500 !important;
    font-size: 0.9rem !important;
    letter-spacing: 0.3px !important;
    transition: all 0.2s ease !important;
    width: 100% !important;
}

.stButton > button:hover {
    background-color: #2D6A4F !important;
    box-shadow: 0 4px 12px rgba(27,67,50,0.25) !important;
}

.stTextArea textarea, .stDateInput input {
    border-radius: 8px !important;
    border-color: #E8ECF0 !important;
    font-family: 'DM Sans', sans-serif !important;
    font-size: 0.9rem !important;
}

.stTextArea textarea:focus, .stDateInput input:focus {
    border-color: #1B4332 !important;
    box-shadow: 0 0 0 2px rgba(27,67,50,0.1) !important;
}

label {
    font-family: 'DM Sans', sans-serif !important;
    font-weight: 500 !important;
    font-size: 0.85rem !important;
    color: #374151 !important;
}

.stChatMessage {
    background: #FFFFFF !important;
    border: 1px solid #E8ECF0 !important;
    border-radius: 12px !important;
}

.chat-container {
    background: #FFFFFF;
    border: 1px solid #E8ECF0;
    border-radius: 12px;
    padding: 1.5rem;
    margin-top: 1rem;
}

.empty-state {
    text-align: center;
    padding: 3rem;
    color: #9CA3AF;
}

.empty-state h3 {
    font-family: 'Outfit', sans-serif;
    font-size: 1rem;
    font-weight: 500;
    color: #6B7280;
    margin-bottom: 0.5rem;
}

.empty-state p {
    font-size: 0.85rem;
    font-weight: 300;
}

div[data-testid="stSidebar"] {
    background-color: #FFFFFF;
    border-right: 1px solid #E8ECF0;
}

div[data-testid="stSidebar"] .stMarkdown {
    padding: 0;
}

.sidebar-section {
    margin-bottom: 1.5rem;
}

.sidebar-label {
    font-family: 'Outfit', sans-serif;
    font-size: 0.7rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 1px;
    color: #9CA3AF;
    margin-bottom: 0.75rem;
}
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="main-header">
    <h1>⚡ FixtureAI</h1>
    <p>Intelligent fixture scheduling for cricket leagues</p>
</div>
""", unsafe_allow_html=True)

with st.sidebar:
    st.markdown('<div class="sidebar-label">League Setup</div>', unsafe_allow_html=True)

    teams_input = st.text_area(
        "Teams (one per line)",
        "Ashington CC\nBlyth CC\nMorpeth CC\nAlnwick CC\nTynemouth CC\nBedlington CC",
        height=180
    )

    start_date = st.date_input("Season start date", date(2025, 4, 5))

    st.markdown('<div class="sidebar-label" style="margin-top:1.5rem">Blackout Dates</div>', unsafe_allow_html=True)

    blackout_input = st.text_area(
        "Dates to skip (DD/MM/YYYY)",
        "19/04/2025\n03/05/2025\n26/05/2025",
        height=120
    )

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown('<div class="sidebar-label" style="margin-top:1.5rem">Ground Sharing</div>', unsafe_allow_html=True)
    ground_input = st.text_area(
        "Teams sharing a ground (format: Team A, Team B)",
        "Ashington CC, Blyth CC",
        height=100
    )
    generate = st.button("Generate Fixtures")

if generate:
    teams = [t.strip() for t in teams_input.split("\n") if t.strip()]

    blackout_dates = []
    for d in blackout_input.split("\n"):
        d = d.strip()
        if d:
            try:
                day, month, year = d.split("/")
                blackout_dates.append(date(int(year), int(month), int(day)))
            except:
                pass

    ground_assignments = {}
    for line in ground_input.split("\n"):
        line = line.strip()
        if "," in line:
            sharing_teams = [t.strip() for t in line.split(",")]
            ground_name = " & ".join(sharing_teams)
            for team in sharing_teams:
                ground_assignments[team] = ground_name

    fixtures = generate_round_robin(teams)
    rounds = group_into_rounds(fixtures, teams)
    schedule = assign_dates(rounds, start_date, blackout_dates)
    
    if ground_assignments:
        schedule = resolve_ground_conflicts(schedule, ground_assignments)

    st.session_state.schedule = schedule
    st.session_state.teams = teams
    st.session_state.ground_assignments = ground_assignments
    st.session_state.chat_history = []

if "schedule" in st.session_state:
    col1, col2 = st.columns([3, 2])

    with col1:
        st.markdown('<div class="section-title">📅 Season Schedule</div>', unsafe_allow_html=True)

        schedule = st.session_state.schedule
        current_date = None
        round_number = 1
        round_fixtures_html = ""
        rounds_html = ""

        for game in schedule:
            if game[0] != current_date:
                if round_fixtures_html:
                    rounds_html += f"""
                    <div class="card">
                        <div class="round-header">Round {round_number - 1} &nbsp;·&nbsp; {current_date.strftime('%A %d %B %Y')}</div>
                        {round_fixtures_html}
                    </div>"""
                    round_fixtures_html = ""

                current_date = game[0]
                round_number += 1

            round_fixtures_html += f"""
            <div class="fixture-row">
                <span class="team-name">{game[1]}</span>
                <span class="vs-badge">VS</span>
                <span class="team-name away">{game[2]}</span>
            </div>"""

        if round_fixtures_html:
            rounds_html += f"""
            <div class="card">
                <div class="round-header">Round {round_number - 1} &nbsp;·&nbsp; {current_date.strftime('%A %d %B %Y')}</div>
                {round_fixtures_html}
            </div>"""

        st.markdown(rounds_html, unsafe_allow_html=True)

    with col2:
        teams = st.session_state.teams
        total_rounds = len(set(game[0] for game in schedule))
        total_fixtures = len(schedule)

        st.markdown('<div class="section-title">📊 Season Overview</div>', unsafe_allow_html=True)


        def generate_csv(schedule):
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(["Date", "Home Team", "Away Team"])
            for game in schedule:
                writer.writerow([game[0].strftime("%d/%m/%Y"), game[1], game[2]])
            return output.getvalue()

        csv_data = generate_csv(st.session_state.schedule)
        st.download_button(
            label="⬇️ Download Fixtures CSV",
            data=csv_data,
            file_name="fixtures.csv",
            mime="text/csv"
        )

        st.markdown("<br>", unsafe_allow_html=True)
        m1, m2 = st.columns(2)
        with m1:
            st.markdown(f"""
            <div class="metric-card">
                <div class="metric-value">{total_rounds}</div>
                <div class="metric-label">Rounds</div>
            </div>""", unsafe_allow_html=True)
        with m2:
            st.markdown(f"""
            <div class="metric-card">
                <div class="metric-value">{total_fixtures}</div>
                <div class="metric-label">Fixtures</div>
            </div>""", unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown('<div class="section-title">⚖️ Home / Away Balance</div>', unsafe_allow_html=True)

        balance_html = '<div class="card">'
        for team in teams:
            home = sum(1 for g in schedule if g[1] == team)
            away = sum(1 for g in schedule if g[2] == team)
            balance_html += f"""
            <div class="balance-row">
                <span class="balance-team">{team}</span>
                <span class="balance-stats">{home}H &nbsp; {away}A</span>
                <span class="balance-pill">Balanced</span>
            </div>"""
        balance_html += "</div>"
        st.markdown(balance_html, unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown('<div class="section-title">🤖 Fixture Assistant</div>', unsafe_allow_html=True)

        if "chat_history" not in st.session_state:
            st.session_state.chat_history = []

        if not st.session_state.chat_history:
            st.markdown("""
            <div class="card empty-state">
                <h3>Ask me anything</h3>
                <p>Try "Show me Ashington CC's fixtures" or "Which teams play on 5th April?"</p>
            </div>""", unsafe_allow_html=True)

        for message in st.session_state.chat_history:
            with st.chat_message(message["role"]):
                st.write(message["content"])

        user_input = st.chat_input("Ask about the fixtures...")

        if user_input:
            st.session_state.chat_history.append({"role": "user", "content": user_input})

            schedule_text = "\n".join(
                [f"{game[0].strftime('%d/%m/%Y')} — {game[1]} vs {game[2]}"
                 for game in st.session_state.schedule]
            )

            prompt = f"""You are a cricket fixture scheduling assistant.
Here is the current fixture schedule:
{schedule_text}

The user asks: {user_input}

If the user wants to reschedule a fixture, respond ONLY with a JSON object in exactly this format:
{{"action": "reschedule", "home_team": "Team Name", "away_team": "Team Name", "new_date": "DD/MM/YYYY"}}

If the user is just asking a question, answer helpfully and concisely in plain English.
Do not return JSON for questions, only for reschedule requests."""

            response = model.generate_content(prompt)
            reply = response.text.strip()

            import json
            action_taken = False

            try:
                clean = reply.replace("```json", "").replace("```", "").strip()
                data = json.loads(clean)

                if data.get("action") == "reschedule":
                    day, month, year = data["new_date"].split("/")
                    new_date = date(int(year), int(month), int(day))

                    updated_schedule, success = reschedule_game(
                        st.session_state.schedule,
                        data["home_team"],
                        data["away_team"],
                        new_date
                    )

                    if success:
                        st.session_state.schedule = updated_schedule
                        reply = f"Done — {data['home_team']} vs {data['away_team']} has been moved to {data['new_date']}."
                    else:
                        reply = f"I couldn't find a fixture between {data['home_team']} and {data['away_team']}. Please check the team names and try again."

                    action_taken = True

            except:
                pass

            st.session_state.chat_history.append({"role": "assistant", "content": reply})
            st.rerun()

else:
    st.markdown("""
    <div style="text-align:center; padding: 5rem 2rem;">
        <div style="font-size: 3rem; margin-bottom: 1rem;">🏏</div>
        <h2 style="font-family: 'Outfit', sans-serif; color: #1A1A2E; font-weight: 600;">Ready to schedule</h2>
        <p style="color: #6B7280; font-size: 0.95rem; font-weight: 300;">Enter your teams and settings in the sidebar, then click Generate Fixtures</p>
    </div>
    """, unsafe_allow_html=True)