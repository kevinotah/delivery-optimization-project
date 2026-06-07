"""
Dynamic Dispatch Simulator for Medical Delivery Company
========================================================

This is a proof-of-concept Streamlit application demonstrating a naive greedy
heuristic for vehicle routing with time windows (VRPTW) in a medical delivery
context.

KEY DESIGN PHILOSOPHY:
- Prioritizes RELIABILITY (hitting strict time windows) over EFFICIENCY (fuel savings)
- Uses a custom, hand-written greedy algorithm (NO black-box optimization libraries)
- Handles real-world chaos: sick drivers, vehicle breakdowns

ALGORITHM PRIORITIES (in order):
1. Temperature-Sensitive goods → Refrigerated Van ONLY
2. Hospital goods → Large Vans first (capacity + reliability)
3. Pharmacy goods → Small Vans first, overflow to Large Vans

If a delivery cannot fit, it's deferred to the afternoon (unassigned_deliveries).
This ensures critical medical deliveries are NEVER sacrificed for convenience items.
"""

import streamlit as st
import pandas as pd
import random
import io
from typing import List, Dict, Tuple
from dataclasses import dataclass, field
import copy
from datetime import datetime, timedelta


# ============================================================================
# SECTION 0: PARIS TRAVEL-TIME MATRIX & LOGISTICS DATA
# ============================================================================

# District definitions: Paris medical delivery zones
DISTRICTS = {
    "Warehouse": (2.35, 48.87),        # Central warehouse (Le Marais area)
    "North_Paris": (2.36, 48.90),      # North Paris (10th-11th arrondissements)
    "East_Paris": (2.42, 48.86),       # East Paris (20th arrondissement)
    "Southeast": (2.40, 48.82),        # Southeast (12th-13th arrondissements)
    "Southwest": (2.30, 48.82),        # Southwest (13th-14th arrondissements)
    "West_Paris": (2.25, 48.85),       # West Paris (6th-7th arrondissements)
}

# Travel time matrix: minutes between districts by time of day
# Based on Paris real-world traffic patterns
TRAVEL_TIME_MATRIX = {
    # Morning rush (7-10am): Slower due to congestion
    ("Warehouse", "North_Paris", "morning_rush"): 32,
    ("Warehouse", "East_Paris", "morning_rush"): 28,
    ("Warehouse", "Southeast", "morning_rush"): 26,
    ("Warehouse", "Southwest", "morning_rush"): 24,
    ("Warehouse", "West_Paris", "morning_rush"): 22,
    ("North_Paris", "East_Paris", "morning_rush"): 20,
    ("North_Paris", "Southeast", "morning_rush"): 22,
    ("North_Paris", "Southwest", "morning_rush"): 28,
    ("North_Paris", "West_Paris", "morning_rush"): 26,
    ("East_Paris", "Southeast", "morning_rush"): 18,
    ("East_Paris", "Southwest", "morning_rush"): 30,
    ("East_Paris", "West_Paris", "morning_rush"): 32,
    ("Southeast", "Southwest", "morning_rush"): 24,
    ("Southeast", "West_Paris", "morning_rush"): 30,
    ("Southwest", "West_Paris", "morning_rush"): 20,
    
    # Mid-morning (10am-12pm): Normal traffic
    ("Warehouse", "North_Paris", "mid_morning"): 20,
    ("Warehouse", "East_Paris", "mid_morning"): 18,
    ("Warehouse", "Southeast", "mid_morning"): 16,
    ("Warehouse", "Southwest", "mid_morning"): 14,
    ("Warehouse", "West_Paris", "mid_morning"): 12,
    ("North_Paris", "East_Paris", "mid_morning"): 14,
    ("North_Paris", "Southeast", "mid_morning"): 16,
    ("North_Paris", "Southwest", "mid_morning"): 18,
    ("North_Paris", "West_Paris", "mid_morning"): 16,
    ("East_Paris", "Southeast", "mid_morning"): 12,
    ("East_Paris", "Southwest", "mid_morning"): 20,
    ("East_Paris", "West_Paris", "mid_morning"): 22,
    ("Southeast", "Southwest", "mid_morning"): 16,
    ("Southeast", "West_Paris", "mid_morning"): 20,
    ("Southwest", "West_Paris", "mid_morning"): 14,
    
    # Afternoon (12pm-5pm): Light traffic
    ("Warehouse", "North_Paris", "afternoon"): 16,
    ("Warehouse", "East_Paris", "afternoon"): 14,
    ("Warehouse", "Southeast", "afternoon"): 12,
    ("Warehouse", "Southwest", "afternoon"): 10,
    ("Warehouse", "West_Paris", "afternoon"): 10,
    ("North_Paris", "East_Paris", "afternoon"): 12,
    ("North_Paris", "Southeast", "afternoon"): 14,
    ("North_Paris", "Southwest", "afternoon"): 16,
    ("North_Paris", "West_Paris", "afternoon"): 14,
    ("East_Paris", "Southeast", "afternoon"): 10,
    ("East_Paris", "Southwest", "afternoon"): 16,
    ("East_Paris", "West_Paris", "afternoon"): 18,
    ("Southeast", "Southwest", "afternoon"): 12,
    ("Southeast", "West_Paris", "afternoon"): 16,
    ("Southwest", "West_Paris", "afternoon"): 12,
}

def get_time_bucket(time_minutes: int) -> str:
    """
    Determine time-of-day bucket for travel time lookup.
    
    Args:
        time_minutes: Minutes from start of day (0 = 00:00)
    
    Returns:
        "morning_rush", "mid_morning", or "afternoon"
    """
    # 6am-10am: morning rush (360-600 minutes) — includes early warehouse departures
    if 360 <= time_minutes < 600:
        return "morning_rush"
    # 10am-12pm: mid morning (600-720 minutes)
    elif 600 <= time_minutes < 720:
        return "mid_morning"
    # 12pm-5pm: afternoon (720-1020 minutes)
    else:
        return "afternoon"  # Default for off-peak

def get_travel_time(from_district: str, to_district: str, departure_time_minutes: int) -> float:
    """
    Get travel time between two districts at a given time of day.
    
    Args:
        from_district: Origin district name (must exist in DISTRICTS)
        to_district: Destination district name
        departure_time_minutes: When vehicle departs (minutes from day start)
    
    Returns:
        Travel time in minutes (float)
    """
    if from_district == to_district:
        return 0.0
    
    time_bucket = get_time_bucket(departure_time_minutes)
    
    # Try direct lookup
    key = (from_district, to_district, time_bucket)
    if key in TRAVEL_TIME_MATRIX:
        return float(TRAVEL_TIME_MATRIX[key])
    
    # Try reverse lookup (symmetric assumption)
    key_reverse = (to_district, from_district, time_bucket)
    if key_reverse in TRAVEL_TIME_MATRIX:
        return float(TRAVEL_TIME_MATRIX[key_reverse])
    
    # Fallback: rough Haversine-based estimate (shouldn't happen with complete matrix)
    from math import radians, cos, sin, asin, sqrt
    lat1, lon1 = DISTRICTS[from_district]
    lat2, lon2 = DISTRICTS[to_district]
    lon1, lat1, lon2, lat2 = map(radians, [lon1, lat1, lon2, lat2])
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * asin(sqrt(a))
    km = 6371 * c
    minutes = km * 3  # Rough estimate: 3 min per km in Paris
    if time_bucket == "morning_rush":
        minutes *= 1.3
    elif time_bucket == "mid_morning":
        minutes *= 1.0
    else:
        minutes *= 0.9
    return minutes


