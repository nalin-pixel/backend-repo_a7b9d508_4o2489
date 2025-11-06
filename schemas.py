from pydantic import BaseModel, Field, HttpUrl
from typing import Optional, List

class Employee(BaseModel):
    """
    Employees collection schema
    Collection name: "employee"
    """
    id: str = Field(..., description="Employee ID (unique)")
    name: str = Field(..., description="Full name")
    designation: Optional[str] = Field(None, description="Job title/designation")
    department: Optional[str] = Field(None, description="Department name")
    employee_picture_link: Optional[HttpUrl] = Field(None, description="Public URL to employee picture")

class Attendance(BaseModel):
    """
    Attendance collection schema
    Collection name: "attendance"
    """
    date: str = Field(..., description="Attendance date in YYYY-MM-DD")
    id: str = Field(..., description="Employee ID")
    entryTime: Optional[str] = Field(None, description="Entry time in HH:MM:SS")
    exitTime: Optional[str] = Field(None, description="Exit time in HH:MM:SS")
    workedHours: Optional[str] = Field(None, description="Worked hours formatted as HH:MM")
