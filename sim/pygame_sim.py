import math
import os
import random
import heapq
import pygame

pygame.init()

WIDTH, HEIGHT = 1400, 850
SCREEN = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("CITRIS 2D Flight Sim - Multi-Leg Routing")

CLOCK = pygame.time.Clock()
FONT = pygame.font.SysFont("arial", 18)
SMALL_FONT = pygame.font.SysFont("arial", 14)

# Colors
BG = (235, 240, 245)
TEXT = (20, 30, 40)
AIRPORT = (20, 140, 90)
UC_COLOR = (180, 60, 60)
PANEL = (255, 255, 255)

GREEN_ROUTE = (30, 180, 90)
YELLOW_ROUTE = (230, 190, 50)
ORANGE_ROUTE = (240, 140, 30)
BLOCKED_ROUTE = (220, 60, 60)

AIRCRAFT_COLORS = [
    (240, 120, 20),
    (70, 130, 255),
    (180, 80, 220),
    (255, 80, 80),
    (255, 180, 60),
]

# -------------------------------------------------
# Map display size
# -------------------------------------------------
MAP_LEFT = 20
MAP_TOP = 60
MAP_WIDTH = 1050
MAP_HEIGHT = 760

# -------------------------------------------------
# Original calibrated map size
# -------------------------------------------------
CALIB_WIDTH = 900
CALIB_HEIGHT = 700

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAP_PATH = os.path.join(BASE_DIR, "assets", "images", "norcal_map.png")

def load_map_image():
    if os.path.exists(MAP_PATH):
        image = pygame.image.load(MAP_PATH).convert()
        image = pygame.transform.smoothscale(image, (MAP_WIDTH, MAP_HEIGHT))
        return image
    return None

MAP_IMAGE = load_map_image()

# -------------------------------------------------
# Nodes in calibrated map coordinates
# -------------------------------------------------
nodes = [
    {"name": "UC Berkeley", "cx": 208, "cy": 257, "type": "uc"},
    {"name": "UC Davis", "cx": 370, "cy": 27, "type": "uc"},
    {"name": "UC Santa Cruz", "cx": 284, "cy": 571, "type": "uc"},
    {"name": "UC Merced", "cx": 764, "cy": 439, "type": "uc"},
    {"name": "KOAR", "cx": 356, "cy": 671, "type": "airport"},
    {"name": "KSNS", "cx": 406, "cy": 670, "type": "airport"},
    {"name": "KCVH", "cx": 474, "cy": 594, "type": "airport"},
    {"name": "KSQL", "cx": 218, "cy": 389, "type": "airport"},
    {"name": "KLVK", "cx": 363, "cy": 321, "type": "airport"},
    {"name": "KNUQ", "cx": 262, "cy": 419, "type": "airport"},
]

node_lookup = {n["name"]: n for n in nodes}

# -------------------------------------------------
# Range assumption
# -------------------------------------------------
MAX_RANGE_MILES = 80.0

# Use one known edge to calibrate map-pixel distance to miles
# Berkeley -> Livermore = 27 mi, from your diagram
def pixel_distance(n1, n2):
    dx = n1["cx"] - n2["cx"]
    dy = n1["cy"] - n2["cy"]
    return math.hypot(dx, dy)

BERKELEY = node_lookup["UC Berkeley"]
LIVERMORE = node_lookup["KLVK"]
PIXELS_PER_27MI = pixel_distance(BERKELEY, LIVERMORE)
MILES_PER_PIXEL = 27.0 / PIXELS_PER_27MI

def miles_between(n1, n2):
    return pixel_distance(n1, n2) * MILES_PER_PIXEL

