import os
from datetime import datetime
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict

from database import db, create_document, get_documents

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------------
# Models for request bodies
# -----------------------------
class RFIDEvent(BaseModel):
    id: str  # employee id
    scanner_id: str  # scanner1 (entry) or scanner2 (exit)
    timestamp: datetime  # ISO timestamp from RFID scanner

# -----------------------------
# Helper utilities
# -----------------------------

def to_date_str(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d")

def to_time_str(dt: datetime) -> str:
    return dt.strftime("%H:%M:%S")

def compute_worked_hours(entry: Optional[str], exit: Optional[str]) -> Optional[str]:
    if not entry or not exit:
        return None
    try:
        e_dt = datetime.strptime(entry, "%H:%M:%S")
        x_dt = datetime.strptime(exit, "%H:%M:%S")
        # Handle overnight not required for factory typical shift, assume same day
        delta = x_dt - e_dt
        total_seconds = int(delta.total_seconds())
        if total_seconds < 0:
            return None
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        return f"{hours:02d}:{minutes:02d}"
    except Exception:
        return None

# -----------------------------
# API Routes
# -----------------------------
@app.get("/")
def read_root():
    return {"message": "Factory Attendance API running"}

@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }

    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
            response["database_name"] = "✅ Set" if os.getenv("DATABASE_NAME") else "❌ Not Set"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
                response["connection_status"] = "Connected"
            except Exception as e:
                response["database"] = f"⚠️ Connected but Error: {str(e)[:80]}"
        else:
            response["database"] = "⚠️ Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:80]}"

    return response

@app.post("/api/rfid")
def ingest_rfid(event: RFIDEvent):
    """
    Ingest a JSON event coming from RFID scanners.
    - scanner1 means entry gate
    - scanner2 means exit gate
    Creates or updates an attendance record for that employee and date.
    """
    if db is None:
        raise HTTPException(status_code=500, detail="Database not available")

    # Fetch employee to ensure exists and get name
    emp = db["employee"].find_one({"id": event.id})
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")

    date_str = to_date_str(event.timestamp)
    time_str = to_time_str(event.timestamp)

    # Find existing attendance for the date
    att = db["attendance"].find_one({"id": event.id, "date": date_str})

    entry_time = att.get("entryTime") if att else None
    exit_time = att.get("exitTime") if att else None

    if event.scanner_id == "scanner1":
        entry_time = time_str
    elif event.scanner_id == "scanner2":
        exit_time = time_str
    else:
        raise HTTPException(status_code=400, detail="Unknown scanner_id")

    worked = compute_worked_hours(entry_time, exit_time)

    payload = {
        "date": date_str,
        "id": event.id,
        "name": emp.get("name"),
        "entryTime": entry_time,
        "exitTime": exit_time,
        "workedHours": worked,
    }

    if att:
        db["attendance"].update_one({"_id": att["_id"]}, {"$set": payload})
    else:
        create_document("attendance", payload)

    return {"status": "ok", "data": payload}

@app.get("/api/attendance")
def get_attendance(date: Optional[str] = None, department: Optional[str] = None):
    """
    List attendance records joined with employee static info.
    If date is not provided, use today's date (server time).
    """
    if db is None:
        raise HTTPException(status_code=500, detail="Database not available")

    if not date:
        date = datetime.now().strftime("%Y-%m-%d")

    # Get attendance for that date
    records = list(db["attendance"].find({"date": date}))

    # Join with employee info
    result = []
    for r in records:
        emp = db["employee"].find_one({"id": r.get("id")})
        if not emp:
            continue
        if department and emp.get("department") != department:
            continue
        result.append({
            "date": r.get("date"),
            "id": r.get("id"),
            "name": r.get("name") or emp.get("name"),
            "designation": emp.get("designation"),
            "department": emp.get("department"),
            "employee_picture": emp.get("employee_picture_link"),
            "entryTime": r.get("entryTime"),
            "exitTime": r.get("exitTime"),
            "workedHours": r.get("workedHours"),
        })

    # Sort by name for predictability
    result.sort(key=lambda x: x.get("name") or "")

    return {"date": date, "records": result}

@app.get("/api/employees")
def get_employees():
    if db is None:
        raise HTTPException(status_code=500, detail="Database not available")
    emps = list(db["employee"].find({}, {"_id": 0}))
    return {"count": len(emps), "employees": emps}

@app.post("/api/employees/seed")
def seed_employees(employees: List[Dict]):
    """
    Seed static employee table once. Idempotent insert by id.
    """
    if db is None:
        raise HTTPException(status_code=500, detail="Database not available")

    inserted = 0
    for e in employees:
        existing = db["employee"].find_one({"id": e.get("id")})
        if existing:
            # update to keep static info fresh
            db["employee"].update_one({"_id": existing["_id"]}, {"$set": e})
        else:
            create_document("employee", e)
            inserted += 1
    return {"status": "ok", "inserted": inserted}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
