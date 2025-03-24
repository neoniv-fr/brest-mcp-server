import os
from dotenv import load_dotenv
import requests
from google.transit import gtfs_realtime_pb2
from mcp.server import FastMCP
from datetime import datetime
from typing import Dict, List, Optional
import json
import zipfile
import io

# Charger les variables d'environnement depuis le fichier .env
load_dotenv()

# Configuration : URLs des flux et paramètres depuis .env
NETWORK_URLS = {
    "bibus": {
        "vehicle_positions": os.getenv("GTFS_VEHICLE_POSITIONS_URL", "https://proxy.transport.data.gouv.fr/resource/bibus-brest-gtfs-rt-vehicle-position"),
        "trip_updates": os.getenv("GTFS_TRIP_UPDATES_URL", "https://proxy.transport.data.gouv.fr/resource/bibus-brest-gtfs-rt-trip-update"),
        "service_alerts": os.getenv("GTFS_SERVICE_ALERTS_URL", "https://proxy.transport.data.gouv.fr/resource/bibus-brest-gtfs-rt-alerts"),
        "gtfs_static": os.getenv("GTFS_STATIC_URL", "https://s3.eu-west-1.amazonaws.com/files.orchestra.ratpdev.com/networks/bibus/exports/medias.zip"),
        "open_agenda": os.getenv("OPEN_AGENDA_URL", "https://api.openagenda.com/v2/events?search=brest&limit=10&key=cf7141c803f746f0abec6bb1667d55e2"),
        "weather_infoclimat": os.getenv("WEATHER_INFOCLIMAT_URL", "https://www.infoclimat.fr/public-api/gfs/json?_ll=48.4475,-4.4181&_auth=ARtTRAV7ByVec1FmAnRVfFU9BzIMegIlVCgDYA1oVyoDaFIzVTVcOlE%2FBnsHKFZgBypXNFphU2MCaVAoD31RMAFrUz8FbgdgXjFRNAItVX5VewdmDCwCJVQ1A2QNflc9A2dSKFU3XDZRNwZ6Bz5WZAcrVyhaZFNsAmVQNQ9nUTYBZFM1BWYHbV4uUSwCNFVmVTIHMwwxAj9UNQNkDWRXNwNgUmBVN1w3USAGZwc%2BVmcHPVc2Wm1TbwJkUCgPfVFLARFTKgUmBydeZFF1Ai9VNFU4BzM%3D&_c=38fc48e42684d2b24279d0b02e2d0713")
    },
    "star": {
        "vehicle_positions": "https://proxy.transport.data.gouv.fr/resource/star-rennes-gtfs-rt-vehicle-position",
        "trip_updates": "https://proxy.transport.data.gouv.fr/resource/star-rennes-gtfs-rt-trip-update",
        "service_alerts": "https://proxy.transport.data.gouv.fr/resource/star-rennes-gtfs-rt-alerts"
    },
    "tub": {
        "vehicle_positions": "https://proxy.transport.data.gouv.fr/resource/tub-saint-brieuc-gtfs-rt-vehicle-position",
        "trip_updates": "https://proxy.transport.data.gouv.fr/resource/tub-saint-brieuc-gtfs-rt-trip-update",
        "service_alerts": "https://proxy.transport.data.gouv.fr/resource/tub-saint-brieuc-gtfs-rt-alerts"
    }
}

REFRESH_INTERVAL = int(os.getenv("GTFS_REFRESH_INTERVAL", "30"))
HOST = os.getenv("MCP_HOST", "0.0.0.0")  # Écoute sur toutes les interfaces pour SSE
PORT = int(os.getenv("MCP_PORT", "8000"))  # Port fixe par défaut pour SSE
NETWORK = os.getenv("NETWORK", "bibus")  # Réseau par défaut

# Initialiser le serveur MCP
mcp = FastMCP("TransitServer", host=HOST, port=PORT)

# Cache en mémoire pour les données
_cache = {
    "vehicle_positions": {"timestamp": 0, "data": None, "last_update": None},
    "trip_updates": {"timestamp": 0, "data": None, "last_update": None},
    "service_alerts": {"timestamp": 0, "data": None, "last_update": None},
    "gtfs_static": {"timestamp": 0, "data": None, "last_update": None},
    "open_agenda": {"timestamp": 0, "data": None, "last_update": None},
    "weather_infoclimat": {"timestamp": 0, "data": None, "last_update": None}
}