# -------------------------------------------------
# Manually classified route preferences
# Undirected edges: use tuple(sorted(...))
# -------------------------------------------------
green_edges = {
    tuple(sorted(("UC Santa Cruz", "KOAR"))),
    tuple(sorted(("UC Santa Cruz", "KSNS"))),
    tuple(sorted(("UC Santa Cruz", "KCVH"))),
    tuple(sorted(("KOAR", "KSNS"))),
    tuple(sorted(("KOAR", "KCVH"))),
    tuple(sorted(("KSNS", "KCVH"))),
}

yellow_edges = {
    tuple(sorted(("UC Berkeley", "UC Davis"))),
    tuple(sorted(("UC Berkeley", "KLVK"))),
    tuple(sorted(("UC Davis", "KLVK"))),
    tuple(sorted(("UC Davis", "UC Merced"))),   # too long, will still be blocked by range
    tuple(sorted(("KLVK", "UC Merced"))),
    tuple(sorted(("KLVK", "KCVH"))),
    tuple(sorted(("KCVH", "UC Merced"))),
    tuple(sorted(("UC Berkeley", "KSQL"))),
}

orange_edges = {
    tuple(sorted(("UC Berkeley", "KNUQ"))),
    tuple(sorted(("KSQL", "KNUQ"))),
    tuple(sorted(("KNUQ", "UC Santa Cruz"))),
    tuple(sorted(("KNUQ", "KCVH"))),
    tuple(sorted(("KSQL", "UC Santa Cruz"))),
    tuple(sorted(("KSQL", "KLVK"))),
    tuple(sorted(("KNUQ", "KLVK"))),
}

# -------------------------------------------------
# Coordinate conversion
# -------------------------------------------------
def node_to_screen(node):
    sx = MAP_LEFT + (node["cx"] / CALIB_WIDTH) * MAP_WIDTH
    sy = MAP_TOP + (node["cy"] / CALIB_HEIGHT) * MAP_HEIGHT
    return int(sx), int(sy)

# -------------------------------------------------
# Graph logic
# -------------------------------------------------
def edge_key(name1, name2):
    return tuple(sorted((name1, name2)))

def route_class(name1, name2):
    key = edge_key(name1, name2)
    if key in green_edges:
        return "green"
    if key in yellow_edges:
        return "yellow"
    if key in orange_edges:
        return "orange"
    return None

def route_color(route_type):
    if route_type == "green":
        return GREEN_ROUTE
    if route_type == "yellow":
        return YELLOW_ROUTE
    if route_type == "orange":
        return ORANGE_ROUTE
    return BLOCKED_ROUTE

def route_penalty(route_type):
    if route_type == "green":
        return 1.0
    if route_type == "yellow":
        return 1.2
    if route_type == "orange":
        return 1.5
    return 9999.0

def build_graph():
    graph = {n["name"]: [] for n in nodes}

    for i in range(len(nodes)):
        for j in range(i + 1, len(nodes)):
            n1 = nodes[i]
            n2 = nodes[j]

            rtype = route_class(n1["name"], n2["name"])
            if rtype is None:
                continue

            dist = miles_between(n1, n2)
            if dist > MAX_RANGE_MILES:
                continue

            cost = dist * route_penalty(rtype)

            graph[n1["name"]].append((n2["name"], cost, dist, rtype))
            graph[n2["name"]].append((n1["name"], cost, dist, rtype))

    return graph

graph = build_graph()

def shortest_path(start_name, end_name):
    pq = [(0.0, start_name, [])]
    visited = set()

    while pq:
        total_cost, current, path = heapq.heappop(pq)

        if current in visited:
            continue
        visited.add(current)

        path = path + [current]

        if current == end_name:
            return path

        for neighbor, cost, dist, rtype in graph[current]:
            if neighbor not in visited:
                heapq.heappush(pq, (total_cost + cost, neighbor, path))

    return None

# -------------------------------------------------
# Aircraft state
# -------------------------------------------------
aircraft_list = []
spawn_timer = 0.0
spawn_interval = 4.0
next_aircraft_id = 1

stats = {
    "spawned": 0,
    "completed": 0,
    "rejected": 0,
}

