import math
import os
import pygame

pygame.init()

WIDTH, HEIGHT = 1200, 800
SCREEN = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("CITRIS 2D Flight Sim - NorCal Map")

CLOCK = pygame.time.Clock()
FONT = pygame.font.SysFont("arial", 18)
SMALL_FONT = pygame.font.SysFont("arial", 14)

# Colors
BG = (235, 240, 245)
GRID = (210, 215, 220)
TEXT = (20, 30, 40)
AIRPORT = (20, 140, 90)
UC_COLOR = (180, 60, 60)
AIRCRAFT = (240, 120, 20)
ROUTE = (90, 90, 90)
PANEL = (255, 255, 255)

# Window padding for map area
MAP_LEFT = 20
MAP_TOP = 60
MAP_WIDTH = 900
MAP_HEIGHT = 700

# Background image path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAP_PATH = os.path.join(BASE_DIR, "assets", "images", "norcal_map.png")

def load_map_image():
    if os.path.exists(MAP_PATH):
        image = pygame.image.load(MAP_PATH).convert()
        image = pygame.transform.smoothscale(image, (MAP_WIDTH, MAP_HEIGHT))
        return image
    return None

MAP_IMAGE = load_map_image()

# Screen coordinates placed on the map rectangle
nodes = [
    {"name": "UC Berkeley", "x": 230, "y": 170, "type": "uc"},
    {"name": "UC Davis", "x": 355, "y": 150, "type": "uc"},
    {"name": "UC Santa Cruz", "x": 165, "y": 325, "type": "uc"},
    {"name": "UC Merced", "x": 455, "y": 430, "type": "uc"},
    {"name": "KOAR", "x": 185, "y": 360, "type": "airport"},
    {"name": "KSNS", "x": 215, "y": 425, "type": "airport"},
    {"name": "KCVH", "x": 305, "y": 450, "type": "airport"},
    {"name": "KSQL", "x": 220, "y": 215, "type": "airport"},
    {"name": "KLVK", "x": 285, "y": 245, "type": "airport"},
]

start_node = nodes[0]
end_node = nodes[3]

aircraft = {
    "x": float(start_node["x"]),
    "y": float(start_node["y"]),
    "speed": 100.0,
    "origin": start_node,
    "destination": end_node,
    "active": True,
}

def draw_grid():
    for x in range(MAP_LEFT, MAP_LEFT + MAP_WIDTH, 50):
        pygame.draw.line(SCREEN, GRID, (x, MAP_TOP), (x, MAP_TOP + MAP_HEIGHT), 1)
    for y in range(MAP_TOP, MAP_TOP + MAP_HEIGHT, 50):
        pygame.draw.line(SCREEN, GRID, (MAP_LEFT, y), (MAP_LEFT + MAP_WIDTH, y), 1)

def draw_background():
    map_rect = pygame.Rect(MAP_LEFT, MAP_TOP, MAP_WIDTH, MAP_HEIGHT)
    pygame.draw.rect(SCREEN, (220, 225, 230), map_rect)

    if MAP_IMAGE is not None:
        SCREEN.blit(MAP_IMAGE, map_rect.topleft)
    else:
        draw_grid()
        missing = SMALL_FONT.render("No map image found: assets/images/norcal_map.png", True, TEXT)
        SCREEN.blit(missing, (MAP_LEFT + 20, MAP_TOP + 20))

    pygame.draw.rect(SCREEN, TEXT, map_rect, 2)

def draw_title():
    title = FONT.render("CITRIS 2D Flight Sim - NorCal Operations View", True, TEXT)
    SCREEN.blit(title, (20, 20))

def draw_nodes():
    for node in nodes:
        color = UC_COLOR if node["type"] == "uc" else AIRPORT
        pygame.draw.circle(SCREEN, color, (node["x"], node["y"]), 8)
        pygame.draw.circle(SCREEN, TEXT, (node["x"], node["y"]), 8, 1)

        label = SMALL_FONT.render(node["name"], True, TEXT)
        SCREEN.blit(label, (node["x"] + 10, node["y"] - 10))

def draw_route():
    pygame.draw.line(
        SCREEN,
        ROUTE,
        (aircraft["origin"]["x"], aircraft["origin"]["y"]),
        (aircraft["destination"]["x"], aircraft["destination"]["y"]),
        2,
    )

def update_aircraft(dt):
    if not aircraft["active"]:
        return

    dx = aircraft["destination"]["x"] - aircraft["x"]
    dy = aircraft["destination"]["y"] - aircraft["y"]
    distance = math.hypot(dx, dy)

    if distance < 1.0:
        aircraft["x"] = aircraft["destination"]["x"]
        aircraft["y"] = aircraft["destination"]["y"]
        aircraft["active"] = False
        return

    direction_x = dx / distance
    direction_y = dy / distance

    aircraft["x"] += direction_x * aircraft["speed"] * dt
    aircraft["y"] += direction_y * aircraft["speed"] * dt

def draw_aircraft():
    x = int(aircraft["x"])
    y = int(aircraft["y"])
    pygame.draw.circle(SCREEN, AIRCRAFT, (x, y), 6)
    pygame.draw.circle(SCREEN, TEXT, (x, y), 6, 1)

    label = SMALL_FONT.render("Aircraft", True, TEXT)
    SCREEN.blit(label, (x + 10, y - 10))

def draw_side_panel():
    panel_rect = pygame.Rect(950, 60, 230, 700)
    pygame.draw.rect(SCREEN, PANEL, panel_rect)
    pygame.draw.rect(SCREEN, TEXT, panel_rect, 2)

    y = 80
    lines = [
        "Scenario",
        "Berkeley -> Merced",
        "",
        f"Aircraft active: {aircraft['active']}",
        f"Speed: {aircraft['speed']:.1f}",
        "",
        "Nodes:",
        "4 UC campuses",
        "5 airports",
        "",
        "Next upgrades:",
        "- multiple aircraft",
        "- weather logic",
        "- demand generation",
        "- route blocking",
    ]

    for line in lines:
        label = SMALL_FONT.render(line, True, TEXT)
        SCREEN.blit(label, (965, y))
        y += 24

def draw_status():
    status = f"{aircraft['origin']['name']} -> {aircraft['destination']['name']}"
    label = SMALL_FONT.render(status, True, TEXT)
    SCREEN.blit(label, (20, 770))

running = True
while running:
    dt = CLOCK.tick(60) / 1000.0

    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

    update_aircraft(dt)

    SCREEN.fill(BG)
    draw_title()
    draw_background()
    draw_route()
    draw_nodes()
    draw_aircraft()
    draw_side_panel()
    draw_status()

    pygame.display.flip()

pygame.quit()