def _fetch_feed(feed_type: str, is_static: bool = False, is_json: bool = False) -> Optional[any]:
    """Récupère un flux et le met en cache."""
    now = datetime.now().timestamp()
    cache = _cache[feed_type]
    
    if now - cache["timestamp"] < REFRESH_INTERVAL and cache["data"]:
        return cache["data"]
    
    try:
        url = NETWORK_URLS[NETWORK][feed_type]
        print(f"Fetching {feed_type} from {url}")
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        
        if is_static:
            data = response.content  # Fichier ZIP brut
            print(f"OK {feed_type} - GTFS static file downloaded (not parsed)")
        elif is_json:
            data = response.json()
            print(f"OK {feed_type} - JSON data fetched ({len(data) if isinstance(data, list) else 'dict'})")
        else:
            feed = gtfs_realtime_pb2.FeedMessage()
            feed.ParseFromString(response.content)
            data = feed
            print(f"OK {feed_type} - {len(feed.entity)} entities")
        
        cache["data"] = data
        cache["timestamp"] = now
        cache["last_update"] = now
        return data
    except Exception as e:
        print(f"Error fetching {feed_type}: {str(e)}")
        return cache["data"] if cache["data"] else None

def _parse_vehicle_positions(feed: gtfs_realtime_pb2.FeedMessage) -> List[Dict]:
    """Transforme un FeedMessage de positions véhicules en une liste de dictionnaires."""
    data = []
    for entity in feed.entity:
        if not entity.HasField('vehicle'):
            continue
        vp = entity.vehicle
        vehicle_info = {
            "vehicle_id": entity.id or (vp.vehicle.id if vp.vehicle.HasField('id') else vp.vehicle.label),
            "latitude": vp.position.latitude if vp.position else None,
            "longitude": vp.position.longitude if vp.position else None,
            "bearing": vp.position.bearing if vp.position.HasField('bearing') else None,
            "speed": vp.position.speed if vp.position.HasField('speed') else None,
            "trip_id": vp.trip.trip_id if vp.HasField('trip') else None,
            "route_id": vp.trip.route_id if vp.HasField('trip') else None,
            "start_time": vp.trip.start_time if vp.HasField('trip') else None,
            "start_date": vp.trip.start_date if vp.HasField('trip') else None,
            "timestamp": vp.timestamp if vp.HasField('timestamp') else None
        }
        data.append(vehicle_info)
    return data

def _parse_trip_updates(feed: gtfs_realtime_pb2.FeedMessage) -> List[Dict]:
    """Transforme un FeedMessage de mises à jour de trajets en une liste de dictionnaires."""
    data = []
    for entity in feed.entity:
        if not entity.HasField('trip_update'):
            continue
        tu = entity.trip_update
        trip_info = {
            "trip_id": tu.trip.trip_id,
            "route_id": tu.trip.route_id,
            "start_time": tu.trip.start_time,
            "start_date": tu.trip.start_date,
            "vehicle_id": tu.vehicle.id if tu.vehicle.HasField('id') else None,
            "stop_time_updates": [
                {
                    "stop_id": stu.stop_id,
                    "arrival_delay": stu.arrival.delay if stu.HasField('arrival') and stu.arrival.HasField('delay') else 0,
                    "departure_delay": stu.departure.delay if stu.HasField('departure') and stu.departure.HasField('delay') else 0,
                    "arrival_time": stu.arrival.time if stu.HasField('arrival') and stu.arrival.HasField('time') else None,
                    "departure_time": stu.departure.time if stu.HasField('departure') and stu.departure.HasField('time') else None,
                    "schedule_relationship": str(stu.schedule_relationship)
                } for stu in tu.stop_time_update
            ]
        }
        data.append(trip_info)
    return data