def choose_random_trip():
    return random.sample(nodes, 2)

def spawn_aircraft():
    global next_aircraft_id

    origin, destination = choose_random_trip()
    path_names = shortest_path(origin["name"], destination["name"])

    if not path_names or len(path_names) < 2:
        stats["rejected"] += 1
        return

    route_nodes = [node_lookup[name] for name in path_names]
    start_x, start_y = node_to_screen(route_nodes[0])

    aircraft = {
        "id": next_aircraft_id,
        "x": float(start_x),
        "y": float(start_y),
        "route_nodes": route_nodes,
        "leg_index": 0,
        "speed": random.uniform(70.0, 130.0),   # visual speed, not true mph
        "color": random.choice(AIRCRAFT_COLORS),
        "active": True,
    }

    next_aircraft_id += 1
    aircraft_list.append(aircraft)
    stats["spawned"] += 1

def current_leg_start(aircraft):
    return aircraft["route_nodes"][aircraft["leg_index"]]

def current_leg_end(aircraft):
    return aircraft["route_nodes"][aircraft["leg_index"] + 1]

def advance_leg(aircraft):
    aircraft["leg_index"] += 1
    if aircraft["leg_index"] >= len(aircraft["route_nodes"]) - 1:
        aircraft["active"] = False
        stats["completed"] += 1

def update_aircraft(dt):
    for aircraft in aircraft_list:
        if not aircraft["active"]:
            continue

        target_node = current_leg_end(aircraft)
        tx, ty = node_to_screen(target_node)

        dx = tx - aircraft["x"]
        dy = ty - aircraft["y"]
        distance = math.hypot(dx, dy)

        if distance < 2.0:
            aircraft["x"] = tx
            aircraft["y"] = ty
            advance_leg(aircraft)
            continue

        direction_x = dx / distance
        direction_y = dy / distance

        aircraft["x"] += direction_x * aircraft["speed"] * dt
        aircraft["y"] += direction_y * aircraft["speed"] * dt

    aircraft_list[:] = [a for a in aircraft_list if a["active"]]

# -------------------------------------------------
# Drawing
# -------------------------------------------------
def draw_background():
    map_rect = pygame.Rect(MAP_LEFT, MAP_TOP, MAP_WIDTH, MAP_HEIGHT)
    pygame.draw.rect(SCREEN, (220, 225, 230), map_rect)

    if MAP_IMAGE is not None:
        SCREEN.blit(MAP_IMAGE, map_rect.topleft)
    else:
        pygame.draw.rect(SCREEN, (235, 235, 235), map_rect)
        msg = SMALL_FONT.render("No map image found: assets/images/norcal_map.png", True, TEXT)
        SCREEN.blit(msg, (MAP_LEFT + 20, MAP_TOP + 20))

    pygame.draw.rect(SCREEN, TEXT, map_rect, 2)

def draw_title():
    title = FONT.render("CITRIS 2D Flight Sim - Multi-Leg Routing", True, TEXT)
    SCREEN.blit(title, (20, 20))

def draw_nodes():
    for node in nodes:
        x, y = node_to_screen(node)
        color = UC_COLOR if node["type"] == "uc" else AIRPORT

        pygame.draw.circle(SCREEN, color, (x, y), 8)
        pygame.draw.circle(SCREEN, TEXT, (x, y), 8, 1)

        label = SMALL_FONT.render(node["name"], True, TEXT)
        SCREEN.blit(label, (x + 10, y - 10))

def draw_network_edges():
    drawn = set()
    for n1_name, neighbors in graph.items():
        for n2_name, cost, dist, rtype in neighbors:
            key = edge_key(n1_name, n2_name)
            if key in drawn:
                continue
            drawn.add(key)

            n1 = node_lookup[n1_name]
            n2 = node_lookup[n2_name]
            x1, y1 = node_to_screen(n1)
            x2, y2 = node_to_screen(n2)

            pygame.draw.line(SCREEN, route_color(rtype), (x1, y1), (x2, y2), 3)

