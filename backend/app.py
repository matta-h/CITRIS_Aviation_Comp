from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI, HTTPException
from backend.routing import NODES, GRAPH, shortest_path

app = FastAPI(title="CITRIS Routing API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # fine for dev
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/nodes")
def get_nodes():
    return NODES

@app.get("/graph")
def get_graph():
    return GRAPH

@app.get("/route")
def get_route(start: str, end: str):
    result = shortest_path(start, end)
    if result is None:
        raise HTTPException(status_code=404, detail="No feasible route found")
    return result