"""Draw each surveyed segment on the OpenStreetMap street network.

For segment "Street from A to B", find the street's ways, the nodes where it meets A and B, and the shortest path
along the street between them. Where a name matches several crossings (divided roads, streets that cross twice),
pick the pair whose path length is closest to the length printed on the survey sheet. "City Limit" endpoints are
street nodes near the city boundary. Writes data/segments_geo.json; segments that need a manual look are flagged.
"""
import heapq, itertools, json, math, pathlib, re

ROOT = pathlib.Path(__file__).resolve().parent.parent
GEO = ROOT / "data/sources/geo"

ABBR = {"st": "street", "ave": "avenue", "blvd": "boulevard", "bivd": "boulevard", "dr": "drive", "rd": "road",
        "pl": "place", "wy": "way", "pkwy": "parkway", "ln": "lane", "ct": "court", "hwy": "highway"}
DIRS = {"n": "north", "s": "south", "e": "east", "w": "west"}
# survey names that OSM spells differently
ALIAS = {"parrot drive": "parrott drive", "los prados street": "los prados", "csm drive": "college of san mateo drive",
         "coyote pointe drive": "coyote point drive", "s el camino real": "el camino real"}


def norm(name):
    words = re.sub(r"[^a-z0-9 ]", " ", name.lower()).split()
    words = [ABBR.get(w, w) if i == len(words) - 1 else w for i, w in enumerate(words)]
    words = [DIRS.get(w, w) if i == 0 and len(words) > 1 else w for i, w in enumerate(words)]
    s = " ".join(words)
    return ALIAS.get(s, s)


def core(name):
    return re.sub(r"^(north|south|east|west) ", "", norm(name))


def hav(a, b):
    lon1, lat1, lon2, lat2 = map(math.radians, (*a, *b))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 3958.8 * 2 * math.asin(math.sqrt(h))  # miles


osm = json.load(open(GEO / "osm_streets.json"))
NODE = {e["id"]: (e["lon"], e["lat"]) for e in osm["elements"] if e["type"] == "node"}
WAYS = [e for e in osm["elements"] if e["type"] == "way" and "name" in e.get("tags", {})]
BY_CORE = {}
for w in WAYS:
    BY_CORE.setdefault(core(w["tags"]["name"]), []).append(w)

_mw = json.load(open(GEO / "osm_motorways.json"))
RAMPS = [pt for e in _mw["elements"] if e["type"] == "way" and e.get("tags", {}).get("highway", "").endswith("_link")
         for pt in ([(g["lon"], g["lat"]) for g in e.get("geometry", [])])]

city = json.load(open(GEO / "san_mateo_city.geojson"))
geom = city["features"][0]["geometry"] if "features" in city else city.get("geometry", city)
rings = geom["coordinates"] if geom["type"] == "Polygon" else [r for poly in geom["coordinates"] for r in poly]
BOUNDARY = [pt for ring in rings for pt in ring]


def ways_for(name):
    out = []
    for part in name.split("/"):
        m = re.match(r"([NSEW])-([NSEW]) (.+)", part.strip())  # "N-S Bayshore Blvd" = North and South Bayshore
        for p in ([f"{m.group(1)} {m.group(3)}", f"{m.group(2)} {m.group(3)}"] if m else [part]):
            out += BY_CORE.get(core(p), [])
    return out


def graph(ways, bridge=0.03):
    g = {}
    for w in ways:
        for a, b in zip(w["nodes"], w["nodes"][1:]):
            if a in NODE and b in NODE:
                d = hav(NODE[a], NODE[b])
                g.setdefault(a, {})[b] = d
                g.setdefault(b, {})[a] = d
    # OSM sometimes splits a street where a crossing or plaza interrupts it; bridge gaps under ~50 m
    comp, cid = {}, 0
    for n in g:
        if n in comp: continue
        stack = [n]; comp[n] = cid
        while stack:
            u = stack.pop()
            for v in g[u]:
                if v not in comp: comp[v] = cid; stack.append(v)
        cid += 1
    if cid > 1:
        nodes = list(g)
        for a, b in itertools.combinations(nodes, 2):
            if comp[a] != comp[b]:
                d = hav(NODE[a], NODE[b])
                if d < bridge:
                    g[a][b] = g[b][a] = d
    return g