def draw_aircraft_routes():
    for aircraft in aircraft_list:
        route_nodes = aircraft["route_nodes"]
        for i in range(len(route_nodes) - 1):
            n1 = route_nodes[i]
            n2 = route_nodes[i + 1]
            rtype = route_class(n1["name"], n2["name"])
            x1, y1 = node_to_screen(n1)
            x2, y2 = node_to_screen(n2)
            pygame.draw.line(SCREEN, route_color(rtype), (x1, y1), (x2, y2), 2)

def draw_aircraft():
    for aircraft in aircraft_list:
        x = int(aircraft["x"])
        y = int(aircraft["y"])
        pygame.draw.circle(SCREEN, aircraft["color"], (x, y), 6)
        pygame.draw.circle(SCREEN, TEXT, (x, y), 6, 1)

def draw_side_panel():
    panel_rect = pygame.Rect(1100, 60, 270, 760)
    pygame.draw.rect(SCREEN, PANEL, panel_rect)
    pygame.draw.rect(SCREEN, TEXT, panel_rect, 2)

    y = 85
    lines = [
        "Scenario",
        "Range-constrained routing",
        "",
        f"Max range: {MAX_RANGE_MILES:.0f} mi",
        f"Spawn interval: {spawn_interval:.1f} s",
        "",
        f"Active aircraft: {len(aircraft_list)}",
        f"Spawned total: {stats['spawned']}",
        f"Completed total: {stats['completed']}",
        f"Rejected trips: {stats['rejected']}",
        "",
        "Edge types:",
        "Green = preferred",
        "Yellow = acceptable",
        "Orange = less preferred",
        "",
        "Controls:",
        "SPACE -> spawn flight",
        "UP/DOWN -> spawn timing",
        "C -> clear aircraft",
    ]

    for line in lines:
        label = SMALL_FONT.render(line, True, TEXT)
        SCREEN.blit(label, (1115, y))
        y += 24

    y += 10
    label = SMALL_FONT.render("Live routes:", True, TEXT)
    SCREEN.blit(label, (1115, y))
    y += 24

    preview_count = min(8, len(aircraft_list))
    for i in range(preview_count):
        aircraft = aircraft_list[i]
        names = [n["name"] for n in aircraft["route_nodes"]]
        text = f"{aircraft['id']}: " + " -> ".join(names)
        label = SMALL_FONT.render(text[:34], True, aircraft["color"])
        SCREEN.blit(label, (1115, y))
        y += 22

def draw_footer():
    footer = SMALL_FONT.render(
        "Flights now use multi-leg routing based on range-limited colored network edges.",
        True,
        TEXT,
    )
    SCREEN.blit(footer, (20, 825))

# -------------------------------------------------
# Seed initial traffic
# -------------------------------------------------
for _ in range(4):
    spawn_aircraft()

# -------------------------------------------------
# Main loop
# -------------------------------------------------
running = True
while running:
    dt = CLOCK.tick(60) / 1000.0
    spawn_timer += dt

    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_SPACE:
                spawn_aircraft()
            elif event.key == pygame.K_UP:
                spawn_interval = max(1.0, spawn_interval - 0.5)
            elif event.key == pygame.K_DOWN:
                spawn_interval = min(10.0, spawn_interval + 0.5)
            elif event.key == pygame.K_c:
                aircraft_list.clear()

    if spawn_timer >= spawn_interval:
        spawn_aircraft()
        spawn_timer = 0.0

    update_aircraft(dt)

    SCREEN.fill(BG)
    draw_title()
    draw_background()
    draw_network_edges()
    draw_aircraft_routes()
    draw_nodes()
    draw_aircraft()
    draw_side_panel()
    draw_footer()

    pygame.display.flip()

pygame.quit()