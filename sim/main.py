import math
import pygame

# -----------------------------
# Basic setup
# -----------------------------
pygame.init()

WIDTH, HEIGHT = 1200, 800
SCREEN = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("CITRIS 2D Flight Sim - Starter")

CLOCK = pygame.time.Clock()
FONT = pygame.font.SysFont("arial", 18)

# Colors
BG = (235, 240, 245)
GRID = (210, 215, 220)
TEXT = (20, 30, 40)
NODE = (30, 100, 200)
AIRPORT = (20, 140, 90)
UC_COLOR = (180, 60, 60)
AIRCRAFT = (240, 120, 20)
ROUTE = (100, 100, 100)

# -----------------------------
# Simple node data
# Screen coordinates for now
# (not true map projection yet)
# -----------------------------
nodes = [
    {"name": "UC Berkeley", "x": 180, "y": 180, "type": "uc"},
    {"name": "UC Davis", "x": 320, "y": 160, "type": "uc"},
    {"name": "UC Santa Cruz", "x": 120, "y": 320, "type": "uc"},
    {"name": "UC Merced", "x": 420, "y": 420, "type": "uc"},
    {"name": "KOAR", "x": 140, "y": 360, "type": "airport"},
    {"name": "KSNS", "x": 170, "y": 420, "type": "airport"},
    {"name": "KCVH", "x": 270, "y": 440, "type": "airport"},
    {"name": "KSQL", "x": 175, "y": 225, "type": "airport"},
    {"name": "KLVK", "x": 240, "y": 250, "type": "airport"},
]

# Aircraft starts at Berkeley, goes to Merced
start_node = nodes[0]
end_node = nodes[3]

aircraft = {
    "x": float(start_node["x"]),
    "y": float(start_node["y"]),
    "speed": 100.0,  # pixels per second
    "origin": start_node,
    "destination": end_node,
    "active": True,
}

# -----------------------------
# Helper functions
# -----------------------------
def draw_grid():
    for x in range(0, WIDTH, 50):
        pygame.draw.line(SCREEN, GRID, (x, 0), (x, HEIGHT), 1)
    for y in range(0, HEIGHT, 50):
        pygame.draw.line(SCREEN, GRID, (0, y), (WIDTH, y), 1)

def draw_title():
    title = FONT.render("CITRIS 2D Flight Sim - Starter Version", True, TEXT)
    SCREEN.blit(title, (20, 20))

def draw_nodes():
    for node in nodes:
        color = UC_COLOR if node["type"] == "uc" else AIRPORT
        pygame.draw.circle(SCREEN, color, (node["x"], node["y"]), 8)

        label = FONT.render(node["name"], True, TEXT)
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

    label = FONT.render("Aircraft", True, TEXT)
    SCREEN.blit(label, (x + 10, y - 10))

def draw_status():
    status_text = (
        f"Route: {aircraft['origin']['name']} -> {aircraft['destination']['name']} | "
        f"Active: {aircraft['active']}"
    )
    label = FONT.render(status_text, True, TEXT)
    SCREEN.blit(label, (20, HEIGHT - 40))

# -----------------------------
# Main loop
# -----------------------------
running = True
while running:
    dt = CLOCK.tick(60) / 1000.0  # seconds

    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

    update_aircraft(dt)

    SCREEN.fill(BG)
    draw_grid()
    draw_title()
    draw_route()
    draw_nodes()
    draw_aircraft()
    draw_status()

    pygame.display.flip()

pygame.quit()