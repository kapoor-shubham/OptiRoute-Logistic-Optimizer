import streamlit as st
import folium
from streamlit_folium import st_folium
import pandas as pd

# --- Source Selector ---
import math
import copy

def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*(math.sin(dlambda/2)**2)
    return 2 * R * math.asin(math.sqrt(a))

def assign_orders_to_warehouses(warehouses, orders, transport_cost_per_km=0.5, backorder_penalty=50.0):
    whs = copy.deepcopy(warehouses)
    assignments = []
    for o in orders:
        qty = o.get("qty", 1)
        distances = [(haversine_km(o["lat"], o["lon"], w["lat"], w["lon"]), w) for w in whs]
        distances.sort(key=lambda x: x[0])
        assigned, dist_km, backorder = None, None, False
        for d, w in distances:
            if w.get("inventory", 0) >= qty:
                assigned, dist_km = w, d
                w["inventory"] -= qty
                break
        if not assigned:  # nearest but out of stock
            d, w = distances[0]
            assigned, dist_km, backorder = w, d, True
        transport_cost = dist_km * transport_cost_per_km
        item_cost = assigned.get("unit_cost", 0.0) * qty
        total_cost = transport_cost + item_cost + (backorder_penalty if backorder else 0.0)
        assignments.append({
            "order_id": o["id"], "warehouse_id": assigned["id"], "warehouse_name": assigned["name"],
            "dist_km": round(dist_km, 2), "transport_cost": round(transport_cost, 2),
            "item_cost": round(item_cost, 2), "backorder": backorder,
            "total_cost": round(total_cost, 2), "qty": qty,
            "lat": o["lat"], "lon": o["lon"]
        })
    return assignments

# --- Route Planner (OR-Tools) ---
from ortools.constraint_solver import pywrapcp, routing_enums_pb2

def build_distance_matrix(depot, customers):
    locations = [depot] + customers
    n = len(locations)
    matrix = [[0]*n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            if i != j:
                matrix[i][j] = int(haversine_km(locations[i]["lat"], locations[i]["lon"],
                                                locations[j]["lat"], locations[j]["lon"]) * 1000)
    return matrix

def solve_vrp(distance_matrix, num_vehicles=1, depot_index=0, time_limit_s=5):
    n = len(distance_matrix)
    manager = pywrapcp.RoutingIndexManager(n, num_vehicles, depot_index)
    routing = pywrapcp.RoutingModel(manager)
    def dist_cb(from_idx, to_idx):
        return distance_matrix[manager.IndexToNode(from_idx)][manager.IndexToNode(to_idx)]
    transit_idx = routing.RegisterTransitCallback(dist_cb)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_idx)
    params = pywrapcp.DefaultRoutingSearchParameters()
    params.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    params.time_limit.seconds = time_limit_s
    solution = routing.SolveWithParameters(params)
    routes = []
    if solution:
        for v in range(num_vehicles):
            idx, route = routing.Start(v), []
            while not routing.IsEnd(idx):
                route.append(manager.IndexToNode(idx))
                idx = solution.Value(routing.NextVar(idx))
            route.append(manager.IndexToNode(idx))
            routes.append(route)
    return routes

# --- Demo Data ---
warehouses = [
    {"id": 1, "name": "WH-A", "lat": 28.61, "lon": 77.23, "inventory": 10, "unit_cost": 5.0},
    {"id": 2, "name": "WH-B", "lat": 28.70, "lon": 77.10, "inventory": 5, "unit_cost": 4.5},
]
orders = [{"id": i+1, "lat": 28.61 + 0.01*(i%5), "lon": 77.23 + 0.01*((i//5)%3), "qty": 1} for i in range(12)]

# --- Streamlit App ---
def run_dashboard():
    st.title("🚛 Logistics Optimizer Agent")
    st.write("Two functional agents: **Source Selector** + **Route Planner**.")

    # Initialize state
    if "assignments" not in st.session_state: st.session_state["assignments"] = None
    if "routes" not in st.session_state: st.session_state["routes"] = None

    # --- Step 1: Source Selector ---
    if st.button("Select Source (Assign Orders)"):
        st.session_state["assignments"] = assign_orders_to_warehouses(warehouses, orders)
        st.session_state["routes"] = None  # reset routes

    if st.session_state["assignments"]:
        st.subheader("📦 Order Assignments")
        df = pd.DataFrame(st.session_state["assignments"])
        st.dataframe(df)

        # Download assignments
        csv = df.to_csv(index=False).encode("utf-8")
        st.download_button("⬇️ Download Assignments CSV", csv, "assignments.csv", "text/csv")

        # --- Step 2: Route Planner ---
        wh_ids = sorted({a["warehouse_id"] for a in st.session_state["assignments"]})
        selected_wh = st.selectbox("Select warehouse for routing", wh_ids)
        if st.button("Plan Route"):
            depot = next(w for w in warehouses if w["id"] == selected_wh)
            customers = [{"id": a["order_id"], "lat": a["lat"], "lon": a["lon"]}
                         for a in st.session_state["assignments"] if a["warehouse_id"] == selected_wh]
            dm = build_distance_matrix(depot, customers)
            st.session_state["routes"] = solve_vrp(dm, num_vehicles=1)

    # Show routes if available
    if st.session_state["routes"]:
        st.subheader("🛣 Optimized Routes")
        st.write(st.session_state["routes"])

        # Map
        selected_wh = next(w for w in warehouses if w["id"] == st.session_state["assignments"][0]["warehouse_id"])
        depot = selected_wh
        customers = [{"id": a["order_id"], "lat": a["lat"], "lon": a["lon"]}
                     for a in st.session_state["assignments"] if a["warehouse_id"] == depot["id"]]
        m = folium.Map(location=[depot["lat"], depot["lon"]], zoom_start=12)
        folium.Marker([depot["lat"], depot["lon"]], popup=f"Warehouse {depot['name']}",
                      icon=folium.Icon(color="red")).add_to(m)
        for c in customers:
            folium.Marker([c["lat"], c["lon"]], popup=f"Order {c['id']}").add_to(m)
        # draw polyline
        route = st.session_state["routes"][0]
        coords = [(depot["lat"], depot["lon"])] + [(customers[i-1]["lat"], customers[i-1]["lon"]) for i in route if i != 0] + [(depot["lat"], depot["lon"])]
        folium.PolyLine(coords, color="blue", weight=2.5).add_to(m)
        st_folium(m, width=700, height=500)


if __name__ == "__main__":
    run_dashboard()