def dijkstra(g, src):
    dist, prev, pq = {src: 0.0}, {}, [(0.0, src)]
    while pq:
        d, u = heapq.heappop(pq)
        if d > dist[u]: continue
        for v, w in g[u].items():
            if d + w < dist.get(v, 1e9):
                dist[v], prev[v] = d + w, u
                heapq.heappush(pq, (d + w, v))
    return dist, prev


def endpoints(street_nodes, cross):
    c = cross.lower()
    if "city limit" in c:
        near = [n for n in street_nodes if min(hav(NODE[n], b) for b in BOUNDARY[::3]) < 0.06]
        return near + [n for n in street_nodes if len(G_CUR[n]) == 1], "city limit"  # or where the street ends
    m = re.match(r"(west|north|south|east) of (.+)", c)
    if m: cross = m.group(2)
    if "off-ramp" in c:
        near = [n for n in street_nodes if any(hav(NODE[n], r) < 0.02 for r in RAMPS)]
        return (near or None), "ramp"
    if "wkwy" in c or "trail" in c or "crossing" in c:
        return None, "unnamed"
    nodes = {n for w in ways_for(cross) for n in w["nodes"]}
    hit = [n for n in street_nodes if n in nodes]
    return hit, "intersection"


G_WIDE = {}


def locate(seg):
    sways = ways_for(seg["street"])
    if not sways: return {"status": "no street"}
    global G_CUR
    g = G_CUR = graph(sways, bridge=0.2 if seg.get("_retry") else 0.03)
    sn = set(g)
    a, ka = endpoints(sn, seg["from"])
    b, kb = endpoints(sn, seg["to"])
    target = seg["length_mi"] or 0
    if not a and not b: return {"status": f"no endpoints ({ka}/{kb})"}
    best = None
    # if one end is unnamed, try every street node for it and let the length decide
    a = a or list(sn); b = b or list(sn)
    for s in a[:40]:
        dist, prev = dijkstra(g, s)
        for t in b:
            if t in dist and t != s:
                err = abs(dist[t] - target)
                if best is None or err < best[0]: best = (err, s, t, dist[t], prev)
    if not best:
        if not seg.get("_retry"):  # OSM splits some downtown blocks; bridge wider gaps along the same street
            G_WIDE[seg["segment_no"]] = True
            return locate(dict(seg, _retry=True))
        return {"status": "no path"}
    err, s, t, d, prev = best
    path = [t]
    while path[-1] != s: path.append(prev[path[-1]])
    coords = [[round(NODE[n][0], 6), round(NODE[n][1], 6)] for n in reversed(path)]
    ok = target and abs(d - target) <= max(0.06, 0.2 * target) and ka != "unnamed" and kb != "unnamed"
    # an unnamed end (walkway, trail, ramp) located by length alone is fine if the length matches closely
    if not ok and target and abs(d - target) <= max(0.03, 0.05 * target): ok = "approx"
    return {"status": "ok" if ok is True else ("approx" if ok else "check"), "path_mi": round(d, 3), "survey_mi": target,
            "ends": [ka, kb], "coords": coords}


if __name__ == "__main__":
    segs = json.load(open(ROOT / "data/ets_2026_segments.json"))
    out = {}
    for s in segs:
        out[s["segment_no"]] = r = locate(s)
        if r["status"] not in ("ok", "approx"):
            print(s["segment_no"], s["street"], "|", s["from"], "->", s["to"], "|", r["status"], r.get("path_mi"), "vs", r.get("survey_mi"))
    json.dump(out, open(ROOT / "data/segments_geo.json", "w"))
    print(sum(v["status"] == "ok" for v in out.values()), "ok,", sum(v["status"] == "approx" for v in out.values()),
          "approx (one end placed by survey length), of", len(out))
