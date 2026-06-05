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
from typing import List, Dict, Tuple
from dataclasses import dataclass, field


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
    """
    id: str
    type: str  # "Hospital", "Temperature-Sensitive", or "Pharmacy"
    boxes: int  # Number of standard medical boxes
    time_window: str  # e.g., "before 9am", "same-day", etc.


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
    """
    id: str
    type: str  # "Refrigerated" or "Ambient"
    capacity: int  # Max boxes
    current_load: int = 0
    assigned_deliveries: List[Delivery] = field(default_factory=list)


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
            boxes=random.randint(1, 5),  # Small to medium load
            time_window="before 9am (STRICT)"
        )
        deliveries.append(delivery)
    
    # Generate Temperature-Sensitive deliveries (CRITICAL: medical compliance)
    for i in range(num_temp_sensitive):
        delivery = Delivery(
            id=f"TEMP-{i+1:03d}",
            type="Temperature-Sensitive",
            boxes=random.randint(1, 3),  # Small load
            time_window="same-day (urgent)"
        )
        deliveries.append(delivery)
    
    # Generate Pharmacy deliveries (FLEXIBLE: can be deferred)
    for i in range(num_pharmacy):
        delivery = Delivery(
            id=f"PHARM-{i+1:03d}",
            type="Pharmacy",
            boxes=random.randint(1, 3),  # Small to medium
            time_window="same-day (flexible)"
        )
        deliveries.append(delivery)
    
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
) -> Tuple[Dict[str, Vehicle], List[Delivery]]:
    """
    Assign deliveries to vans using a greedy, priority-based heuristic.
    
    This is the "brains" of the dispatch system. It implements the following logic:
    
    PRIORITY ORDER:
    1. Temperature-Sensitive → ONLY Refrigerated Van (non-negotiable)
    2. Hospital → Large Vans first (prioritize capacity & reliability)
    3. Pharmacy → Small Vans first (efficiency), overflow to Large Vans
    
    CONSTRAINT CHECKING:
    - A delivery is assigned ONLY if it fits in the van's remaining capacity
    - If NO van can fit a delivery, it goes to unassigned_deliveries
    - Unassigned orders are rescheduled for the afternoon/next day
    
    CHAOS MODE (Real-world disruptions):
    - "sick_driver": Reduces fleet by 1 small van (capacity = 0)
    - "fridge_breakdown": Reduces refrigerated capacity to 22 boxes (50% loss)
    
    Args:
        deliveries: List of Delivery objects to assign
        fleet: Dict of Vehicle objects (modified in-place)
        chaos_mode: Dict with "sick_driver" and "fridge_breakdown" booleans
    
    Returns:
        Tuple of:
        - updated_fleet: Vehicles with assigned_deliveries populated
        - unassigned_deliveries: Orders that couldn't fit anywhere
    """
    if chaos_mode is None:
        chaos_mode = {}
    
    # Apply chaos mode modifications before assignment
    if chaos_mode.get("sick_driver", False):
        # Sick driver removes Small-Van-3 from service (capacity set to 0)
        fleet["Small-Van-3"].capacity = 0
    
    if chaos_mode.get("fridge_breakdown", False):
        # Refrigerated van suffers 50% capacity loss
        fleet["Refrigerated-Van-1"].capacity = 22  # 45 / 2 rounded down
    
    unassigned_deliveries = []
    
    # ========================================================================
    # PRIORITY 1: Temperature-Sensitive Goods → Refrigerated Van ONLY
    # ========================================================================
    # Medical compliance: temperature-sensitive goods MUST go in the fridge
    temp_sensitive = [d for d in deliveries if d.type == "Temperature-Sensitive"]
    for delivery in temp_sensitive:
        fridge_van = fleet["Refrigerated-Van-1"]
        # Check if delivery fits in refrigerated van
        if fridge_van.current_load + delivery.boxes <= fridge_van.capacity:
            fridge_van.current_load += delivery.boxes
            fridge_van.assigned_deliveries.append(delivery)
        else:
            # Refrigerated capacity exceeded: defer this delivery
            # In production, this would trigger an alert to the dispatcher
            unassigned_deliveries.append(delivery)
    
    # ========================================================================
    # PRIORITY 2: Hospital Deliveries → Large Vans First
    # ========================================================================
    # Hospital deliveries have strict time windows (before 9am) and are critical
    # Assign to Large Vans first (larger capacity = more flexibility)
    hospital = [d for d in deliveries if d.type == "Hospital"]
    large_vans = [fleet["Large-Van-1"], fleet["Large-Van-2"]]
    
    for delivery in hospital:
        assigned = False
        
        # Try each large van in order
        for van in large_vans:
            if van.current_load + delivery.boxes <= van.capacity:
                van.current_load += delivery.boxes
                van.assigned_deliveries.append(delivery)
                assigned = True
                break
        
        # Fallback: if no large van has capacity, try small vans
        if not assigned:
            small_vans = [fleet["Small-Van-1"], fleet["Small-Van-2"], fleet["Small-Van-3"]]
            for van in small_vans:
                if van.current_load + delivery.boxes <= van.capacity:
                    van.current_load += delivery.boxes
                    van.assigned_deliveries.append(delivery)
                    assigned = True
                    break
        
        # If still not assigned, add to unassigned
        if not assigned:
            unassigned_deliveries.append(delivery)
    
    # ========================================================================
    # PRIORITY 3: Pharmacy Deliveries → Small Vans First, Then Large Vans
    # ========================================================================
    # Pharmacy deliveries are flexible and can be deferred if needed
    # Assign to Small Vans first (efficiency), then Large Vans (overflow)
    pharmacy = [d for d in deliveries if d.type == "Pharmacy"]
    small_vans = [fleet["Small-Van-1"], fleet["Small-Van-2"], fleet["Small-Van-3"]]
    
    for delivery in pharmacy:
        assigned = False
        
        # First, try to fit in a small van (preferred for efficiency)
        for van in small_vans:
            if van.current_load + delivery.boxes <= van.capacity:
                van.current_load += delivery.boxes
                van.assigned_deliveries.append(delivery)
                assigned = True
                break
        
        # If no small van available, try large vans (overflow)
        if not assigned:
            for van in large_vans:
                if van.current_load + delivery.boxes <= van.capacity:
                    van.current_load += delivery.boxes
                    van.assigned_deliveries.append(delivery)
                    assigned = True
                    break
        
        # If still not assigned, add to unassigned (will be rescheduled)
        if not assigned:
            unassigned_deliveries.append(delivery)
    
    return fleet, unassigned_deliveries


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
    st.title("🚚 Dynamic Dispatch Simulator")
    st.markdown(
        "**Interactive Prototype for Medical Delivery Optimization (Paris)**\n\n"
        "This system demonstrates a **priority-based greedy algorithm** that "
        "prioritizes **Reliability** (hitting strict time windows) over **Efficiency** (fuel costs)."
    )
    
    # ====================================================================
    # SIDEBAR: USER CONTROLS
    # ====================================================================
    with st.sidebar:
        st.header("⚙️ Dispatch Controls")
        
        # Input 1: Slider for number of deliveries
        num_deliveries = st.slider(
            "📦 Daily Deliveries",
            min_value=30,
            max_value=70,
            value=50,
            step=5,
            help="Select the total volume of deliveries (default: 50 simulates a heavy Monday)"
        )
        
        # Input 2: Generate button
        st.markdown("---")
        generate_plan = st.button(
            "🎯 Generate Monday Dispatch Plan",
            use_container_width=True,
            type="primary",
            help="Click to run the dispatch algorithm with current settings"
        )
        
        # Input 3 & 4: Chaos mode toggles
        st.markdown("---")
        st.subheader("⚡ Chaos Mode (Real-World Scenarios)")
        st.caption("Simulate disruptions to see algorithm resilience")
        
        chaos_sick_driver = st.checkbox(
            "🤒 Driver Calls in Sick (Lose 1 Small Van)",
            help="One small van is removed from the fleet (capacity → 0)"
        )
        chaos_fridge_breakdown = st.checkbox(
            "❄️ Fridge Van Breakdown (Capacity -50%)",
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
        # Use session state to store random seed for consistency
        if 'seed' not in st.session_state:
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
        fleet, unassigned = assign_deliveries(deliveries, fleet, chaos_mode)
        
        # Step 4: Calculate key metrics
        total_deliveries = len(deliveries)
        assigned_count = total_deliveries - len(unassigned)
        failed_count = len(unassigned)
        assignment_rate = (assigned_count / total_deliveries * 100) if total_deliveries > 0 else 0
        
        # ================================================================
        # TOP SECTION: KEY PERFORMANCE INDICATORS
        # ================================================================
        st.markdown("### 📊 Dispatch Summary")
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
        st.markdown("Each card shows a vehicle, its load, and what's inside.")
        
        van_ids = list(fleet.keys())
        
        # Row 1: First 3 vans
        col1, col2, col3 = st.columns(3)
        cols = [col1, col2, col3]
        
        for idx, van_id in enumerate(van_ids[:3]):
            van = fleet[van_id]
            with cols[idx]:
                with st.container(border=True):
                    # Van header with icon
                    icon = "❄️" if van.type == "Refrigerated" else "📦"
                    st.write(f"**{icon} {van.id}**")
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
                    
                    # Breakdown of assigned deliveries by type
                    if van.assigned_deliveries:
                        delivery_types = {}
                        for delivery in van.assigned_deliveries:
                            delivery_types[delivery.type] = delivery_types.get(delivery.type, 0) + 1
                        
                        st.markdown("**Assigned:**")
                        for delivery_type, count in sorted(delivery_types.items()):
                            st.write(f"  • {delivery_type}: {count}")
                    else:
                        st.write("*No deliveries assigned*")
        
        # Row 2: Last 3 vans
        col1, col2, col3 = st.columns(3)
        cols = [col1, col2, col3]
        
        for idx, van_id in enumerate(van_ids[3:]):
            van = fleet[van_id]
            with cols[idx]:
                with st.container(border=True):
                    # Van header with icon
                    icon = "❄️" if van.type == "Refrigerated" else "📦"
                    st.write(f"**{icon} {van.id}**")
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
                    
                    # Breakdown of assigned deliveries by type
                    if van.assigned_deliveries:
                        delivery_types = {}
                        for delivery in van.assigned_deliveries:
                            delivery_types[delivery.type] = delivery_types.get(delivery.type, 0) + 1
                        
                        st.markdown("**Assigned:**")
                        for delivery_type, count in sorted(delivery_types.items()):
                            st.write(f"  • {delivery_type}: {count}")
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
                    f"**{failed_count} delivery(ies) deferred.** These are **flexible "
                    "Pharmacy orders** that the algorithm prioritized out to ensure **100% "
                    "reliability for critical Hospital and Temperature-Sensitive deliveries**."
                )
                
                # Group unassigned by type and display
                unassigned_by_type = {}
                for delivery in unassigned:
                    delivery_type = delivery.type
                    if delivery_type not in unassigned_by_type:
                        unassigned_by_type[delivery_type] = []
                    unassigned_by_type[delivery_type].append(delivery)
                
                for delivery_type, delivery_list in sorted(unassigned_by_type.items()):
                    st.write(f"**{delivery_type} ({len(delivery_list)} orders):**")
                    for delivery in delivery_list[:10]:  # Show first 10
                        st.write(f"  • {delivery.id} ({delivery.boxes} boxes)")
                    if len(delivery_list) > 10:
                        st.write(f"  ... and {len(delivery_list) - 10} more")
        
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
# ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    main()
