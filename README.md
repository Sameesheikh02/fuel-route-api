# Fuel Optimization Routing API

A high-performance Django/PostGIS routing engine designed to calculate the most cost-effective fuel stops for long-haul trucking, optimized for speed and real-world logistics constraints.

## 🚀 Performance Optimizations
* **Concurrent Geocoding:** Utilizes `ThreadPoolExecutor` to perform parallel API requests, slashing initial latency in half.
* **Geometric Simplification:** Implements PostGIS `simplify()` on route polylines to reduce computational load, allowing sub-second responses for cross-country routes.
* **Realistic Greedy Algorithm:** A custom logic engine that avoids "micro-stops" by enforcing a 10-gallon minimum purchase rule, mimicking real driver behavior.
* **Payload Compression:** Utilizes encoded polyline geometry for highly efficient data transfer.

## 🛠 Tech Stack
- **Backend:** Django & Django REST Framework
- **Spatial:** PostGIS (Geometry calculations)
- **APIs:** OpenRouteService (Geocoding & Routing)
- **Logic:** Custom Greedy Optimization Algorithm

## ⚙️ Installation
1. Clone the repo.
2. Install requirements: `pip install -r requirements.txt`
3. Configure your `settings.py` with your `ORS_API_KEY`.
4. Run migrations: `python manage.py migrate`
5. Load your data: `python manage.py loaddata routing/fixtures/initial_data.json`

## 🔌 API Usage
**Endpoint:** `POST /api/plan-route/`
**Payload:**
```json
{
    "start": "Miami, FL",
    "end": "Seattle, WA"
}