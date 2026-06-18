import requests
import polyline
import concurrent.futures
from django.conf import settings
from django.contrib.gis.geos import LineString
from django.contrib.gis.db.models.functions import LineLocatePoint
from .models import FuelStation

def geocode_address(address_str):
    """Fetches coordinates. Thread-safe for concurrent execution."""
    url = "https://api.openrouteservice.org/geocode/search"
    params = {
        "api_key": settings.ORS_API_KEY,
        "text": address_str,
        "boundary.country": "USA",
        "size": 1
    }
    
    response = requests.get(url, params=params, timeout=5)
    if response.status_code != 200:
        raise ValueError(f"Geocoding API failed for: {address_str}")
        
    data = response.json()
    if not data.get("features"):
        raise ValueError(f"Could not geocode address: {address_str}")
        
    return data["features"][0]["geometry"]["coordinates"]

def get_optimal_fuel_route(start_address, end_address):
    # ==========================================
    # SPEED OPTIMIZATION 1: Concurrent Geocoding
    # Cuts the initial wait time in half by firing both requests at the same time.
    # ==========================================
    with concurrent.futures.ThreadPoolExecutor() as executor:
        future_start = executor.submit(geocode_address, start_address)
        future_end = executor.submit(geocode_address, end_address)
        
        start_coords = future_start.result()
        end_coords = future_end.result()

    headers = {
        'Authorization': settings.ORS_API_KEY,
        'Content-Type': 'application/json'
    }
    
    # SPEED OPTIMIZATION 2: Minimal Payload
    # Turning off turn-by-turn text instructions shrinks the ORS download size massively
    body = {
        "coordinates": [start_coords, end_coords],
        "instructions": False 
    }
    
    response = requests.post('https://api.openrouteservice.org/v2/directions/driving-car', json=body, headers=headers)
    if response.status_code != 200:
        raise Exception("Routing API failed")

    route_data = response.json()['routes'][0]
    total_distance_miles = route_data['summary']['distance'] / 1609.34 
    
    route_coords = polyline.decode(route_data['geometry'])
    route_coords_lnglat = [(lng, lat) for lat, lng in route_coords]
    route_line = LineString(route_coords_lnglat, srid=4326)

    # ==========================================
    # SPEED OPTIMIZATION 3: Geometry Simplification
    # Removes thousands of microscopic road curves. PostGIS fractional math 
    # executes exponentially faster on a simplified geometric line.
    # ==========================================
    simplified_route = route_line.simplify(0.005, preserve_topology=True)

    # Approximate 2 miles in degrees
    search_radius = 2.0 / 69.0 
    
    stations_qs = FuelStation.objects.filter(
        location__isnull=False,
        location__dwithin=(simplified_route, search_radius)
    ).annotate(
        line_fraction=LineLocatePoint(simplified_route, 'location')
    ).order_by('line_fraction')

    stations = []
    for s in stations_qs:
        stations.append({
            'name': s.name,
            'price': s.price,
            'dist': s.line_fraction * total_distance_miles,
            'location': {'lat': s.location.y, 'lng': s.location.x}
        })

    stations.append({
        'name': 'Destination',
        'price': 0.0, 
        'dist': total_distance_miles,
        'location': {'lat': end_coords[1], 'lng': end_coords[0]}
    })

    # 4. Realistic Greedy Optimization Algorithm
    current_loc = 0.0
    current_fuel = 500.0  
    total_cost = 0.0
    curr_station = {'name': 'Start', 'price': 0.0, 'dist': 0.0}
    purchases = []

    while current_loc + current_fuel < total_distance_miles:
        reachable = [s for s in stations if current_loc < s['dist'] <= current_loc + 500.0]
        
        if not reachable:
            raise ValueError(f"Route impossible: Gap larger than 500 miles detected near mile {current_loc}")

        cheaper_station = next((s for s in reachable if s['price'] < curr_station['price']), None)

        if cheaper_station:
            fuel_needed = cheaper_station['dist'] - current_loc
            if current_fuel < fuel_needed:
                gallons_to_buy = (fuel_needed - current_fuel) / 10.0
                
                # ==========================================
                # REALISM OPTIMIZATION: The Practicality Rule
                # Never stop for less than 10 gallons. Over-buy slightly to reach the cheap 
                # station comfortably, avoiding micro-stops.
                # ==========================================
                if gallons_to_buy < 10.0:
                    gallons_to_buy = 10.0
                    
                # Prevent overflowing the 500-mile (50 gallon) tank capacity
                if current_fuel + (gallons_to_buy * 10) > 500.0:
                    gallons_to_buy = (500.0 - current_fuel) / 10.0

                cost = gallons_to_buy * curr_station['price']
                total_cost += cost
                current_fuel += (gallons_to_buy * 10.0)
                
                if curr_station['dist'] > 0: 
                    purchases.append({
                        'station': curr_station['name'],
                        'price_per_gallon': curr_station['price'],
                        'gallons': round(gallons_to_buy, 2),
                        'cost': round(cost, 2),
                        'location': curr_station['location']
                    })

            current_fuel -= (cheaper_station['dist'] - current_loc)
            current_loc = cheaper_station['dist']
            curr_station = cheaper_station

        else:
            # We are at the cheapest station in range. Fill up to maximum needed.
            miles_to_end = total_distance_miles - current_loc
            target_fuel = min(500.0, miles_to_end)
            
            if current_fuel < target_fuel:
                gallons_to_buy = (target_fuel - current_fuel) / 10.0
                cost = gallons_to_buy * curr_station['price']
                total_cost += cost
                current_fuel = target_fuel
                
                if curr_station['dist'] > 0:
                    purchases.append({
                        'station': curr_station['name'],
                        'price_per_gallon': curr_station['price'],
                        'gallons': round(gallons_to_buy, 2),
                        'cost': round(cost, 2),
                        'location': curr_station['location']
                    })

            next_station = min(reachable, key=lambda s: s['price'])
            current_fuel -= (next_station['dist'] - current_loc)
            current_loc = next_station['dist']
            curr_station = next_station

    return {
        "route_geometry": route_data['geometry'],
        "total_distance_miles": round(total_distance_miles, 2),
        "total_fuel_cost": round(total_cost, 2),
        "fuel_stops": purchases
    }