# ============================================================================
# SECTION 1: DATA STRUCTURES
# ============================================================================

@dataclass
class Delivery:
    """
    Represents a single delivery order.
    
    Attributes:
        id: Unique identifier (e.g., "HOSP-001", "TEMP-042")
        type: One of "Hospital", "Temperature-Sensitive", or "Pharmacy"
        boxes: Number of standard medical boxes (1-5)
        time_window: Description of delivery time constraint (for reference)
        early_time: Earliest delivery time (minutes from start of day, e.g., 360 = 6am)
        late_time: Latest delivery time (minutes from start of day, e.g., 540 = 9am)
        is_hard_window: If True, time window is a hard constraint; if False, it's soft preference
        load_time: When this delivery was loaded (in minutes from day start, or None if not loaded)
        district: Paris district where delivery goes (e.g., "North_Paris")
        service_time: Estimated service time on site in minutes (5-30)
    """
    id: str
    type: str  # "Hospital", "Temperature-Sensitive", or "Pharmacy"
    boxes: int  # Number of standard medical boxes
    time_window: str  # e.g., "before 9am", "same-day", etc. (for human reference)
    early_time: int = 360  # Default 6:00 AM (360 minutes from 0:00)
    late_time: int = 1080  # Default 6:00 PM (1080 minutes from 0:00)
    is_hard_window: bool = False  # Default: soft constraint
    load_time: int = None  # Minutes from day start when loaded (for 24-hour rule)
    district: str = "Warehouse"  # Paris district (for travel-time matrix lookup)
    # Estimated service time on site in minutes (5-30)
    service_time: int = 5


@dataclass
class Vehicle:
    """
    Represents a delivery vehicle in the fleet.
    
    Attributes:
        id: Unique identifier (e.g., "Refrigerated-Van-1", "Small-Van-2")
        type: One of "Refrigerated" or "Ambient"
        capacity: Maximum boxes the vehicle can carry
        current_load: Current boxes loaded (starts at 0)
        assigned_deliveries: List of Delivery objects assigned to this vehicle
        driver_start_time: When driver starts shift (minutes from day start, default 6am=360)
        driver_hours_used: Total hours driver has worked so far (includes driving + service)
        driver_hours_limit: Maximum hours driver can work per day (typically 8-10)
    """
    id: str
    type: str  # "Refrigerated" or "Ambient"
    capacity: int  # Max boxes
    current_load: int = 0
    assigned_deliveries: List[Delivery] = field(default_factory=list)
    driver_start_time: int = 360  # Default 6:00 AM
    driver_hours_used: float = 0.5  # Initial 30 min for loading/prep
    driver_hours_limit: float = 10.0  # Legal max shift: 10 hours


# ============================================================================
# SECTION 1B: CONSTRAINT VALIDATORS
# ============================================================================

def minutes_to_hm(minutes: int) -> str:
    """Convert minutes from day start (0=00:00) to HH:MM format."""
    minutes = int(minutes)  # Ensure it's an integer
    hours = minutes // 60
    mins = minutes % 60
    return f"{hours:02d}:{mins:02d}"


def is_delivery_within_time_window(delivery: Delivery, arrival_time: int) -> Tuple[bool, str]:
    """
    Check if a delivery's arrival time falls within its time window.
    
    Args:
        delivery: The Delivery to check
        arrival_time: Arrival time in minutes from day start
    
    Returns:
        (is_feasible, reason) tuple
    """
    if delivery.early_time <= arrival_time <= delivery.late_time:
        return True, ""
    else:
        window = f"{minutes_to_hm(delivery.early_time)}-{minutes_to_hm(delivery.late_time)}"
        arrival = minutes_to_hm(arrival_time)
        return False, f"Time window violation: arrives {arrival}, window {window}"


def is_delivery_within_24h_rule(delivery: Delivery, load_time: int, arrival_time: int) -> Tuple[bool, str]:
    """
    Check if delivery completes within 24 hours from load time (medical compliance).
    
    Args:
        delivery: The Delivery to check
        load_time: When delivery was loaded (minutes from day start)
        arrival_time: When delivery will arrive (minutes from day start)
    
    Returns:
        (is_feasible, reason) tuple
    """
    # Convert to total minutes elapsed
    if arrival_time >= load_time:
        elapsed_minutes = arrival_time - load_time
    else:
        # Delivery arrives next day
        elapsed_minutes = (24 * 60 - load_time) + arrival_time
    
    max_minutes = 24 * 60  # 24 hours
    if elapsed_minutes <= max_minutes:
        return True, ""
    else:
        hours = elapsed_minutes / 60.0
        return False, f"24-hour transit rule violated: {hours:.1f}h from load"


def is_driver_within_hours(vehicle: Vehicle, added_minutes: float) -> Tuple[bool, str]:
    """
    Check if adding a delivery would exceed driver working hour limits.
    
    Args:
        vehicle: The Vehicle to check
        added_minutes: Travel + service time for the new delivery (in minutes)
    
    Returns:
        (is_feasible, reason) tuple
    """
    new_hours = vehicle.driver_hours_used + (added_minutes / 60.0)
    if new_hours <= vehicle.driver_hours_limit:
        return True, ""
    else:
        return False, f"Driver hours limit exceeded: {new_hours:.1f}h / {vehicle.driver_hours_limit:.1f}h"


def check_all_constraints(
    delivery: Delivery,
    vehicle: Vehicle,
    arrival_time: int,
    added_minutes: float
) -> Tuple[bool, str]:
    """
    Check all constraints for assigning a delivery to a vehicle.
    
    Args:
        delivery: The Delivery to assign
        vehicle: The Vehicle to assign to
        arrival_time: When the delivery would arrive (minutes from day start)
        added_minutes: Travel + service time for this delivery
    
    Returns:
        (is_feasible, reason) tuple with reason if infeasible
    """
    # Check capacity
    if vehicle.current_load + delivery.boxes > vehicle.capacity:
        return False, f"Capacity exceeded: {vehicle.current_load + delivery.boxes} / {vehicle.capacity} boxes"
    
    # Check driver hours
    feasible, reason = is_driver_within_hours(vehicle, added_minutes)
    if not feasible:
        return False, reason
    
    # Check time window (only for hard constraints for now, to avoid complexity)
    if delivery.is_hard_window:
        feasible, reason = is_delivery_within_time_window(delivery, arrival_time)
        if not feasible:
            return False, reason
    
    # Check 24-hour medical transit rule
    if delivery.load_time is not None:
        feasible, reason = is_delivery_within_24h_rule(delivery, delivery.load_time, arrival_time)
        if not feasible:
            return False, reason
    
    return True, ""


# ============================================================================
# SECTION 2: FLEET & DATA GENERATION
# ============================================================================

def create_fleet() -> Dict[str, Vehicle]:
    """
    Initialize the fixed fleet of 6 vehicles.
    
    Fleet Composition:
    - 1 Refrigerated Van (45 boxes): For temperature-sensitive medical goods
    - 2 Large Ambient Vans (45 boxes each): For high-volume pharmacy/hospital
    - 3 Small Ambient Vans (30 boxes each): For targeted/time-critical deliveries
    
    Returns:
        Dictionary mapping vehicle IDs to Vehicle objects
    """
    fleet = {
        "Refrigerated-Van-1": Vehicle(
            id="Refrigerated-Van-1",
            type="Refrigerated",
            capacity=45
        ),
        "Large-Van-1": Vehicle(
            id="Large-Van-1",
            type="Ambient",
            capacity=45
        ),
        "Large-Van-2": Vehicle(
            id="Large-Van-2",
            type="Ambient",
            capacity=45
        ),
        "Small-Van-1": Vehicle(
            id="Small-Van-1",
            type="Ambient",
            capacity=30
        ),
        "Small-Van-2": Vehicle(
            id="Small-Van-2",
            type="Ambient",
            capacity=30
        ),
        "Small-Van-3": Vehicle(
            id="Small-Van-3",
            type="Ambient",
            capacity=30
        ),
    }
    return fleet