def _parse_service_alerts(feed: gtfs_realtime_pb2.FeedMessage) -> List[Dict]:
    """Transforme un FeedMessage d'alertes de service en une liste de dictionnaires."""
    cause_map = {1: "UNKNOWN_CAUSE", 2: "OTHER_CAUSE", 3: "TECHNICAL_PROBLEM", 4: "STRIKE", 5: "DEMONSTRATION", 6: "ACCIDENT", 7: "HOLIDAY", 8: "WEATHER", 9: "MAINTENANCE", 10: "CONSTRUCTION", 11: "POLICE_ACTIVITY", 12: "MEDICAL_EMERGENCY"}
    effect_map = {1: "NO_SERVICE", 2: "REDUCED_SERVICE", 3: "SIGNIFICANT_DELAYS", 4: "DETOUR", 5: "ADDITIONAL_SERVICE", 6: "MODIFIED_SERVICE", 7: "OTHER_EFFECT", 8: "UNKNOWN_EFFECT", 9: "STOP_MOVED"}
    data = []
    for entity in feed.entity:
        if not entity.HasField('alert'):
            continue
        alert = entity.alert
        alert_info = {
            "alert_id": entity.id,
            "cause": cause_map.get(alert.cause, "UNKNOWN_CAUSE") if alert.HasField('cause') else None,
            "effect": effect_map.get(alert.effect, "UNKNOWN_EFFECT") if alert.HasField('effect') else None,
            "active_periods": [{"start": p.start, "end": p.end} for p in alert.active_period if p.HasField('start') or p.HasField('end')],
            "routes": [ie.route_id for ie in alert.informed_entity if ie.HasField('route_id')],
            "stops": [ie.stop_id for ie in alert.informed_entity if ie.HasField('stop_id')],
            "description": alert.description_text.translation[0].text if alert.description_text.translation else None,
            "header": alert.header_text.translation[0].text if alert.header_text.translation else None
        }
        data.append(alert_info)
    return data

def _parse_open_agenda(data: Dict) -> List[Dict]:
    """Transforme les données Open Agenda en une liste de dictionnaires."""
    events = data.get("events", []) if isinstance(data, dict) else data
    return [
        {
            "uid": event.get("uid"),
            "title": event.get("title", {}).get("fr"),
            "description": event.get("description", {}).get("fr"),
            "location": event.get("location", {}).get("name"),
            "latitude": event.get("location", {}).get("latitude"),
            "longitude": event.get("location", {}).get("longitude"),
            "start_time": event.get("timings", [{}])[0].get("begin"),
            "end_time": event.get("timings", [{}])[0].get("end")
        } for event in events
    ]

def _parse_weather_infoclimat(data: Dict) -> Dict:
    """Transforme les données Infoclimat en un dictionnaire structuré."""
    forecasts = {}
    for timestamp, values in data.items():
        if timestamp.startswith("20"):  # Filtrer les timestamps valides
            forecasts[timestamp] = {
                "temperature_2m": values.get("temperature", {}).get("2m"),
                "wind_speed": values.get("vent_moyen", {}).get("10m"),
                "wind_gusts": values.get("vent_rafales", {}).get("10m"),
                "wind_direction": values.get("vent_direction", {}).get("10m"),
                "precipitation": values.get("pluie"),
                "humidity": values.get("humidite", {}).get("2m"),
                "pressure": values.get("pression", {}).get("niveau_de_la_mer")
            }
    return forecasts

def _get_vehicle_positions_data() -> List[Dict]:
    feed = _fetch_feed("vehicle_positions")
    if feed:
        return _parse_vehicle_positions(feed)
    return []

def _get_trip_updates_data() -> List[Dict]:
    feed = _fetch_feed("trip_updates")
    if feed:
        return _parse_trip_updates(feed)
    return []

def _get_service_alerts_data() -> List[Dict]:
    feed = _fetch_feed("service_alerts")
    if feed:
        return _parse_service_alerts(feed)
    return []

@mcp.tool("get_vehicles")
def get_vehicle_positions():
    return {
        "status": "success",
        "data": _get_vehicle_positions_data(),
        "lastUpdate": _cache["vehicle_positions"]["last_update"]
    }

@mcp.tool("get_trip_updates")
def get_trip_updates():
    return {
        "status": "success",
        "data": _get_trip_updates_data(),
        "lastUpdate": _cache["trip_updates"]["last_update"]
    }

@mcp.tool("get_alerts")
def get_service_alerts():
    return {
        "status": "success",
        "data": _get_service_alerts_data(),
        "lastUpdate": _cache["service_alerts"]["last_update"]
    }

@mcp.tool("get_events")
def get_open_agenda_events():
    data = _fetch_feed("open_agenda", is_json=True)
    return {"status": "success", "data": _parse_open_agenda(data) if data else [], "lastUpdate": _cache["open_agenda"]["last_update"]}

@mcp.tool("get_weather_forecast")
def get_weather_forecast():
    data = _fetch_feed("weather_infoclimat", is_json=True)
    return {"status": "success", "data": _parse_weather_infoclimat(data) if data else {}, "lastUpdate": _cache["weather_infoclimat"]["last_update"]}

