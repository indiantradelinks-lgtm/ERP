"""Static catalogues + seed data for the AI Quotation module.

`SERVICE_BASES`         : permissible RFQ bases per service.
`BASIS_FIELDS`          : extra contextual fields to render in the UI per (service, basis).
`PRESET_ITEMS`          : suggested line items per (service, basis) — used by frontend
                          quick-add and by the Claude-suggest prompt as priors.
`DEFAULT_CONDITIONS`    : technical / commercial / inclusion / exclusion clauses
                          seeded into `db.condition_library` on first startup.
"""
from typing import Dict, List

SERVICES = ["scaffolding", "painting", "rope_access", "insulation", "roof_sheeting"]

SERVICE_BASES: Dict[str, List[str]] = {
    "scaffolding": [
        "manpower_material", "material_only", "manpower_only", "volume", "area",
        "monthly_rental", "erection_dismantling", "shutdown", "lump_sum",
    ],
    "painting": [
        "manpower_material", "manpower_only", "material_only", "area",
        "item_rate", "lump_sum",
    ],
    "rope_access": [
        "manpower_only", "manpower_tools", "job", "height_access", "area", "lump_sum",
    ],
    "insulation": [
        "manpower_material", "material_only", "manpower_only", "area",
        "running_meter", "thickness", "lump_sum",
    ],
    "roof_sheeting": [
        "manpower_material", "material_only", "manpower_only", "area",
        "running_meter", "item_rate", "lump_sum",
    ],
}

# Friendly labels (frontend uses these)
BASIS_LABELS = {
    "manpower_material": "Manpower + Material",
    "material_only": "Material Only Supply",
    "manpower_only": "Manpower Only Supply",
    "volume": "Volume Basis",
    "area": "Area Basis (m²)",
    "monthly_rental": "Monthly Rental",
    "erection_dismantling": "Erection & Dismantling",
    "shutdown": "Shutdown Project",
    "lump_sum": "Lump Sum",
    "manpower_tools": "Manpower + Tools",
    "job": "Per Job",
    "height_access": "Height / Access Basis",
    "item_rate": "Item Rate",
    "running_meter": "Running Meter",
    "thickness": "Thickness Basis",
}

# Extra header fields to capture per basis (frontend renders dynamically)
BASIS_FIELDS: Dict[str, List[Dict]] = {
    "scaffolding": [
        {"key": "scaffold_type", "label": "Scaffolding Type", "type": "select",
         "options": ["cuplock", "tubular", "ring_lock", "h_frame", "mobile", "other"]},
        {"key": "height", "label": "Avg / Max Height (m)", "type": "number"},
        {"key": "area_or_volume", "label": "Area / Volume (m² or m³)", "type": "number"},
        {"key": "duration_days", "label": "Expected Duration (days)", "type": "number"},
        {"key": "mobilization_date", "label": "Mobilization Date", "type": "date"},
        {"key": "demobilization_date", "label": "Demobilization Date", "type": "date"},
    ],
    "painting": [
        {"key": "paint_type", "label": "Paint Type", "type": "select",
         "options": ["epoxy", "enamel", "emulsion", "pu", "polyurethane", "zinc_rich", "other"]},
        {"key": "surface_type", "label": "Surface", "type": "select",
         "options": ["steel_structure", "concrete", "tank", "pipeline", "wall", "floor", "other"]},
        {"key": "coats", "label": "Number of Coats", "type": "number"},
        {"key": "dft", "label": "DFT (microns)", "type": "number"},
        {"key": "area_sqm", "label": "Area (m²)", "type": "number"},
    ],
    "rope_access": [
        {"key": "work_type", "label": "Work Type", "type": "select",
         "options": ["inspection", "painting", "welding", "cleaning", "installation", "ndt", "other"]},
        {"key": "height", "label": "Height (m)", "type": "number"},
        {"key": "access_difficulty", "label": "Access Difficulty", "type": "select",
         "options": ["easy", "moderate", "difficult", "extreme"]},
        {"key": "rope_tech_count", "label": "Rope Access Technicians", "type": "number"},
        {"key": "certification", "label": "Cert Level (IRATA/SPRAT)", "type": "select",
         "options": ["level_1", "level_2", "level_3", "mixed"]},
    ],
    "insulation": [
        {"key": "insulation_type", "label": "Insulation Type", "type": "select",
         "options": ["hot", "cold", "acoustic", "cryogenic", "fire_proof", "other"]},
        {"key": "material", "label": "Material", "type": "select",
         "options": ["rock_wool", "glass_wool", "mineral_wool", "puf", "ceramic_fibre", "other"]},
        {"key": "thickness_mm", "label": "Thickness (mm)", "type": "number"},
        {"key": "cladding", "label": "Cladding", "type": "select",
         "options": ["aluminium", "ss", "gi", "none"]},
        {"key": "area_or_length", "label": "Area (m²) / Length (m)", "type": "number"},
    ],
    "roof_sheeting": [
        {"key": "sheet_type", "label": "Sheet Type", "type": "select",
         "options": ["color_coated", "galvanised", "gi", "frp", "polycarbonate", "tin", "other"]},
        {"key": "sheet_thickness", "label": "Sheet Thickness (mm)", "type": "number"},
        {"key": "area_sqm", "label": "Roof Area (m²)", "type": "number"},
        {"key": "height", "label": "Working Height (m)", "type": "number"},
        {"key": "gutter_required", "label": "Gutter Required", "type": "select",
         "options": ["yes", "no"]},
    ],
}


