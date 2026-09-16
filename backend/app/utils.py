from math import atan2, cos, radians, sin, sqrt

def haversine_km(lat1, lon1, lat2, lon2):
    r = 6371
    p1, p2 = radians(lat1), radians(lat2)
    dp = radians(lat2 - lat1)
    dl = radians(lon2 - lon1)
    a = sin(dp / 2) ** 2 + cos(p1) * cos(p2) * sin(dl / 2) ** 2
    return 2 * r * atan2(sqrt(a), sqrt(1 - a))

def optimize_stops(stops):
    if not stops:
        return []
    remaining = list(stops)
    ordered = [remaining.pop(0)]
    while remaining:
        current = ordered[-1]
        nxt = min(
            remaining,
            key=lambda s: haversine_km(current["latitude"], current["longitude"], s["latitude"], s["longitude"])
        )
        ordered.append(nxt)
        remaining.remove(nxt)
    return ordered
