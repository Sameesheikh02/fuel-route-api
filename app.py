import streamlit as st
import requests
import polyline
import pandas as pd
import folium
from streamlit_folium import st_folium

# --- PAGE CONFIGURATION ---
st.set_page_config(
    page_title="Optimal Fuel Route Planner",
    page_icon="⛽",
    layout="wide"
)

st.title("⛽ Smart Fuel Route Optimizer")
st.markdown("Find the cheapest fuel stops along your path while ensuring you never run out of gas.")

# --- SIDEBAR CONTROLS ---
st.sidebar.header("Route Settings")

DJANGO_API_URL = st.sidebar.text_input(
    "Django API URL", 
    value="http://127.0.0.1:8000/api/plan-route/"
)

start_node = st.sidebar.text_input("Start Location", value="New York, NY")
end_node = st.sidebar.text_input("Destination", value="Los Angeles, CA")

submit_btn = st.sidebar.button("Calculate Optimal Route", type="primary")

# --- MAIN INTERACTION LOGIC ---

# 1. When the button is clicked, fetch the data and save it to memory
if submit_btn:
    if not start_node or not end_node:
        st.error("Please enter both a starting location and a destination.")
    else:
        with st.spinner("Calculating optimal route and fuel choices..."):
            payload = {"start": start_node, "end": end_node}
            try:
                response = requests.post(DJANGO_API_URL, json=payload, timeout=30)
                
                if response.status_code == 200:
                    # Save the successful data to Streamlit's session state
                    st.session_state["route_data"] = response.json()
                elif response.status_code == 400:
                    st.error(f"Bad Request: {response.json().get('error', 'Invalid inputs')}")
                elif response.status_code == 500:
                    st.error(f"Algorithmic Error: {response.json().get('error', 'Unknown backend issue')}")
                else:
                    st.error(f"Unexpected status code {response.status_code}: {response.text}")
                    
            except requests.exceptions.ConnectionError:
                st.error(f"Could not connect to the Django API backend at {DJANGO_API_URL}.")

# 2. If data exists in memory (even after a rerun), render the UI
if "route_data" in st.session_state:
    data = st.session_state["route_data"]
    
    total_distance = data.get("total_distance_miles", 0)
    total_cost = data.get("total_fuel_cost", 0)
    fuel_stops = data.get("fuel_stops", [])
    encoded_geometry = data.get("route_geometry", "")
    
    # Summary Metrics
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Distance", f"{total_distance:,.2f} miles")
    col2.metric("Total Fuel Cost", f"${total_cost:,.2f}")
    col3.metric("Optimized Fuel Stops", f"{len(fuel_stops)} stops")
    
    st.write("---")
    
    decoded_coords = polyline.decode(encoded_geometry)
    
    # Render Map View
    if decoded_coords:
        st.subheader("Route & Stop Visualization")
        
        mid_idx = len(decoded_coords) // 2
        m = folium.Map(location=decoded_coords[mid_idx], zoom_start=5)
        
        folium.PolyLine(
            locations=decoded_coords,
            color="blue",
            weight=4,
            opacity=0.7,
            tooltip="Optimized Route Path"
        ).add_to(m)
        
        folium.Marker(location=decoded_coords[0], popup="Start", icon=folium.Icon(color="green")).add_to(m)
        folium.Marker(location=decoded_coords[-1], popup="Destination", icon=folium.Icon(color="red")).add_to(m)
        
        for idx, stop in enumerate(fuel_stops):
            loc = stop["location"]
            popup_text = f"""
            <b>Stop #{idx+1}: {stop['station']}</b><br>
            Price: ${stop['price_per_gallon']}/gal<br>
            Gallons to Refuel: {stop['gallons']} gal<br>
            Total Stop Cost: ${stop['cost']}
            """
            folium.Marker(
                location=[loc["lat"], loc["lng"]],
                popup=folium.Popup(popup_text, max_width=300),
                icon=folium.Icon(color="orange", icon="gas-pump", prefix="fa"),
                tooltip=f"Stop #{idx+1}: {stop['station']}"
            ).add_to(m)
        
        # FIXED: returned_objects=[] prevents the map from triggering infinite loop reruns
        st_folium(m, width="100%", height=500, returned_objects=[])

    # Structured Data Breakdown Table
    if fuel_stops:
        st.subheader("📋 Step-by-Step Refueling Schedule")
        
        table_data = []
        for idx, stop in enumerate(fuel_stops):
            table_data.append({
                "Stop Order": idx + 1,
                "Station Name": stop["station"],
                "Price Per Gallon ($)": stop["price_per_gallon"],
                "Gallons to Purchase": stop["gallons"],
                "Estimated Cost ($)": stop["cost"]
            })
        
        df_stops = pd.DataFrame(table_data)
        st.dataframe(df_stops, use_container_width=True, hide_index=True)
    else:
        st.info("No fuel stops required! Your initial tank capacity of 500 miles is enough to reach your destination.")