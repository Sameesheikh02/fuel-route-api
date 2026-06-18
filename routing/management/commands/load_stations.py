import pandas as pd
import time
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut
from django.core.management.base import BaseCommand
from django.contrib.gis.geos import Point
from routing.models import FuelStation

class Command(BaseCommand):
    help = 'Instantly load stations, then safely geocode missing coordinates with fallback'

    def handle(self, *args, **kwargs):
        self.stdout.write(self.style.WARNING("--- PHASE 1: INSTANT DATA SYNC ---"))
        
        # 1. Load and instantly remove duplicate IDs from the CSV using pandas
        df = pd.read_csv('fuel_prices.csv')
        df = df.drop_duplicates(subset=['OPIS Truckstop ID'], keep='last')
        
        # 2. Fetch all existing stations from the DB into memory
        existing_stations = {s.opis_id: s for s in FuelStation.objects.all()}
        
        to_create = []
        to_update = []

        for _, row in df.iterrows():
            opis_id = row['OPIS Truckstop ID']
            price = row['Retail Price']

            if opis_id in existing_stations:
                station = existing_stations[opis_id]
                # Only update if the price actually changed
                if station.price != price:
                    station.price = price
                    to_update.append(station)
            else:
                # Create new station (temporarily without coordinates)
                to_create.append(FuelStation(
                    opis_id=opis_id,
                    name=row['Truckstop Name'].strip(),
                    address=row['Address'],
                    city=row['City'],
                    state=row['State'],
                    rack_id=row['Rack ID'],
                    price=price,
                    location=None  # We will fill this in Phase 2
                ))

        # Execute massive bulk operations
        if to_update:
            FuelStation.objects.bulk_update(to_update, ['price'], batch_size=1000)
            self.stdout.write(self.style.SUCCESS(f"Instantly updated {len(to_update)} prices."))
        if to_create:
            FuelStation.objects.bulk_create(to_create, batch_size=1000)
            self.stdout.write(self.style.SUCCESS(f"Instantly created {len(to_create)} new stations."))

        self.stdout.write(self.style.SUCCESS("Phase 1 Complete! All data is securely in the database."))

        # ==========================================
        
        # ONLY target stations that do not have coordinates yet
        stations_to_geocode = FuelStation.objects.filter(location__isnull=True)
        total_missing = stations_to_geocode.count()

        if total_missing == 0:
            self.stdout.write(self.style.SUCCESS("\nAll stations have coordinates. You are fully ready!"))
            return

        self.stdout.write(self.style.WARNING(f"\n--- PHASE 2: GEOCODING {total_missing} MISSING LOCATIONS ---"))
        self.stdout.write("Note: You can stop (Ctrl+C) anytime and resume later without losing progress.")

        geolocator = Nominatim(user_agent="fuel_routing_enterprise_app")
        geocode_cache = {}
        success_count = 0

        for station in stations_to_geocode:
            clean_addr = str(station.address).split(', EXIT')[0].split(' &')[0].strip()
            full_address = f"{clean_addr}, {station.city}, {station.state}, USA"
            fallback_address = f"{station.city}, {station.state}, USA"

            if full_address in geocode_cache:
                station.location = geocode_cache[full_address]
                station.save(update_fields=['location'])
                success_count += 1
                continue
                
            if fallback_address in geocode_cache:
                station.location = geocode_cache[fallback_address]
                station.save(update_fields=['location'])
                success_count += 1
                continue

            try:
                # Attempt 1: Try specific highway/street address
                location = geolocator.geocode(full_address, timeout=10)
                
                # Attempt 2: Fallback to just City, State if Attempt 1 fails
                if not location:
                    time.sleep(1.1)  # Respect API limits before second attempt
                    location = geolocator.geocode(fallback_address, timeout=10)

                # Only save to the database if we successfully found coordinates
                if location:
                    point = Point(location.longitude, location.latitude, srid=4326)
                    station.location = point
                    
                    geocode_cache[full_address] = point
                    geocode_cache[fallback_address] = point
                    
                    station.save(update_fields=['location'])
                    success_count += 1
                else:
                    self.stdout.write(self.style.ERROR(f"Could not resolve any location for: {station.name}"))

                # The unavoidable rate limit for Nominatim
                time.sleep(1.1) 

            except GeocoderTimedOut:
                self.stdout.write(self.style.ERROR(f"Timeout on: {full_address}"))
                time.sleep(2)
                continue

            if success_count > 0 and success_count % 10 == 0:
                self.stdout.write(f"Geocoded {success_count} / {total_missing} missing stations...")

        self.stdout.write(self.style.SUCCESS("All geocoding complete!"))