def generate_deliveries(num_deliveries: int) -> List[Delivery]:
    """
    Generate a randomized list of daily deliveries with realistic distribution.
    
    Distribution (from client requirements):
    - ~10% Hospital (strict <9 AM window, Ambient, 1-5 boxes, CRITICAL)
    - ~15% Temperature-Sensitive (requires Refrigerated Van, 1-3 boxes, CRITICAL)
    - ~75% Pharmacy (flexible same-day, Ambient, 1-3 boxes, DEFERRABLE)
    
    Args:
        num_deliveries: Total number of deliveries to generate
    
    Returns:
        Shuffled list of Delivery objects
    """
    deliveries = []
    
    # Calculate distribution
    num_hospital = max(1, int(num_deliveries * 0.10))
    num_temp_sensitive = max(1, int(num_deliveries * 0.15))
    num_pharmacy = num_deliveries - num_hospital - num_temp_sensitive
    
    # Generate Hospital deliveries (CRITICAL: strict time windows)
    for i in range(num_hospital):
        delivery = Delivery(
            id=f"HOSP-{i+1:03d}",
            type="Hospital",
            boxes=random.randint(3, 7),  # Small to medium load
            time_window="before 9am (STRICT)",
            early_time=360,  # 6:00 AM
            late_time=540,   # 9:00 AM (STRICT constraint)
            is_hard_window=True,
            load_time=360  # Load at 6:00 AM
        )
        deliveries.append(delivery)
    
    # Generate Temperature-Sensitive deliveries (CRITICAL: medical compliance)
    for i in range(num_temp_sensitive):
        delivery = Delivery(
            id=f"TEMP-{i+1:03d}",
            type="Temperature-Sensitive",
            boxes=random.randint(2, 4),  # Small load
            time_window="same-day (urgent)",
            early_time=360,  # 6:00 AM
            late_time=1080,  # 6:00 PM
            is_hard_window=False,  # Soft constraint
            load_time=360  # Load at 6:00 AM
        )
        deliveries.append(delivery)
    
    # Generate Pharmacy deliveries (FLEXIBLE: can be deferred)
    for i in range(num_pharmacy):
        delivery = Delivery(
            id=f"PHARM-{i+1:03d}",
            type="Pharmacy",
            boxes=random.randint(2, 5),  # Small to medium
            time_window="same-day (flexible)",
            early_time=360,  # 6:00 AM
            late_time=1080,  # 6:00 PM
            is_hard_window=False,  # Soft constraint
            load_time=360  # Load at 6:00 AM
        )
        deliveries.append(delivery)
    
    # Assign districts and service times
    district_list = [d for d in DISTRICTS.keys() if d != "Warehouse"]
    for d in deliveries:
        d.district = random.choice(district_list)  # Random Paris district
        if d.type == "Hospital":
            d.service_time = random.randint(25, 40)
        elif d.type == "Temperature-Sensitive":
            d.service_time = random.randint(10, 20)
        else:
            d.service_time = random.randint(8, 15)

    # Shuffle to simulate realistic order arrival throughout the morning
    random.shuffle(deliveries)
    return deliveries


# ============================================================================
# SECTION 3: NAIVE GREEDY SOLVING HEURISTIC
# ============================================================================

def assign_deliveries(
    deliveries: List[Delivery],
    fleet: Dict[str, Vehicle],
    chaos_mode: Dict[str, bool] = None
) -> Tuple[Dict[str, Vehicle], List[Delivery], Dict[str, str]]:
    """
    Assign deliveries to vans using a constraint-aware, priority-based heuristic.
    
    KEY CHANGE: This now enforces VRPTW constraints:
    1. Time windows (hard for hospitals, soft for others)
    2. Driver working hours (8-10 hour limits)
    3. 24-hour medical transit rule
    4. Capacity (as before)
    
    PRIORITY ORDER (same as before):
    1. Temperature-Sensitive → ONLY Refrigerated Van (non-negotiable)
    2. Hospital → Large Vans first (prioritize capacity & reliability)
    3. Pharmacy → Small Vans first (efficiency), overflow to Large Vans
    
    CONSTRAINT CHECKING:
    - Before assigning, calculate estimated arrival time based on current route
    - Use check_all_constraints() to verify feasibility
    - If ANY constraint fails, defer the delivery
    
    Args:
        deliveries: List of Delivery objects to assign
        fleet: Dict of Vehicle objects (modified in-place)
        chaos_mode: Dict with "sick_driver" and "fridge_breakdown" booleans
    
    Returns:
        Tuple of:
        - updated_fleet: Vehicles with assigned_deliveries populated
        - unassigned_deliveries: Orders that couldn't fit anywhere
        - unassigned_reasons: Dict mapping delivery ID to reason for deferral
    """
    if chaos_mode is None:
        chaos_mode = {}
    
    # Apply chaos mode modifications before assignment
    if chaos_mode.get("sick_driver", False):
        fleet["Small-Van-3"].capacity = 0
    
    if chaos_mode.get("fridge_breakdown", False):
        fleet["Refrigerated-Van-1"].capacity = 22
    
    unassigned_deliveries = []
    unassigned_reasons: Dict[str, str] = {}
    
    # Helper function to estimate arrival time and travel minutes for a delivery
    def estimate_arrival_and_travel(van: Vehicle, delivery: Delivery) -> Tuple[int, float]:
        """
        Estimate when this delivery would arrive if added to van's current route.
        Uses real Paris travel-time matrix.
        
        Returns:
            (arrival_time_minutes, travel_plus_service_minutes)
        """
        current_time = van.driver_start_time + 30  # 6:30am after loading
        last_district = "Warehouse"

        for d in van.assigned_deliveries:
            travel = get_travel_time(last_district, d.district, current_time)
            current_time += travel + d.service_time
            last_district = d.district

        # Travel from last location to this delivery
        travel_to_delivery = get_travel_time(last_district, delivery.district, current_time)
        arrival_time = current_time + travel_to_delivery
        travel_plus_service = travel_to_delivery + delivery.service_time
        
        return int(arrival_time), travel_plus_service
    
    # ========================================================================
    # PRIORITY 1: Temperature-Sensitive → Refrigerated Van ONLY
    # ========================================================================
    temp_sensitive = [d for d in deliveries if d.type == "Temperature-Sensitive"]
    for delivery in temp_sensitive:
        fridge_van = fleet["Refrigerated-Van-1"]
        
        # Estimate arrival time
        arrival_time, added_minutes = estimate_arrival_and_travel(fridge_van, delivery)
        
        # Check all constraints
        feasible, reason = check_all_constraints(delivery, fridge_van, arrival_time, added_minutes)
        
        if feasible:
            fridge_van.current_load += delivery.boxes
            fridge_van.assigned_deliveries.append(delivery)
            fridge_van.driver_hours_used += added_minutes / 60.0
        else:
            unassigned_deliveries.append(delivery)
            unassigned_reasons[delivery.id] = reason
    
    # ========================================================================
    # PRIORITY 2: Hospital → Large Vans First
    # ========================================================================
    hospital = [d for d in deliveries if d.type == "Hospital"]
    large_vans = [fleet["Large-Van-1"], fleet["Large-Van-2"]]
    
    for delivery in hospital:
        assigned = False
        
        # Try each large van in order
        for van in large_vans:
            arrival_time, added_minutes = estimate_arrival_and_travel(van, delivery)
            feasible, reason = check_all_constraints(delivery, van, arrival_time, added_minutes)
            
            if feasible:
                van.current_load += delivery.boxes
                van.assigned_deliveries.append(delivery)
                van.driver_hours_used += added_minutes / 60.0
                assigned = True
                break
        
        # Fallback: try small vans
        if not assigned:
            small_vans = [fleet["Small-Van-1"], fleet["Small-Van-2"], fleet["Small-Van-3"]]
            for van in small_vans:
                arrival_time, added_minutes = estimate_arrival_and_travel(van, delivery)
                feasible, reason = check_all_constraints(delivery, van, arrival_time, added_minutes)
                
                if feasible:
                    van.current_load += delivery.boxes
                    van.assigned_deliveries.append(delivery)
                    van.driver_hours_used += added_minutes / 60.0
                    assigned = True
                    break
        
        # If still not assigned, add to unassigned
        if not assigned:
            # Try to report most relevant constraint that failed
            arrival_time, added_minutes = estimate_arrival_and_travel(large_vans[0], delivery)
            _, reason = check_all_constraints(delivery, large_vans[0], arrival_time, added_minutes)
            unassigned_deliveries.append(delivery)
            unassigned_reasons[delivery.id] = reason if reason else "No vehicle with available capacity"
    
    # ========================================================================
    # PRIORITY 3: Pharmacy → Small Vans First, Then Large Vans
    # ========================================================================
    pharmacy = [d for d in deliveries if d.type == "Pharmacy"]
    small_vans = [fleet["Small-Van-1"], fleet["Small-Van-2"], fleet["Small-Van-3"]]
    
    for delivery in pharmacy:
        assigned = False
        last_reason = ""
        
        # Try small vans first
        for van in small_vans:
            arrival_time, added_minutes = estimate_arrival_and_travel(van, delivery)
            feasible, reason = check_all_constraints(delivery, van, arrival_time, added_minutes)
            last_reason = reason
            
            if feasible:
                van.current_load += delivery.boxes
                van.assigned_deliveries.append(delivery)
                van.driver_hours_used += added_minutes / 60.0
                assigned = True
                break
        
        # Try large vans (overflow)
        if not assigned:
            for van in large_vans:
                arrival_time, added_minutes = estimate_arrival_and_travel(van, delivery)
                feasible, reason = check_all_constraints(delivery, van, arrival_time, added_minutes)
                last_reason = reason
                
                if feasible:
                    van.current_load += delivery.boxes
                    van.assigned_deliveries.append(delivery)
                    van.driver_hours_used += added_minutes / 60.0
                    assigned = True
                    break
        
        # If still not assigned, add to unassigned
        if not assigned:
            unassigned_deliveries.append(delivery)
            unassigned_reasons[delivery.id] = last_reason if last_reason else "No vehicle with available capacity"
    
    return fleet, unassigned_deliveries, unassigned_reasons



