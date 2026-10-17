"""Yousty apprenticeship availability API. Start the application with: python run.py

Adapted from the course starter (Student-API-Basic) to our Yousty data model:
Company, Occupation, Location and ApprenticeshipPosition.

The file is organised in three layers:
  1. Data access     - read and save the JSON files in data/
  2. Application logic - checks and rules (does the ID exist? is the status valid?)
  3. Interface       - the HTTP routes that FastAPI shows in /docs
"""

import json
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(
    title="Yousty Apprenticeship API",
    description="Manage the availability of apprenticeship positions for 2027.",
)

# Locate the data folder beside this Python file, even from another working directory.
DATA_DIR = Path(__file__).resolve().parent / "data"

# The only two values our model allows for availability_status.
AvailabilityStatus = Literal["Available", "Not available"]


# ---------------------------------------------------------------------------
# 1. Data access layer: read and save JSON records
# ---------------------------------------------------------------------------

def load_records(file_name: str) -> list[dict]:
    # json.load converts the JSON array into a Python list of dictionaries.
    with (DATA_DIR / file_name).open(encoding="utf-8") as file:
        return json.load(file)


def save_records(file_name: str, records: list[dict]) -> None:
    # json.dump writes the Python list back into the JSON file.
    with (DATA_DIR / file_name).open("w", encoding="utf-8") as file:
        json.dump(records, file, indent=2, ensure_ascii=False)
        file.write("\n")


# ---------------------------------------------------------------------------
# 2. Application logic: find records and check the rules of our model
# ---------------------------------------------------------------------------

def find_record(records: list[dict], id_field: str, record_id: str) -> dict | None:
    # Check each record; return the first one whose ID matches.
    for record in records:
        if record[id_field] == record_id:
            return record
    return None


def get_or_404(file_name: str, id_field: str, record_id: str, label: str) -> dict:
    record = find_record(load_records(file_name), id_field, record_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"{label} not found")
    return record


def check_references(position: dict) -> None:
    # Our model: each apprenticeship position belongs to exactly ONE existing
    # company, occupation and location. JSON does not enforce this, so we check it.
    references = [
        ("companies.json", "company_id", "Company"),
        ("occupations.json", "occupation_id", "Occupation"),
        ("locations.json", "location_id", "Location"),
    ]
    for file_name, id_field, label in references:
        if find_record(load_records(file_name), id_field, position[id_field]) is None:
            raise HTTPException(
                status_code=422,
                detail=f"{label} {position[id_field]} does not exist",
            )


def next_apprenticeship_id(positions: list[dict]) -> str:
    # IDs follow the pattern A01, A02, ... The new ID is the highest number + 1.
    numbers = [int(p["apprenticeship_id"][1:]) for p in positions]
    return f"A{max(numbers, default=0) + 1:02d}"


# Input formats for the write operations. FastAPI checks the request body
# against these before our function runs (wrong type or status -> 422).
class PositionInput(BaseModel):
    occupation_id: str
    company_id: str
    location_id: str
    availability_year: int = 2027
    availability_status: AvailabilityStatus = "Available"


class AvailabilityInput(BaseModel):
    availability_status: AvailabilityStatus


# ---------------------------------------------------------------------------
# 3. Interface layer: HTTP routes
# ---------------------------------------------------------------------------

@app.get("/")
def root():
    return {"message": "Welcome to the Yousty Apprenticeship API!", "documentation": "/docs"}


# --- Reference data: read all / read one ----------------------------------

@app.get("/companies", tags=["Companies"])
def list_companies():
    return load_records("companies.json")


@app.get("/companies/{company_id}", tags=["Companies"])
def get_company(company_id: str):
    return get_or_404("companies.json", "company_id", company_id, "Company")


@app.get("/occupations", tags=["Occupations"])
def list_occupations():
    return load_records("occupations.json")


@app.get("/occupations/{occupation_id}", tags=["Occupations"])
def get_occupation(occupation_id: str):
    return get_or_404("occupations.json", "occupation_id", occupation_id, "Occupation")


@app.get("/locations", tags=["Locations"])
def list_locations():
    return load_records("locations.json")


@app.get("/locations/{location_id}", tags=["Locations"])
def get_location(location_id: str):
    return get_or_404("locations.json", "location_id", location_id, "Location")


# --- Apprenticeship positions: full CRUD ------------------------------------

POSITIONS_FILE = "apprenticeship_positions.json"


# READ all - use case "Search Apprenticeships" with optional filters
# ("Filter by Availability", "Starting Year", occupation, location, company).
@app.get("/apprenticeship-positions", tags=["Apprenticeship positions"])
def list_positions(
    availability_status: AvailabilityStatus | None = None,
    availability_year: int | None = None,
    occupation_id: str | None = None,
    location_id: str | None = None,
    company_id: str | None = None,
):
    filters = {
        "availability_status": availability_status,
        "availability_year": availability_year,
        "occupation_id": occupation_id,
        "location_id": location_id,
        "company_id": company_id,
    }
    positions = load_records(POSITIONS_FILE)
    # Keep a position only if it matches every filter that was given.
    return [
        p for p in positions
        if all(value is None or p[field] == value for field, value in filters.items())
    ]


# READ one - use case "View Vacancy Details" / "View Availability Information"
@app.get("/apprenticeship-positions/{apprenticeship_id}", tags=["Apprenticeship positions"])
def get_position(apprenticeship_id: str):
    return get_or_404(POSITIONS_FILE, "apprenticeship_id", apprenticeship_id,
                      "Apprenticeship position")


# CREATE - use case "Manage Apprenticeship Vacancy" (company adds a position)
@app.post("/apprenticeship-positions", status_code=201, tags=["Apprenticeship positions"])
def create_position(new_position: PositionInput):
    position = new_position.model_dump()
    check_references(position)

    positions = load_records(POSITIONS_FILE)
    # Rule: the same company may not list the same occupation at the same
    # location for the same year twice.
    for p in positions:
        if all(p[f] == position[f] for f in
               ("company_id", "occupation_id", "location_id", "availability_year")):
            raise HTTPException(
                status_code=409,
                detail=f"This position already exists as {p['apprenticeship_id']}",
            )

    record = {"apprenticeship_id": next_apprenticeship_id(positions), **position}
    positions.append(record)
    save_records(POSITIONS_FILE, positions)
    return record


# UPDATE - use case "Update Availability" (company marks a position as filled/open)
@app.patch("/apprenticeship-positions/{apprenticeship_id}/availability",
           tags=["Apprenticeship positions"])
def update_availability(apprenticeship_id: str, change: AvailabilityInput):
    positions = load_records(POSITIONS_FILE)
    position = find_record(positions, "apprenticeship_id", apprenticeship_id)
    if position is None:
        raise HTTPException(status_code=404, detail="Apprenticeship position not found")

    # position points to the dictionary inside the list, so changing it
    # changes the list we save.
    position["availability_status"] = change.availability_status
    save_records(POSITIONS_FILE, positions)
    return position


# DELETE - company removes a position it no longer offers
@app.delete("/apprenticeship-positions/{apprenticeship_id}", tags=["Apprenticeship positions"])
def delete_position(apprenticeship_id: str):
    positions = load_records(POSITIONS_FILE)
    position = find_record(positions, "apprenticeship_id", apprenticeship_id)
    if position is None:
        raise HTTPException(status_code=404, detail="Apprenticeship position not found")

    positions.remove(position)
    save_records(POSITIONS_FILE, positions)
    return {"deleted": apprenticeship_id}