@mcp.tool()
def get_vehicle(vehicle_id: str):
    vehicles = _get_vehicle_positions_data()
    for v in vehicles:
        if str(v.get("vehicle_id")) == str(vehicle_id):
            return v
    return None

@mcp.tool()
def get_trip_update(trip_id: str):
    trips = _get_trip_updates_data()
    for t in trips:
        if t.get("trip_id") == trip_id:
            return t
    return None

@mcp.tool()
def get_alert(alert_id: str):
    alerts = _get_service_alerts_data()
    for a in alerts:
        if a.get("alert_id") == alert_id:
            return a
    return None

@mcp.tool()
def count_vehicles():
    vehicles = _get_vehicle_positions_data()
    return {"status": "success", "data": len(vehicles)}

@mcp.tool()
def count_alerts():
    alerts = _get_service_alerts_data()
    return {"status": "success", "data": len(alerts)}

@mcp.tool()
def find_trips_by_route(route_id: str):
    trips = _get_trip_updates_data()
    return [t["trip_id"] for t in trips if t.get("route_id") == route_id]

@mcp.tool()
def find_vehicles_by_route(route_id: str) -> List[Dict]:
    vehicles = []
    feed = _fetch_feed("vehicle_positions")
    if not feed:
        return vehicles
        
    for entity in feed.entity:
        if entity.HasField('vehicle'):
            vp = entity.vehicle
            if vp.HasField('trip') and vp.trip.HasField('route_id') and vp.trip.route_id == route_id:
                vehicle_info = {
                    "vehicle_id": vp.vehicle.id if vp.vehicle.HasField('id') else vp.vehicle.label,
                    "position": {
                        "latitude": vp.position.latitude,
                        "longitude": vp.position.longitude,
                        "bearing": vp.position.bearing if vp.position.HasField('bearing') else None,
                        "speed": vp.position.speed if vp.position.HasField('speed') else None
                    },
                    "trip_id": vp.trip.trip_id,
                    "current_status": vp.current_status if vp.HasField('current_status') else None,
                    "timestamp": vp.timestamp if vp.HasField('timestamp') else None
                }
                vehicles.append(vehicle_info)
    return vehicles

@mcp.tool()
def find_alerts_by_route(route_id: str) -> List[Dict]:
    alerts = []
    feed = _fetch_feed("service_alerts")
    if not feed:
        return alerts
        
    for entity in feed.entity:
        if entity.HasField('alert'):
            alert = entity.alert
            for informed_entity in alert.informed_entity:
                if informed_entity.HasField('route_id') and informed_entity.route_id == route_id:
                    alert_info = {
                        "id": entity.id,
                        "effect": alert.effect,
                        "header": alert.header_text.translation[0].text if alert.header_text.translation else None,
                        "description": alert.description_text.translation[0].text if alert.description_text.translation else None,
                        "start": alert.active_period[0].start if alert.active_period else None,
                        "end": alert.active_period[0].end if alert.active_period else None
                    }
                    alerts.append(alert_info)
                    break
    return alerts

@mcp.resource("gtfs://vehicles")
def vehicles_resource() -> Dict:
    return get_vehicle_positions()

@mcp.resource("gtfs://vehicle/{vehicle_id}")
def vehicle_resource(vehicle_id: str) -> Dict:
    return get_vehicle(vehicle_id)

@mcp.resource("gtfs://route/{route_id}")
def route_resource(route_id: str) -> Dict:
    vehicles = find_vehicles_by_route(route_id)
    alerts = find_alerts_by_route(route_id)
    return {
        "status": "success",
        "data": {
            "route_id": route_id,
            "vehicles": vehicles,
            "alerts": alerts,
            "statistics": {
                "vehicle_count": len(vehicles),
                "alert_count": len(alerts)
            },
            "timestamp": datetime.now().isoformat()
        }
    }

@mcp.resource("gtfs://network/stats")
def network_stats_resource() -> Dict:
    return {
        "status": "success",
        "data": _get_network_statistics()
    }

def _get_network_statistics() -> Dict:
    vehicles = _get_vehicle_positions_data()
    trips = _get_trip_updates_data()
    return {
        "totalVehicles": len(vehicles),
        "vehiclesByStatus": _count_vehicles_by_status(vehicles),
        "averageDelay": _calculate_average_delay(trips),
        "routesWithAlerts": len(set(alert.get("route_id") for alert in _get_service_alerts_data() if alert.get("route_id"))),
        "onTimePerformance": _calculate_on_time_performance(trips)
    }