def _item(description: str, unit: str, hsn: str = "9987", gst: float = 18.0, qty: float = 1, rate: float = 0):
    return {"description": description, "unit": unit, "hsn_sac": hsn, "gst_pct": gst,
            "quantity": qty, "rate": rate}


# (service, basis) → ordered list of suggested line items
PRESET_ITEMS: Dict[str, Dict[str, List[Dict]]] = {
    "scaffolding": {
        "manpower_material": [
            _item("Scaffolding material supply on rental basis", "m³", "9986"),
            _item("Erection of scaffolding", "m³", "9954"),
            _item("Dismantling of scaffolding", "m³", "9954"),
            _item("Skilled scaffolder manpower", "day", "9985"),
            _item("Helper / khalasi manpower", "day", "9985"),
            _item("Supervisor deployment", "day", "9985"),
            _item("Safety compliance & PPE", "lot", "9985"),
            _item("Transportation - Mob/Demob", "lot", "9965"),
        ],
        "material_only": [
            _item("Cuplock verticals (3.0m)", "Nos", "7308"),
            _item("Cuplock ledgers (2.0m)", "Nos", "7308"),
            _item("Cuplock braces", "Nos", "7308"),
            _item("Base jacks / U-heads", "Nos", "7308"),
            _item("Steel planks", "Nos", "7308"),
            _item("Tubes (40NB / 48mm OD)", "m", "7308"),
            _item("Couplers / clamps", "Nos", "7308"),
            _item("Safety net / mesh", "m²", "5608"),
            _item("Transportation & loading", "lot", "9965"),
        ],
        "manpower_only": [
            _item("Scaffolder (skilled)", "day", "9985"),
            _item("Helper / khalasi", "day", "9985"),
            _item("Scaffolding supervisor", "day", "9985"),
            _item("Safety officer", "day", "9985"),
            _item("Rigger (if required)", "day", "9985"),
        ],
        "volume": [
            _item("Scaffolding erection on volume basis", "m³", "9954"),
            _item("Scaffolding dismantling on volume basis", "m³", "9954"),
            _item("Scaffolding rental on volume basis", "m³/month", "9986"),
            _item("Extra height / difficult access charges", "m³", "9954"),
        ],
        "area": [
            _item("Scaffolding works on area basis", "m²", "9954"),
            _item("Rental on area basis", "m²/month", "9986"),
        ],
        "monthly_rental": [
            _item("Scaffolding monthly rental", "lot/month", "9986"),
            _item("Initial erection", "lot", "9954"),
            _item("Final dismantling", "lot", "9954"),
        ],
        "erection_dismantling": [
            _item("Erection of scaffolding", "m³", "9954"),
            _item("Dismantling of scaffolding", "m³", "9954"),
        ],
        "shutdown": [
            _item("Shutdown scaffolding package", "lot", "9954"),
            _item("Round-the-clock scaffolder team", "shift", "9985"),
            _item("Standby crew", "shift", "9985"),
        ],
        "lump_sum": [
            _item("Scaffolding works - lump sum", "lot", "9954"),
        ],
    },
    "painting": {
        "manpower_material": [
            _item("Surface preparation - power tool cleaning (St3)", "m²", "9987"),
            _item("Primer application - 1 coat", "m²", "9987"),
            _item("Intermediate coat", "m²", "9987"),
            _item("Final / finish coat", "m²", "9987"),
            _item("Paint material supply", "ltr", "3208"),
            _item("Painter manpower", "day", "9985"),
            _item("Helper", "day", "9985"),
            _item("Spray machine / tools", "day", "9987"),
        ],
        "manpower_only": [
            _item("Painter (skilled)", "day", "9985"),
            _item("Helper", "day", "9985"),
            _item("Painting supervisor", "day", "9985"),
        ],
        "material_only": [
            _item("Epoxy primer", "ltr", "3208"),
            _item("Epoxy intermediate", "ltr", "3208"),
            _item("PU top coat", "ltr", "3208"),
            _item("Thinner", "ltr", "3814"),
            _item("Consumables (rollers/brushes/tape)", "lot", "9603"),
        ],
        "area": [
            _item("Painting on area basis - complete system", "m²", "9987"),
            _item("Touch-up work", "m²", "9987"),
        ],
        "item_rate": [
            _item("Item rate painting - per item", "Nos", "9987"),
        ],
        "lump_sum": [
            _item("Painting works - lump sum", "lot", "9987"),
        ],
    },
    "rope_access": {
        "manpower_only": [
            _item("Rope access technician (L1)", "day", "9985"),
            _item("Rope access technician (L2)", "day", "9985"),
            _item("Rope access supervisor (L3)", "day", "9985"),
            _item("Safety officer / rescue standby", "day", "9985"),
        ],
        "manpower_tools": [
            _item("Rope access technician with kit", "day", "9985"),
            _item("Rope access supervisor with kit", "day", "9985"),
            _item("Tools and tackles deployment", "day", "9987"),
            _item("Rescue arrangement", "day", "9985"),
        ],
        "job": [
            _item("Rope access work execution - per job", "Nos", "9987"),
            _item("Mobilization", "lot", "9965"),
            _item("Demobilization", "lot", "9965"),
            _item("Safety documentation", "lot", "9987"),
        ],
        "height_access": [
            _item("Rope access works - height based", "m height", "9987"),
        ],
        "area": [
            _item("Rope access works on area basis", "m²", "9987"),
        ],
        "lump_sum": [
            _item("Rope access works - lump sum", "lot", "9987"),
        ],
    },
    "insulation": {
        "manpower_material": [
            _item("Rock wool / glass wool supply", "m³", "6806"),
            _item("Aluminium cladding sheet (24 SWG)", "m²", "7606"),
            _item("Wire mesh / chicken wire", "m²", "7314"),
            _item("Binding wire / SS bands", "kg", "7217"),
            _item("Sealant / silicone", "kg", "3214"),
            _item("Insulation fixing - skilled labour", "m²", "9954"),
            _item("Cladding fixing - skilled labour", "m²", "9954"),
            _item("Helper / khalasi", "day", "9985"),
        ],
        "material_only": [
            _item("Rock wool blanket", "m³", "6806"),
            _item("Glass wool", "m³", "6806"),
            _item("Aluminium cladding", "m²", "7606"),
            _item("SS bands / buckles", "kg", "7326"),
        ],
        "manpower_only": [
            _item("Skilled insulation fitter", "day", "9985"),
            _item("Cladding fitter", "day", "9985"),
            _item("Helper", "day", "9985"),
        ],
        "area": [
            _item("Insulation + cladding on area basis", "m²", "9954"),
        ],
        "running_meter": [
            _item("Pipe insulation on running meter basis", "m", "9954"),
        ],
        "thickness": [
            _item("Insulation works on thickness basis", "m²·mm", "9954"),
        ],
        "lump_sum": [
            _item("Insulation works - lump sum", "lot", "9954"),
        ],
    },
    "roof_sheeting": {
        "manpower_material": [
            _item("Color-coated roofing sheet (0.5mm)", "m²", "7210"),
            _item("Self-drilling fasteners with EPDM", "Nos", "7318"),
            _item("EPDM sealant", "ltr", "3506"),
            _item("Flashing / ridge cap", "m", "7308"),
            _item("Gutter (color-coated)", "m", "7308"),
            _item("Roof sheet fixing - skilled labour", "m²", "9954"),
            _item("Old sheet removal (if applicable)", "m²", "9954"),
            _item("Safety lifeline arrangement", "lot", "9985"),
        ],
        "material_only": [
            _item("Color-coated GI sheet", "m²", "7210"),
            _item("Fasteners and seals", "lot", "7318"),
            _item("Flashing & accessories", "m", "7308"),
        ],
        "manpower_only": [
            _item("Roof sheet fitter (skilled)", "day", "9985"),
            _item("Helper", "day", "9985"),
            _item("Supervisor", "day", "9985"),
        ],
        "area": [
            _item("Roofing works on area basis", "m²", "9954"),
        ],
        "running_meter": [
            _item("Gutter / ridge on running meter basis", "m", "9954"),
        ],
        "item_rate": [
            _item("Item rate roof work", "Nos", "9954"),
        ],
        "lump_sum": [
            _item("Roof sheeting works - lump sum", "lot", "9954"),
        ],
    },
}


