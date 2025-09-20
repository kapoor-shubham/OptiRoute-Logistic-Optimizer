import os
import json
import random
import streamlit as st
import folium
from streamlit_folium import st_folium
import openai

# -------------------------------
# Setup OpenAI Key
# -------------------------------
openai.api_key = os.getenv("OPENAI_API_KEY")

# -------------------------------
# OpenAI Agents
# -------------------------------

st.write("✅ Running correct test_app.py from:", os.path.abspath(__file__))

def select_source(warehouses, customers, optimization_goal="cost"):
    prompt = f"""
    You are a logistics optimization agent.
    Warehouses data: {json.dumps(warehouses)}
    Customers data: {json.dumps(customers)}
    Goal: Optimize for {optimization_goal}.

    Select the best warehouse(s) that minimizes {optimization_goal}, 
    while meeting demand. Respond in valid JSON format:

    {{
      "selected_warehouses": ["W1", "W3"],
      "reasoning": "shortest average distance and lowest cost"
    }}
    """

    response = openai.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0
    )

    result_text = response.choices[0].message.content.strip()
    try:
        return json.loads(result_text)
    except:
        return {"error": "Invalid response", "raw": result_text}


def plan_routes(selected_warehouses, customers, optimization_goal="time"):
    prompt = f"""
    You are a route optimization agent.
    Selected Warehouses: {selected_warehouses}
    Customers: {json.dumps(customers)}
    Goal: Optimize delivery routes for {optimization_goal}.

    Generate an ordered route plan.
    Respond in valid JSON format:

    {{
      "routes": [
        {{"warehouse": "W1", "order": ["C1", "C3", "C2"]}},
        {{"warehouse": "W2", "order": ["C4", "C5"]}}
      ],
      "reasoning": "minimized travel time using nearest neighbor logic"
    }}
    """

    response = openai.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0
    )

    result_text = response.choices[0].message.content.strip()
    try:
        return json.loads(result_text)
    except:
        return {"error": "Invalid response", "raw": result_text}


# -------------------------------
# Sample Data Generator
# -------------------------------

def generate_sample_data():
    warehouses = [
        {"id": "W1", "cost": 100, "time": 12, "emissions": 50, "location": (28.61, 77.20)}, # Delhi
        {"id": "W2", "cost": 120, "time": 10, "emissions": 40, "location": (19.07, 72.87)}, # Mumbai
        {"id": "W3", "cost": 90, "time": 15, "emissions": 60, "location": (13.08, 80.27)},  # Chennai
    ]

    customers = []
    for i in range(1, 6):
        customers.append({
            "id": f"C{i}",
            "demand": random.randint(10, 50),
            "location": (
                round(random.uniform(15.0, 28.0), 2),
                round(random.uniform(70.0, 85.0), 2)
            )
        })

    return warehouses, customers


# -------------------------------
# Streamlit App
# -------------------------------

st.set_page_config(page_title="Logistics Optimizer Agent", layout="wide")
st.title("🚚 Logistics Optimizer Agent (OpenAI-Powered)")

# Sidebar Controls
st.sidebar.header("Controls")
optimization_goal = st.sidebar.selectbox("Optimization Goal", ["cost", "time", "emissions"])
run_agents = st.sidebar.button("Run OpenAI Agents")

# Generate Data
if "warehouses" not in st.session_state:
    st.session_state.warehouses, st.session_state.customers = generate_sample_data()

if st.button("🔄 Regenerate Sample Data"):
    st.session_state.warehouses, st.session_state.customers = generate_sample_data()

warehouses = st.session_state.warehouses
customers = st.session_state.customers

# Show Raw Data
with st.expander("📦 Warehouses Data"):
    st.json(warehouses)

with st.expander("🧑‍🤝‍🧑 Customers Data"):
    st.json(customers)

# Run OpenAI Agents
if run_agents:
    st.subheader("🤖 Agent Results")

    selected = select_source(warehouses, customers, optimization_goal)
    st.write("### Source Selector Agent Result")
    st.json(selected)

    if "selected_warehouses" in selected:
        routes = plan_routes(selected["selected_warehouses"], customers, optimization_goal)
        st.write("### Route Planner Agent Result")
        st.json(routes)

        # Save to session state for map + download
        st.session_state.routes = routes
    else:
        st.error("Source selection failed.")

# -------------------------------
# Map Visualization
# -------------------------------
if "routes" in st.session_state:
    st.subheader("🗺️ Optimized Routes Map")

    m = folium.Map(location=[22.5, 78.9], zoom_start=5)

    # Plot Warehouses
    for w in warehouses:
        folium.Marker(
            location=w["location"],
            popup=f"Warehouse {w['id']}",
            icon=folium.Icon(color="blue", icon="home"),
        ).add_to(m)

    # Plot Customers
    for c in customers:
        folium.Marker(
            location=c["location"],
            popup=f"Customer {c['id']} (Demand {c['demand']})",
            icon=folium.Icon(color="green", icon="user"),
        ).add_to(m)

    # Draw Routes
    if "routes" in st.session_state.routes:
        for route in st.session_state.routes["routes"]:
            wh_id = route["warehouse"]
            wh = next((w for w in warehouses if w["id"] == wh_id), None)
            if not wh:
                continue

            points = [wh["location"]]
            for cid in route["order"]:
                cust = next((c for c in customers if c["id"] == cid), None)
                if cust:
                    points.append(cust["location"])

            folium.PolyLine(points, color="red", weight=3, opacity=0.8).add_to(m)

    st_folium(m, width=700, height=500)

    # Download Button
    st.download_button(
        label="⬇️ Download Routes JSON",
        data=json.dumps(st.session_state.routes, indent=2),
        file_name="optimized_routes.json",
        mime="application/json",
    )
