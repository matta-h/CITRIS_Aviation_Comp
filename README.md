# ✈️ Merced Airlink Nexus — eVTOL Routing & Simulation System

A simulation and routing platform for **Advanced Air Mobility (AAM)**, designed for the **CITRIS Aviation Prize**. This project models a **VTOL air taxi network** connecting Northern California UC campuses and regional airports, with a focus on **safety, routing, weather integration, and operational feasibility**.

---

## 📌 Overview

Merced Airlink Nexus is a modular system that combines:

- 🌍 Interactive map-based routing (React + Leaflet)
- ⚙️ Backend simulation engine (FastAPI)
- 🌦️ Weather-aware route optimization
- 🚧 Hazard-aware path planning (no-fly + slow zones)
- 🛫 Multi-leg routing with real-world constraints

The goal is to simulate how **eVTOL aircraft (e.g., Joby S4)** could operate in a **taxi-like service across Northern California**.

---

## 🧠 Project Context

This project was developed as part of the **CITRIS Aviation Prize**, focusing on:

- Vertiport siting across UC campuses
- Routing strategies under real-world constraints
- Safety, weather, and emergency modeling
- Scalable simulation architecture  

Phase 2 emphasizes moving from **concept → implementation**, including routing logic, simulator integration, and safety systems.

---

## 🗺️ Features

### ✅ Routing Engine
- Graph-based shortest path routing (Dijkstra-style)
- Multi-leg routing for distances > ~85 miles
- Stop penalties and airport-based transfers

### 🌦️ Weather Integration
- Real-time weather via API (e.g., Open-Meteo)
- Node classification: `Good / Caution / Unsafe`
- Weather penalties applied to routing decisions

### 🚧 Hazard System
- **Hard hazards** → no-fly zones (detours generated)
- **Soft hazards** → slow zones (cost penalties)
- Dynamic rerouting around hazards

### 🛫 Simulation Capabilities (In Progress)
- Demand modeling based on population/activity
- Aircraft state machine (idle → takeoff → enroute → landing)
- Emergency/diversion logic
- Timeline-based simulation playback  

---

## 🏗️ System Architecture

Frontend (React + Leaflet)
        ↓
FastAPI Backend (Routing + Simulation Engine)
        ↓
Data Adapters
   ├── Weather API
   ├── Airspace Data (planned: ForeFlight)
   ├── Traffic Data (planned)

---

## ⚙️ Tech Stack

**Frontend**
- React
- Leaflet / React-Leaflet

**Backend**
- FastAPI (Python)
- Uvicorn

**APIs / Data Sources**
- Weather API (Open-Meteo)
- Planned: ForeFlight (airspace)
- Planned: LandScan (population density)
- Planned: Aviationstack / flight tracking

---

## 🚀 Getting Started

### 1. Clone Repository
```bash
git clone https://github.com/your-username/CITRIS_Aviation_Comp.git
cd CITRIS_Aviation_Comp
```

### 2. Backend Setup
```bash
cd backend
pip install -r requirements.txt
python -m uvicorn app:app --reload
```

Backend runs at:
http://127.0.0.1:8000

### 3. Frontend Setup
```bash
cd frontend
npm install
npm start
```

Frontend runs at:
http://localhost:3000

---

## 🧪 Simulation Roadmap

1. Time Model  
2. Data Adapters  
3. Decision Engine  
4. Metrics  
5. UI Integration  

---

## ✈️ Flight Model (Concept)

Idle → Task Validation → Takeoff → Enroute → Hazard Handling / Reroute / Divert → Landing → Unload → Charge → Idle

---

## 📊 Constraints & Assumptions

- Max direct flight distance ≈ 85 miles
- Longer trips require intermediate stops
- Vertiports at UC campuses and regional airports
- Weather and hazards dynamically affect routing

---

## 🛠️ Future Work

- ForeFlight API integration
- Terrain & obstacle data
- Economic modeling
- Autonomous behavior
- Sense-and-avoid simulation
- Performance optimization
- UI improvements

---

## ⚠️ Known Limitations

- Routing latency
- Limited real-time traffic
- Simplified flight dynamics
- Incomplete emergency modeling

---

## 🤝 Contributors

- Matthew Huynh  
- Alexander Jones  
- Anthony Luna  
- Oliver Htway  
- Sachin Giri  
- Nadiya Rowshan  

Advisor: Dr. Francesco Danzi  

---

## 📄 License

Academic/research use under CITRIS Aviation Prize.

---

## 💡 Vision

A scalable simulation platform bridging:

Concept → Real-world AAM implementation