# Conditions library — seeded on startup if collection is empty.
DEFAULT_CONDITIONS: List[Dict] = [
    # --- Technical · common ---
    {"category": "technical", "service": "common", "order": 1,
     "text": "Work shall be executed strictly as per the approved scope of work and as per site safety guidelines."},
    {"category": "technical", "service": "common", "order": 2,
     "text": "Client shall provide a clear work front, access, and necessary permits before commencement of work."},
    {"category": "technical", "service": "common", "order": 3,
     "text": "Any additional work beyond the quoted scope shall be charged extra at agreed rates."},
    {"category": "technical", "service": "common", "order": 4,
     "text": "Measurement shall be jointly certified by the client representative and INDIAN TRADE LINKS supervisor."},
    {"category": "technical", "service": "common", "order": 5,
     "text": "Work completion shall depend on site clearance, access continuity, and timely availability of work front."},
    {"category": "technical", "service": "common", "order": 6,
     "text": "All statutory permits (height pass, hot work, confined space, etc.) shall be arranged before execution."},
    # --- Technical · scaffolding ---
    {"category": "technical", "service": "scaffolding", "order": 1,
     "text": "Scaffolding shall be erected as per site requirement and prevailing safety norms (BIS / OSHA / client standard)."},
    {"category": "technical", "service": "scaffolding", "order": 2,
     "text": "Scaffolding material shall remain the property of INDIAN TRADE LINKS unless specifically sold."},
    {"category": "technical", "service": "scaffolding", "order": 3,
     "text": "Any damage, shortage, or loss of scaffolding material at the client site shall be charged extra at replacement rate."},
    {"category": "technical", "service": "scaffolding", "order": 4,
     "text": "Dismantling shall be carried out only after a written instruction / clearance from the client."},
    {"category": "technical", "service": "scaffolding", "order": 5,
     "text": "Rental shall continue until the material is physically returned or dismantling clearance is provided."},
    # --- Technical · painting ---
    {"category": "technical", "service": "painting", "order": 1,
     "text": "Surface preparation shall be done as per agreed scope and applicable paint system data sheet."},
    {"category": "technical", "service": "painting", "order": 2,
     "text": "Paint consumption may vary depending on actual surface condition; theoretical coverage is indicative only."},
    {"category": "technical", "service": "painting", "order": 3,
     "text": "Any additional coat beyond the agreed paint system shall be charged separately."},
    {"category": "technical", "service": "painting", "order": 4,
     "text": "Client shall provide adequate work front, lighting, ventilation, and access for execution."},
    # --- Technical · rope access ---
    {"category": "technical", "service": "rope_access", "order": 1,
     "text": "Rope access work is subject to safe anchorage availability and site feasibility assessment."},
    {"category": "technical", "service": "rope_access", "order": 2,
     "text": "Rescue plan and emergency access shall be confirmed before commencement of work."},
    {"category": "technical", "service": "rope_access", "order": 3,
     "text": "Work shall be stopped during unsafe weather conditions (high wind, lightning, rain) without penalty."},
    # --- Technical · insulation ---
    {"category": "technical", "service": "insulation", "order": 1,
     "text": "Insulation quantity shall be measured and certified on the actual executed work basis."},
    {"category": "technical", "service": "insulation", "order": 2,
     "text": "Any change in insulation thickness, material grade, or cladding specification shall be re-quoted."},
    {"category": "technical", "service": "insulation", "order": 3,
     "text": "Cladding and finishing shall be carried out as per the approved specification only."},
    # --- Technical · roof sheeting ---
    {"category": "technical", "service": "roof_sheeting", "order": 1,
     "text": "Roof work shall be subject to weather conditions and confirmed safe access arrangements."},
    {"category": "technical", "service": "roof_sheeting", "order": 2,
     "text": "Client shall provide a clear working area, with all obstructions removed at the work front."},
    {"category": "technical", "service": "roof_sheeting", "order": 3,
     "text": "Any structural repair or strengthening of the existing roof framework is excluded unless mentioned."},
    {"category": "technical", "service": "roof_sheeting", "order": 4,
     "text": "Additional safety lifelines, edge protection, or man-lift arrangement shall be charged separately."},

    # --- Commercial · common ---
    {"category": "commercial", "service": "common", "order": 1,
     "text": "Prices quoted are exclusive of GST. GST shall be charged extra as applicable at the prevailing rate."},
    {"category": "commercial", "service": "common", "order": 2,
     "text": "Payment shall be made as per the agreed payment terms mentioned in this quotation."},
    {"category": "commercial", "service": "common", "order": 3,
     "text": "Quotation validity is as mentioned. Rates beyond validity are subject to revision."},
    {"category": "commercial", "service": "common", "order": 4,
     "text": "Mobilization advance, if applicable, shall be payable before commencement of work."},
    {"category": "commercial", "service": "common", "order": 5,
     "text": "Transportation, loading & unloading shall be charged extra unless explicitly included."},
    {"category": "commercial", "service": "common", "order": 6,
     "text": "All statutory deductions (TDS, GST TDS, etc.) shall be as per applicable law and against valid certificates."},
    {"category": "commercial", "service": "common", "order": 7,
     "text": "Any delay arising out of client-side clearances, permits, or work front shall not be attributable to INDIAN TRADE LINKS."},
    {"category": "commercial", "service": "common", "order": 8,
     "text": "Material shortage, theft, or damage at the client site shall be charged extra at replacement value."},
    {"category": "commercial", "service": "common", "order": 9,
     "text": "Work beyond the quoted scope shall be treated as Extra Work and billed at mutually agreed rates."},
    {"category": "commercial", "service": "common", "order": 10,
     "text": "Final billing shall be on the basis of jointly certified measurement (JMC)."},

    # --- Inclusions · common ---
    {"category": "inclusion", "service": "common", "order": 1, "text": "Manpower as per quoted scope and category."},
    {"category": "inclusion", "service": "common", "order": 2, "text": "Material as per quoted scope and specification."},
    {"category": "inclusion", "service": "common", "order": 3, "text": "Tools, tackles, and consumables required for execution."},
    {"category": "inclusion", "service": "common", "order": 4, "text": "Site supervision by competent personnel."},
    {"category": "inclusion", "service": "common", "order": 5, "text": "Standard safety PPE for own manpower."},
    {"category": "inclusion", "service": "common", "order": 6, "text": "Basic documentation, JMC sheets and progress reports."},

    # --- Exclusions · common ---
    {"category": "exclusion", "service": "common", "order": 1, "text": "Civil work / chipping / grouting / foundation."},
    {"category": "exclusion", "service": "common", "order": 2, "text": "Electrical work / power source / temporary lighting."},
    {"category": "exclusion", "service": "common", "order": 3, "text": "Crane, hydra, JCB, or lifting equipment (unless mentioned)."},
    {"category": "exclusion", "service": "common", "order": 4, "text": "Water and electricity at the work site."},
    {"category": "exclusion", "service": "common", "order": 5, "text": "Client permits / hot work permits / confined space permits / gate passes."},
    {"category": "exclusion", "service": "common", "order": 6, "text": "Accommodation, food & local transport of manpower (unless mentioned)."},
    {"category": "exclusion", "service": "common", "order": 7, "text": "Third-party testing, NDT, or inspection charges."},
    {"category": "exclusion", "service": "common", "order": 8, "text": "Material damage, theft, or loss at client site."},
    {"category": "exclusion", "service": "common", "order": 9, "text": "Statutory fees, octroi, entry tax, or any local levies."},
    {"category": "exclusion", "service": "common", "order": 10, "text": "Standby or idle time charges beyond agreed working hours."},
]


def all_presets_payload() -> Dict:
    """Returned by GET /quotation-builder/presets — used by the frontend."""
    return {
        "services": SERVICES,
        "bases": SERVICE_BASES,
        "basis_labels": BASIS_LABELS,
        "basis_fields": BASIS_FIELDS,
        "preset_items": PRESET_ITEMS,
    }