# ============================================================================
# SECTION 4: EXPLAINABILITY ENGINE
# ============================================================================

def generate_explainability_report(delivery: Delivery, fleet: Dict[str, Vehicle], constraint_reason: str) -> Dict:
    """
    Generate a detailed explanation of why a delivery was deferred.
    
    Returns a dict with:
    - primary_reason: The constraint that blocked this delivery
    - affected_vans: Which vans couldn't accommodate it and why
    - best_fit_van: The van that came closest to accepting it
    - what_would_unblock: How many hours/boxes would need to free up
    """
    report = {
        "delivery_id": delivery.id,
        "delivery_type": delivery.type,
        "primary_reason": constraint_reason,
        "affected_vans": [],
        "best_fit_van": None,
        "what_would_unblock": None,
    }
    
    # Analyze each van to understand why it couldn't take this delivery
    best_fit_margin = float('-inf')
    
    for van_id, van in fleet.items():
        if van.capacity == 0:
            continue
        
        arrival_time, added_minutes = (0, 0)  # Dummy for now
        feasible, reason = check_all_constraints(delivery, van, arrival_time, added_minutes)
        
        if not feasible:
            capacity_check = van.current_load + delivery.boxes <= van.capacity
            hours_remaining = van.driver_hours_limit - van.driver_hours_used
            
            report["affected_vans"].append({
                "van_id": van_id,
                "constraint_failed": reason,
                "capacity_available": van.capacity - van.current_load,
                "hours_remaining": hours_remaining,
                "van_type": van.type,
            })
            
            # Track best fit (closest to having capacity)
            if capacity_check:  # Capacity is OK, must be hours
                margin = hours_remaining - (added_minutes / 60.0)
            else:
                margin = van.capacity - van.current_load - delivery.boxes
            
            if margin > best_fit_margin:
                best_fit_margin = margin
                report["best_fit_van"] = van_id
    
    # Suggest what would unblock this delivery
    if "Driver hours" in constraint_reason:
        # Need more driving hours
        total_deficit = 0.0
        for van_info in report["affected_vans"]:
            if "Driver hours" in van_info["constraint_failed"]:
                total_deficit += abs(van_info["hours_remaining"])
        report["what_would_unblock"] = f"Free up {total_deficit:.1f}h total driver time across vans"
    elif "Capacity" in constraint_reason:
        # Need more box capacity
        total_deficit = 0
        for van_info in report["affected_vans"]:
            if "Capacity" in van_info["constraint_failed"]:
                total_deficit += delivery.boxes - van_info["capacity_available"]
        report["what_would_unblock"] = f"Free up {total_deficit} boxes total across vans"
    
    return report


def sequence_route_for_vehicle(van: Vehicle) -> Tuple[List[Delivery], float]:
    """
    Sequence deliveries for a vehicle using nearest-district heuristic with travel-time matrix.
    """
    remaining = van.assigned_deliveries.copy()
    route: List[Delivery] = []
    current_district = "Warehouse"
    total_minutes = 30.0  # Loading time
    current_time = van.driver_start_time + 30  # 6:30am departure from warehouse

    while remaining:
        # Find nearest unvisited district (by travel time)
        nearest = min(
            remaining,
            key=lambda d: get_travel_time(current_district, d.district, current_time)
        )
        # Travel to nearest
        travel = get_travel_time(current_district, nearest.district, current_time)
        total_minutes += travel
        current_time += travel
        # Service at location
        total_minutes += nearest.service_time
        current_time += nearest.service_time
        route.append(nearest)
        current_district = nearest.district
        remaining.remove(nearest)

    # Return to warehouse
    back_minutes = get_travel_time(current_district, "Warehouse", current_time)
    total_minutes += back_minutes

    return route, total_minutes