def _count_vehicles_by_status(vehicles: List[Dict]) -> Dict:
    status_count = {"IN_TRANSIT": 0, "STOPPED": 0, "UNKNOWN": 0}
    for vehicle in vehicles:
        current_status = vehicle.get("current_status", "UNKNOWN")
        status_count[current_status] = status_count.get(current_status, 0) + 1
    return status_count

def _calculate_average_delay(trips: List[Dict]) -> float:
    delays = [
        stop.get("arrival_delay", 0)
        for trip in trips
        for stop in trip.get("stop_time_updates", [])
    ]
    return sum(delays) / len(delays) if delays else 0

def _calculate_on_time_performance(trips: List[Dict], threshold: int = 180) -> float:
    total = 0
    on_time = 0
    for trip in trips:
        for stop in trip.get("stop_time_updates", []):
            total += 1
            if abs(stop.get("arrival_delay", 0)) < threshold:
                on_time += 1
    return (on_time / total * 100) if total > 0 else 100

@mcp.resource("gtfs://networks")
def available_networks_resource() -> Dict:
    networks = []
    for network, urls in NETWORK_URLS.items():
        networks.append({
            "id": network,
            "name": {
                "bibus": "Bibus (Brest)",
                "star": "STAR (Rennes)",
                "tub": "TUB (Saint-Brieuc)"
            }.get(network, network),
            "urls": urls
        })
    return {
        "status": "success",
        "data": networks,
        "count": len(networks)
    }

@mcp.resource("gtfs://network/{network}/vehicles")
def network_vehicles_resource(network: str) -> Dict:
    feed = _get_network_feed(network, "vehicle_positions")
    if not feed:
        return {"status": "error", "message": f"Réseau {network} non trouvé ou données indisponibles"}
    
    vehicles = []
    for entity in feed.entity:
        if entity.HasField('vehicle'):
            vp = entity.vehicle
            vehicle_info = {
                "vehicle_id": vp.vehicle.id if vp.vehicle.HasField('id') else vp.vehicle.label,
                "position": {
                    "latitude": vp.position.latitude,
                    "longitude": vp.position.longitude,
                    "bearing": vp.position.bearing if vp.position.HasField('bearing') else None,
                    "speed": vp.position.speed if vp.position.HasField('speed') else None
                },
                "trip_id": vp.trip.trip_id if vp.HasField('trip') else None,
                "route_id": vp.trip.route_id if vp.HasField('trip') else None,
                "current_status": vp.current_status if vp.HasField('current_status') else None,
                "timestamp": vp.timestamp if vp.HasField('timestamp') else None
            }
            vehicles.append(vehicle_info)
    return {
        "status": "success",
        "network": network,
        "data": vehicles,
        "count": len(vehicles),
        "timestamp": datetime.now().isoformat()
    }

def _get_network_feed(network: str, feed_type: str) -> Optional[gtfs_realtime_pb2.FeedMessage]:
    if network not in NETWORK_URLS:
        return None
    try:
        url = NETWORK_URLS[network][feed_type]
        print(f"Fetching {feed_type} from {network} at {url}")
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        feed = gtfs_realtime_pb2.FeedMessage()
        feed.ParseFromString(response.content)
        print(f"Successfully fetched {network} {feed_type} with {len(feed.entity)} entities")
        return feed
    except Exception as e:
        print(f"Error fetching {network} {feed_type}: {str(e)}")
        return None

@mcp.resource("gtfs://static")
def gtfs_static_resource():
    data = _fetch_feed("gtfs_static", is_static=True)
    return {"status": "success", "data": "Raw ZIP file available (not parsed)", "size": len(data) if data else 0, "lastUpdate": _cache["gtfs_static"]["last_update"]}

@mcp.resource("gtfs://events")
def events_resource():
    return get_open_agenda_events()

@mcp.resource("gtfs://weather")
def weather_resource():
    return get_weather_forecast()

if __name__ == "__main__":
    transport = os.getenv("MCP_TRANSPORT", "sse")  # Par défaut SSE pour compatibilité avec MCP Inspector
    if transport == "tcp":
        print("Info: transport 'tcp' non supporté, utilisation de 'sse' à la place.")
        transport = "sse"
    print(f"Starting MCP server with transport: {transport} on {HOST}:{PORT}")
    mcp.run(transport=transport)