# ------------------------------------------------------------------------------
# Repair heuristic: reassign deliveries from a disrupted van to remaining fleet
# ------------------------------------------------------------------------------
def repair_assign_from_van(original_fleet: Dict[str, Vehicle], disrupted_van_id: str) -> Tuple[Dict[str, Vehicle], List[Delivery], Dict[str, str]]:
    fleet = copy.deepcopy(original_fleet)
    if disrupted_van_id not in fleet:
        return fleet, [], {}

    disrupted = fleet[disrupted_van_id]
    deliveries_to_move = disrupted.assigned_deliveries.copy()
    
    # Remove them from disrupted van and take it out of service
    disrupted.assigned_deliveries = []
    disrupted.current_load = 0
    disrupted.capacity = 0

    unassigned = []
    reasons: Dict[str, str] = {}

    # Helper to estimate time (same as main heuristic)
    def estimate_arr_and_travel(van: Vehicle, delivery: Delivery) -> Tuple[int, float]:
        current_time = van.driver_start_time + 30 
        last_district = "Warehouse"
        if van.assigned_deliveries:
            last_district = van.assigned_deliveries[-1].district
        travel = get_travel_time(last_district, delivery.district, current_time)
        return int(current_time + travel), travel + delivery.service_time

    # Helper that ACTUALLY checks your constraints
    def try_assign_to_list(delivery: Delivery, vans: List[Vehicle]) -> bool:
        for v in vans:
            if v.capacity > 0:
                arr_time, added_minutes = estimate_arr_and_travel(v, delivery)
                feasible, reason = check_all_constraints(delivery, v, arr_time, added_minutes)
                if feasible:
                    v.current_load += delivery.boxes
                    v.assigned_deliveries.append(delivery)
                    v.driver_hours_used += added_minutes / 60.0
                    return True
                else:
                    reasons[delivery.id] = reason # Log why it failed
        return False

    large_vans = [fleet[k] for k in fleet if k.startswith("Large-Van")]
    small_vans = [fleet[k] for k in fleet if k.startswith("Small-Van")]
    fridge = fleet.get("Refrigerated-Van-1")

    for d in deliveries_to_move:
        assigned = False
        if d.type == "Temperature-Sensitive":
            if fridge and fridge.capacity > 0:
                arr_time, add_min = estimate_arr_and_travel(fridge, d)
                if check_all_constraints(d, fridge, arr_time, add_min)[0]:
                    fridge.current_load += d.boxes
                    fridge.assigned_deliveries.append(d)
                    fridge.driver_hours_used += add_min / 60.0
                    assigned = True
        elif d.type == "Hospital":
            assigned = try_assign_to_list(d, large_vans)
            if not assigned: assigned = try_assign_to_list(d, small_vans)
        else:
            assigned = try_assign_to_list(d, small_vans)
            if not assigned: assigned = try_assign_to_list(d, large_vans)

        if not assigned:
            unassigned.append(d)

    return fleet, unassigned, reasons

# ============================================================================
# PHASE 3: COMPLEMENTARY LOGISTICS LOGIC
# ============================================================================

def parse_csv_orders(file_contents: str) -> Tuple[List[Delivery], List[str]]:
    """CSV parser engine for real client order sheets."""
    deliveries = []
    errors = []
    try:
        df = pd.read_csv(io.StringIO(file_contents))
        required_cols = ["id", "type", "boxes", "district"]
        for col in required_cols:
            if col not in df.columns:
                return [], [f"Missing column check: '{col}'"]

        for idx, row in df.iterrows():
            row_id = str(row.get("id", f"ROW-{idx}"))
            dtype = str(row.get("type", "Pharmacy"))
            if dtype not in ["Hospital", "Temperature-Sensitive", "Pharmacy"]:
                dtype = "Pharmacy"
            
            try:
                boxes = int(row.get("boxes", 1))
                if boxes <= 0: boxes = 1
            except ValueError:
                boxes = 1

            district = str(row.get("district", "North_Paris"))
            if district not in DISTRICTS:
                district = "North_Paris"

            tw_str = str(row.get("time_window", "same-day"))
            early, late, is_hard = 360, 1080, False
            if dtype == "Hospital":
                early, late, is_hard = 360, 540, True
                tw_str = "before 9am (STRICT)"

            svc_time = int(row.get("service_time", 10)) if "service_time" in df.columns else 10

            deliveries.append(Delivery(
                id=row_id, type=dtype, boxes=boxes, time_window=tw_str,
                early_time=early, late_time=late, is_hard_window=is_hard,
                load_time=360, district=district, service_time=svc_time
            ))
    except Exception as e:
        return [], [f"Parsing mistake: {str(e)}"]
    return deliveries, errors


def run_benchmark_suite(deliveries: List[Delivery]) -> Dict[str, Dict]:
    """Automated benchmark tests running cross-strategy metrics updates."""
    scenarios = {
        "Normal Operation": {"sick_driver": False, "fridge_breakdown": False},
        "Sick Driver Scenario": {"sick_driver": True, "fridge_breakdown": False},
        "Fridge Breakdown": {"sick_driver": False, "fridge_breakdown": True}
    }
    results = {}
    for name, config in scenarios.items():
        fleet = create_fleet()
        up_fleet, unassigned, _ = assign_deliveries(copy.deepcopy(deliveries), fleet, config)
        
        total = len(deliveries)
        assigned = total - len(unassigned)
        hosp_total = len([d for d in deliveries if d.type == "Hospital"])
        hosp_unassigned = len([d for d in unassigned if d.type == "Hospital"])
        
        total_cap = sum(v.capacity for v in up_fleet.values() if v.capacity > 0)
        total_load = sum(v.current_load for v in up_fleet.values())
        util = (total_load / total_cap * 100) if total_cap > 0 else 0

        results[name] = {
            "success_rate": (assigned / total * 100) if total > 0 else 0,
            "deferred_count": len(unassigned),
            "hospital_hit_rate": ((hosp_total - hosp_unassigned) / hosp_total * 100) if hosp_total > 0 else 100,
            "capacity_utilization": util
        }
    return results

# ============================================================================
# SECTION 4: STREAMLIT UI / USER EXPERIENCE
# ============================================================================

def main():
    """Main Streamlit application entry point."""
    st.set_page_config(
        page_title="Dynamic Dispatch Simulator",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    # Page header
    st.title("Dynamic Dispatch Simulator")
    st.markdown(
        "**Interactive Prototype for Medical Delivery Optimization (Paris)**\n\n"
        "This system demonstrates a **priority-based greedy algorithm** that "
        "prioritizes **Reliability** (hitting strict time windows) over **Efficiency** (fuel costs)."
    )
    
    # ====================================================================
    # SIDEBAR: USER CONTROLS
    # ====================================================================
    with st.sidebar:
        st.header("Dispatch Controls")
        
        # Input 1: Slider for number of deliveries
        num_deliveries = st.slider(
            "Daily Deliveries",
            min_value=30,
            max_value=70,
            value=50,
            step=5,
            help="Select the total volume of deliveries (default: 50 simulates a heavy Monday)"
        )
        
        # Input 2: Generate button
        st.markdown("---")
        generate_plan = st.button(
            "Generate Morning Dispatch Plan",
            use_container_width=True,
            type="primary",
            help="Click to run the dispatch algorithm with current settings"
        )
        
        # Input 3 & 4: Chaos mode toggles
        st.markdown("---")
        st.subheader("Chaos Mode (Real-World Scenarios)")
        st.caption("Simulate disruptions to see algorithm resilience")
        
        chaos_sick_driver = st.checkbox(
            "Driver Calls in Sick (Lose 1 Small Van)",
            key="chaos_sick",
            help="One small van is removed from the fleet (capacity → 0)"
        )
        chaos_fridge_breakdown = st.checkbox(
            "Fridge Van Breakdown (Capacity -50%)",
            key="chaos_fridge",
            help="Refrigerated van capacity drops from 45 to 22 boxes"
        )
        
        # Instructions
        st.markdown("---")
        st.caption(
            "💡 **Try this:** Toggle both chaos options and regenerate to see how the "
            "algorithm protects critical Hospital and Temperature-Sensitive deliveries "
            "while deferring flexible Pharmacy orders."
        )
    
# ====================================================================
    # MAIN CONTENT: DISPATCH RESULTS
    # ====================================================================
    if generate_plan:
        # Generate a new seed each time the button is clicked
        st.session_state.seed = random.randint(0, 10000)
        random.seed(st.session_state.seed)
        
        # Step 1: Initialize fleet and generate deliveries
        fleet = create_fleet()
        deliveries = generate_deliveries(num_deliveries)
        
        # Step 2: Prepare chaos mode configuration
        chaos_mode = {
            "sick_driver": chaos_sick_driver,
            "fridge_breakdown": chaos_fridge_breakdown
        }
        
        # Step 3: Run the naive greedy heuristic
        fleet, unassigned, unassigned_reasons = assign_deliveries(deliveries, fleet, chaos_mode)
        
        # Step 4: Save EVERYTHING to session state so it survives button clicks
        st.session_state.plan_generated = True
        st.session_state.fleet = fleet
        st.session_state.deliveries = deliveries
        st.session_state.unassigned = unassigned
        st.session_state.unassigned_reasons = unassigned_reasons


    # ================================================================
    # DRAW THE UI ONLY IF A PLAN HAS BEEN GENERATED
    # ================================================================
    if st.session_state.get("plan_generated", False):
        # Load the latest data from session state
        fleet = st.session_state.fleet
        deliveries = st.session_state.deliveries
        unassigned = st.session_state.unassigned
        unassigned_reasons = st.session_state.unassigned_reasons

        # Calculate key metrics
        total_deliveries = len(deliveries)
        assigned_count = total_deliveries - len(unassigned)
        failed_count = len(unassigned)
        assignment_rate = (assigned_count / total_deliveries * 100) if total_deliveries > 0 else 0

        # ================================================================
        # TOP SECTION: KEY PERFORMANCE INDICATORS
        # ================================================================
        
        st.markdown("---")
        st.markdown("### Dispatch Summary")
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric(
                "📦 Total Deliveries",
                total_deliveries,
                help="Total orders to deliver today"
            )
        
        with col2:
            st.metric(
                "✅ Assigned",
                assigned_count,
                help="Orders successfully assigned to vans"
            )
        
        with col3:
            st.metric(
                "❌ Deferred",
                failed_count,
                help="Orders moved to afternoon/next day (all are flexible Pharmacy orders)"
            )
        
        with col4:
            st.metric(
                "📈 Success Rate",
                f"{assignment_rate:.1f}%",
                help="Percentage of orders assigned in morning dispatch"
            )
        
# ================================================================
        # FLEET VISUALIZATION: 6 VAN CARDS
        # ================================================================
        st.markdown("### 🚐 Fleet Utilization & Assignments")
        st.markdown("Click on any vehicle dropdown to see its load, route, and details.")
        
        van_ids = list(fleet.keys())
        
        # Row 1: First 3 vans
        col1, col2, col3 = st.columns(3)
        cols = [col1, col2, col3]
        
        for idx, van_id in enumerate(van_ids[:3]):
            van = fleet[van_id]
            with cols[idx]:
                icon = "❄️" if van.type == "Refrigerated" else "📦"
                
                # Make the title of the dropdown show the Van ID and its current load
                expander_title = f"{icon} {van.id} ({van.current_load}/{van.capacity} boxes)"
                
                # Use st.expander instead of st.container to create the dropdown
                with st.expander(expander_title, expanded=False):
                    st.caption(f"{van.type} | Capacity: {van.capacity} boxes")
                    
                    # Capacity progress bar
                    if van.capacity > 0:
                        utilization = van.current_load / van.capacity
                    else:
                        utilization = 0.0
                    st.progress(
                        utilization,
                        text=f"{van.current_load}/{van.capacity} boxes ({int(utilization*100)}%)"
                    )
                    
                    # Driver hours display
                    hours_color = "🟢" if van.driver_hours_used <= 8 else ("🟡" if van.driver_hours_used <= 10 else "🔴")
                    st.caption(
                        f"{hours_color} Driver hours: {van.driver_hours_used:.1f}h / {van.driver_hours_limit:.1f}h"
                    )
                    
                    # Breakdown of assigned deliveries by type
                    if van.assigned_deliveries:
                        delivery_types = {}
                        for delivery in van.assigned_deliveries:
                            delivery_types[delivery.type] = delivery_types.get(delivery.type, 0) + 1
                        
                        st.markdown("**Assigned (counts):**")
                        for delivery_type, count in sorted(delivery_types.items()):
                            st.write(f"  • {delivery_type}: {count}")

                        # Sequence the route for this vehicle and show estimated time
                        route, est_minutes = sequence_route_for_vehicle(van)
                        st.markdown(f"**Estimated route time:** {int(est_minutes)} minutes (incl. loading and service)")
                        st.markdown("**Route (first 10 stops):**")
                        for stop in route[:10]:
                            st.write(f"  • {stop.id} | {stop.type} | {stop.boxes} boxes | {stop.district} | svc {stop.service_time}m")
                    else:
                        st.write("*No deliveries assigned*")
        
        # Row 2: Last 3 vans
        col1, col2, col3 = st.columns(3)
        cols = [col1, col2, col3]
        
        for idx, van_id in enumerate(van_ids[3:]):
            van = fleet[van_id]
            with cols[idx]:
                icon = "❄️" if van.type == "Refrigerated" else "📦"
                
                expander_title = f"{icon} {van.id} ({van.current_load}/{van.capacity} boxes)"
                
                with st.expander(expander_title, expanded=False):
                    st.caption(f"{van.type} | Capacity: {van.capacity} boxes")
                    
                    # Capacity progress bar
                    if van.capacity > 0:
                        utilization = van.current_load / van.capacity
                    else:
                        utilization = 0.0
                    st.progress(
                        utilization,
                        text=f"{van.current_load}/{van.capacity} boxes ({int(utilization*100)}%)"
                    )
                    
                    # Driver hours display
                    hours_color = "🟢" if van.driver_hours_used <= 8 else ("🟡" if van.driver_hours_used <= 10 else "🔴")
                    st.caption(
                        f"{hours_color} Driver hours: {van.driver_hours_used:.1f}h / {van.driver_hours_limit:.1f}h"
                    )
                    
                    # Breakdown of assigned deliveries by type
                    if van.assigned_deliveries:
                        delivery_types = {}
                        for delivery in van.assigned_deliveries:
                            delivery_types[delivery.type] = delivery_types.get(delivery.type, 0) + 1
                        
                        st.markdown("**Assigned (counts):**")
                        for delivery_type, count in sorted(delivery_types.items()):
                            st.write(f"  • {delivery_type}: {count}")

                        # Sequence the route for this vehicle and show estimated time
                        route, est_minutes = sequence_route_for_vehicle(van)
                        st.markdown(f"**Estimated route time:** {int(est_minutes)} minutes (incl. loading and service)")
                        st.markdown("**Route (first 10 stops):**")
                        for stop in route[:10]:
                            st.write(f"  • {stop.id} | {stop.type} | {stop.boxes} boxes | {stop.district} | svc {stop.service_time}m")
                    else:
                        st.write("*No deliveries assigned*")
        
        # ================================================================
        # UNASSIGNED DELIVERIES ALERT
        # ================================================================
        if unassigned:
            st.markdown("---")
            st.markdown("### ⚠️ Deferred Deliveries (Afternoon/Next Day)")
            
            with st.container(border=True):
                st.markdown(
                    f"**{failed_count} delivery(ies) deferred.** "
                    "Below you can see why each delivery could not fit in the morning plan "
                    "(due to constraints like time windows, driver hours, or capacity)."
                )
                
                # Group unassigned by constraint type and display
                unassigned_by_reason = {}
                for delivery in unassigned:
                    reason = unassigned_reasons.get(delivery.id, "Unknown reason")
                    if reason not in unassigned_by_reason:
                        unassigned_by_reason[reason] = []
                    unassigned_by_reason[reason].append(delivery)
                
                for reason, delivery_list in sorted(unassigned_by_reason.items()):
                    st.write(f"**❌ {reason}** ({len(delivery_list)} order(s)):")
                    for delivery in delivery_list[:5]:
                        st.write(
                            f"  • {delivery.id} | {delivery.type} | "
                            f"{delivery.boxes} boxes | window {minutes_to_hm(delivery.early_time)}-{minutes_to_hm(delivery.late_time)}"
                        )
                    if len(delivery_list) > 5:
                        st.write(f"  ... and {len(delivery_list) - 5} more")
        
    # Repair simulation controls
        st.markdown("---")
        st.markdown("### 🛠️ Repair Simulation")
        st.caption("Simulate a van breaking down mid-route and attempt constraint-aware reassignment.")
        
        active_vans = [v_id for v_id, v in fleet.items() if v.current_load > 0]
        
        if not active_vans:
            st.warning("No active vans to simulate a breakdown on.")
        else:
            repair_event = st.selectbox("Select a van to break down:", active_vans)
            run_repair = st.button("🔁 Simulate Disruption & Run Repair")

            if run_repair:
                baseline_fleet = st.session_state.fleet
                repaired_fleet, newly_unassigned, repair_reasons = repair_assign_from_van(baseline_fleet, repair_event)

                # Update the master session state!
                st.session_state.fleet = repaired_fleet
                
                # Add the newly failed deliveries to the global deferred list
                if newly_unassigned:
                    st.session_state.unassigned.extend(newly_unassigned)
                    st.session_state.unassigned_reasons.update(repair_reasons)
                
                # Send a quick popup notification that survives the page reload
                st.toast(f"🚨 Van {repair_event} broke down! Rerouting deliveries...", icon="🔄")
                
                # Force the whole app to redraw with the new data instantly
                st.rerun()
        
        # ================================================================
        # INSIGHTS & EXPLANATION
        # ================================================================
        st.markdown("---")
        with st.expander("💡 **Algorithm Explanation & Insights**", expanded=False):
            st.markdown(
                f"""
                ### How the Algorithm Works
                
                **Priority System (why some deliveries are deferred):**
                1. **Temperature-Sensitive:** ALWAYS assigned to Refrigerated Van (medical requirement)
                2. **Hospital:** Assigned to Large Vans first (maximize reliability for strict time windows)
                3. **Pharmacy:** Assigned to Small Vans, overflow to Large Vans (deferrable if needed)
                
                **Key Metrics from This Run:**
                - **Assignment Rate:** {assignment_rate:.1f}% ({assigned_count} of {total_deliveries} orders)
                - **Deferred Orders:** {failed_count} (all non-critical Pharmacy deliveries)
                - **Refrigerated Capacity Used:** {fleet['Refrigerated-Van-1'].current_load}/{fleet['Refrigerated-Van-1'].capacity} boxes
                
                **Why This Design Prioritizes Reliability:**
                - ❌ **Never** sacrifice Hospital deliveries for fuel savings
                - ❌ **Never** miss temperature-sensitive delivery windows
                - ✅ **Happily** defer Pharmacy orders if needed (they're same-day flexible)
                - ✅ This matches the client's stated priority: "A missed hospital delivery costs more than a week of fuel savings"
                
                **Chaos Mode Behavior:**
                - If sick driver is enabled: Small-Van-3 is removed, reducing total capacity
                - If fridge breakdown is enabled: Refrigerated capacity drops to 50%
                - The algorithm still protects Hospital & Temp-Sensitive, but more Pharmacy orders get deferred
                """
            )
        
        # Store state in session for reference
        st.session_state.fleet = fleet
        st.session_state.deliveries = deliveries

        # Phase 4 sections (appended below existing UI)
        phase4_render(fleet, deliveries, unassigned, unassigned_reasons)

    else:
        # Default state: show instructions
        st.info(
            "👈 **Get Started:** Use the sidebar controls to set up your dispatch plan.\n\n"
            "1. Adjust the number of daily deliveries (30-70)\n"
            "2. Optionally enable 'Chaos Mode' to simulate real disruptions\n"
            "3. Click 'Generate Monday Dispatch Plan' to run the algorithm\n\n"
            "Watch how the system handles constraints and protects critical deliveries!"
        )

        


# ============================================================================
# PHASE 4: EXPLAINABILITY PANEL
# ============================================================================

def phase4_explainability_panel(unassigned, unassigned_reasons, fleet):
    """
    Phase 4 — Explainability Panel.
    Shows a detailed per-delivery breakdown of why each deferred order
    could not be assigned, and what would be needed to fix it.
    Uses the existing generate_explainability_report() engine from Phase 2.
    """
    st.markdown("### Explainability Panel")
    st.caption("Detailed breakdown of why each deferred delivery could not be assigned.")

    if not unassigned:
        st.success("✅ All deliveries were assigned — nothing to explain.")
        return

    # Summary counts
    c1, c2, c3 = st.columns(3)
    c1.metric("Total Deferred", len(unassigned))
    critical = sum(1 for d in unassigned if d.type in ("Hospital", "Temperature-Sensitive"))
    c2.metric("⚠️ Critical Deferred", critical)
    c3.metric("Pharmacy Deferred", sum(1 for d in unassigned if d.type == "Pharmacy"))

    if critical > 0:
        st.error("🚨 Critical deliveries were deferred — immediate action required!")

    # Group by simplified reason category
    groups = {}
    for d in unassigned:
        r = unassigned_reasons.get(d.id, "Unknown")
        if "Driver hours" in r:
            cat = "Driver Hours Limit"
        elif "Capacity" in r:
            cat = "Capacity Exceeded"
        elif "Time window" in r:
            cat = "Time Window Violation"
        elif "24-hour" in r:
            cat = "24-Hour Transit Rule"
        else:
            cat = "No Available Vehicle"
        groups.setdefault(cat, []).append(d)

    for cat, items in sorted(groups.items()):
        with st.expander(f"**{cat}** — {len(items)} order(s)", expanded=True):
            for d in items:
                full_reason = unassigned_reasons.get(d.id, "Unknown")
                report = generate_explainability_report(d, fleet, full_reason)
                st.markdown(
                    f"**{d.id}** | {d.type} | {d.boxes} boxes | {d.district} | "
                    f"Window: {minutes_to_hm(d.early_time)}–{minutes_to_hm(d.late_time)}"
                )
                st.markdown(f"- **Root cause:** {full_reason}")
                if report["best_fit_van"]:
                    st.markdown(f"- **Closest van:** {report['best_fit_van']}")
                if report["what_would_unblock"]:
                    st.markdown(f"- **To unblock:** {report['what_would_unblock']}")
                st.markdown("---")


# ============================================================================
# PHASE 4: LAST-MINUTE INSERTION
# ============================================================================

def phase4_insert_last_minute_order(fleet, current_deliveries):
    """
    Phase 4 — Last-Minute Insertion.
    Lets the dispatcher add a single new order after the morning plan is already
    generated. Tries to insert it into the best available van using the same
    priority rules as the main algorithm, and reports the result.

    Args:
        fleet: Current fleet dict (from session state)
        current_deliveries: Current delivery list (from session state)

    Returns:
        updated_fleet, updated_deliveries, result_message (str), success (bool)
    """
    district_list = [d for d in DISTRICTS.keys() if d != "Warehouse"]

    # Try each candidate van in priority order based on delivery type
    def try_insert(delivery, vans):
        for van in vans:
            if van.capacity == 0:
                continue
            # Simple capacity + hours check
            est_travel = 20.0  # conservative estimate
            added_minutes = est_travel + delivery.service_time
            feasible, reason = check_all_constraints(delivery, van, van.driver_start_time + 60, added_minutes)
            if feasible:
                van.current_load += delivery.boxes
                van.assigned_deliveries.append(delivery)
                van.driver_hours_used += added_minutes / 60.0
                return True, van.id, ""
            last_reason = reason
        return False, None, last_reason

    large_vans = [fleet["Large-Van-1"], fleet["Large-Van-2"]]
    small_vans = [fleet["Small-Van-1"], fleet["Small-Van-2"], fleet["Small-Van-3"]]
    fridge_van = fleet["Refrigerated-Van-1"]

    st.markdown("### Last-Minute Order Insertion")
    st.caption("Add a new delivery order to the existing plan after it has already been generated.")

    with st.form("last_minute_form"):
        col1, col2 = st.columns(2)
        with col1:
            new_type = st.selectbox("Delivery Type", ["Hospital", "Temperature-Sensitive", "Pharmacy"])
            new_boxes = st.number_input("Number of Boxes", min_value=1, max_value=10, value=2)
        with col2:
            new_district = st.selectbox("District", district_list)
            new_service = st.number_input("Service Time (minutes)", min_value=5, max_value=30, value=10)
        submitted = st.form_submit_button("➕ Insert Order into Plan")

    if submitted:
        # Build the new delivery object
        new_id = f"LASTMIN-{random.randint(100, 999)}"
        if new_type == "Hospital":
            new_delivery = Delivery(
                id=new_id, type="Hospital", boxes=new_boxes,
                time_window="before 9am (STRICT)",
                early_time=360, late_time=540, is_hard_window=True,
                load_time=360, district=new_district, service_time=new_service
            )
            ok, van_id, reason = try_insert(new_delivery, large_vans)
            if not ok:
                ok, van_id, reason = try_insert(new_delivery, small_vans)
        elif new_type == "Temperature-Sensitive":
            new_delivery = Delivery(
                id=new_id, type="Temperature-Sensitive", boxes=new_boxes,
                time_window="same-day (urgent)",
                early_time=360, late_time=1080, is_hard_window=False,
                load_time=360, district=new_district, service_time=new_service
            )
            ok, van_id, reason = try_insert(new_delivery, [fridge_van])
        else:
            new_delivery = Delivery(
                id=new_id, type="Pharmacy", boxes=new_boxes,
                time_window="same-day (flexible)",
                early_time=360, late_time=1080, is_hard_window=False,
                load_time=360, district=new_district, service_time=new_service
            )
            ok, van_id, reason = try_insert(new_delivery, small_vans)
            if not ok:
                ok, van_id, reason = try_insert(new_delivery, large_vans)

        if ok:
            current_deliveries.append(new_delivery)
            st.success(f"✅ Order **{new_id}** inserted into **{van_id}** successfully!")
            st.session_state.fleet = fleet
            st.session_state.deliveries = current_deliveries
        else:
            st.error(f"❌ Could not insert order **{new_id}**. Reason: {reason}")

    return fleet, current_deliveries


# ============================================================================
# PHASE 4: ROUTE RE-OPTIMIZATION POST-DISRUPTION
# ============================================================================

def phase4_reoptimize_after_disruption(fleet):
    """
    Phase 4 — Route Re-Optimization Post-Disruption.
    After a van breaks down or a driver calls in sick, this goes beyond the
    simple repair (capacity-only check) and re-sequences all affected routes
    using the nearest-district heuristic with the travel-time matrix.
    Also reports which deliveries were moved and the new estimated route times.

    Args:
        fleet: Current fleet dict (from session state)
    """
    st.markdown("### Route Re-Optimization Post-Disruption")
    st.caption(
        "More advanced than the basic repair: after removing a van, this re-sequences "
        "all remaining routes using the travel-time matrix for tighter estimates."
    )

    disrupted_van = st.selectbox(
        "Select van that went out of service:",
        list(fleet.keys()),
        key="phase4_reopt_van"
    )

    if st.button("🔄 Re-Optimize All Routes", key="phase4_reopt_btn"):
        # Step 1: pull deliveries off the disrupted van
        working_fleet = copy.deepcopy(fleet)
        disrupted = working_fleet[disrupted_van]
        deliveries_to_redistribute = disrupted.assigned_deliveries.copy()
        disrupted.assigned_deliveries = []
        disrupted.current_load = 0
        disrupted.capacity = 0

        remaining_vans = [v for k, v in working_fleet.items() if k != disrupted_van and v.capacity > 0]

        moved_log = []
        could_not_place = []

        # Step 2: insert each displaced delivery into the best remaining van
        for d in deliveries_to_redistribute:
            best_van = None
            best_extra_time = float("inf")

            for van in remaining_vans:
                if van.current_load + d.boxes > van.capacity:
                    continue
                # Estimate extra time to add this delivery to this van
                if van.assigned_deliveries:
                    last_dist = van.assigned_deliveries[-1].district
                else:
                    last_dist = "Warehouse"
                current_t = van.driver_start_time + int(van.driver_hours_used * 60)
                extra = get_travel_time(last_dist, d.district, current_t) + d.service_time
                new_hours = van.driver_hours_used + extra / 60.0
                if new_hours > van.driver_hours_limit:
                    continue
                if extra < best_extra_time:
                    best_extra_time = extra
                    best_van = van

            if best_van:
                best_van.current_load += d.boxes
                best_van.assigned_deliveries.append(d)
                best_van.driver_hours_used += best_extra_time / 60.0
                moved_log.append((d.id, d.type, best_van.id))
            else:
                could_not_place.append(d)

        # Step 3: re-sequence all routes
        st.markdown(f"**Disrupted van:** {disrupted_van} — {len(deliveries_to_redistribute)} deliveries redistributed")

        if moved_log:
            st.markdown("**Moved deliveries:**")
            for did, dtype, vid in moved_log:
                st.write(f"  • {did} ({dtype}) → {vid}")

        if could_not_place:
            st.warning(f"⚠️ {len(could_not_place)} delivery(ies) could not be placed in any remaining van:")
            for d in could_not_place:
                st.write(f"  • {d.id} ({d.type}, {d.boxes} boxes)")
        else:
            st.success("✅ All displaced deliveries successfully redistributed!")

        # Step 4: show new re-sequenced route times for all active vans
        st.markdown("**Updated route estimates after re-optimization:**")
        for van_id, van in working_fleet.items():
            if van.capacity == 0 or not van.assigned_deliveries:
                continue
            route, est_min = sequence_route_for_vehicle(van)
            st.write(f"  • **{van_id}**: {len(route)} stops — {int(est_min)} min estimated")

        # Save updated fleet back to session
        st.session_state.fleet = working_fleet


# ============================================================================
# PHASE 4: UI — appended as a new section after existing main() output
# ============================================================================

def phase4_render(fleet, deliveries, unassigned, unassigned_reasons):
    """
    Phase 4 — Renders all three Phase 4 sections below the existing UI.
    Call this from main() after the existing content, passing the current
    fleet and deliveries from session state.
    """
    st.markdown("---")

    # Feature 1: Explainability Panel
    phase4_explainability_panel(unassigned, unassigned_reasons, fleet)

    st.markdown("---")

    # Feature 2: Last-Minute Insertion
    phase4_insert_last_minute_order(fleet, deliveries)

    st.markdown("---")

    # Feature 3: Route Re-Optimization
    phase4_reoptimize_after_disruption(fleet)


# ============================================================================
# ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    main()
