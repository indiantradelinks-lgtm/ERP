"""Seed category-wise standard item master lists. Idempotent — safe to re-run (inserts only missing codes)."""
import asyncio
import os
import sys
import uuid
from datetime import datetime, timezone

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

NEW_CATEGORIES = [
    {"code": "ITM", "name": "IT Items", "sub_categories": ["Computers", "Printers", "Networking", "Accessories"]},
    {"code": "FUR", "name": "Office Furniture", "sub_categories": ["Chairs", "Tables", "Storage"]},
]

# (name, uom, min_stock)
ITEMS = {
    "Scaffolding Material": [
        ("MS Scaffolding Pipe 6.0 Mtr", "Nos", 50), ("MS Scaffolding Pipe 5.0 Mtr", "Nos", 50),
        ("MS Scaffolding Pipe 4.0 Mtr", "Nos", 50), ("MS Scaffolding Pipe 3.0 Mtr", "Nos", 50),
        ("MS Scaffolding Pipe 2.0 Mtr", "Nos", 30), ("MS Scaffolding Pipe 1.5 Mtr", "Nos", 30),
        ("MS Scaffolding Pipe 1.0 Mtr", "Nos", 30), ("Fixed Coupler (Right Angle)", "Nos", 200),
        ("Swivel Coupler", "Nos", 200), ("Sleeve Coupler (Joint)", "Nos", 100),
        ("Putlog / Board Clamp", "Nos", 100), ("Beam Clamp (Girder Coupler)", "Nos", 50),
        ("Base Plate 150x150mm", "Nos", 50), ("Adjustable Base Jack", "Nos", 50),
        ("Adjustable U-Head Jack", "Nos", 50), ("Joint Pin (Spigot)", "Nos", 100),
        ("Scaffold Wooden Board 6ft", "Nos", 50), ("Steel Plank / Metal Deck 2 Mtr", "Nos", 50),
        ("Steel Plank / Metal Deck 3 Mtr", "Nos", 50), ("Toe Board 2 Mtr", "Nos", 30),
        ("Scaffold Steel Ladder 6 Mtr", "Nos", 10), ("Aluminium Ladder 12ft", "Nos", 5),
        ("Ladder Clamp", "Nos", 40), ("Caster Wheel with Brake 8 inch", "Nos", 16),
        ("Cuplock Vertical 3.0 Mtr", "Nos", 40), ("Cuplock Ledger 1.8 Mtr", "Nos", 40),
        ("Adjustable Prop Jack 3.6 Mtr", "Nos", 20), ("Tie Rod with Wing Nut", "Nos", 30),
        ("Safety Net 10x10 Mtr", "Nos", 10), ("Green Shade Net Roll 3x50 Mtr", "Roll", 5),
        ("Scaff Tag with Holder", "Nos", 100), ("Manila Rope 24mm", "Mtr", 200),
        ("GI Binding Wire", "Kg", 50),
    ],
    "PPE and Safety Items": [
        ("Safety Helmet with Ratchet", "Nos", 50), ("Helmet Chin Strap", "Nos", 100),
        ("Safety Shoes (Steel Toe)", "Pair", 30), ("Gum Boots", "Pair", 10),
        ("Full Body Harness with Double Lanyard", "Nos", 30), ("Energy Absorber Lanyard", "Nos", 20),
        ("Work Positioning Belt", "Nos", 10), ("Cotton Knitted Hand Gloves", "Pair", 200),
        ("Leather Hand Gloves", "Pair", 100), ("Cut-Resistant Gloves Level 5", "Pair", 50),
        ("Nitrile Coated Gloves", "Pair", 100), ("Electrical Rubber Gloves 11KV", "Pair", 5),
        ("Safety Goggles Clear", "Nos", 50), ("Safety Goggles Dark (Welding)", "Nos", 20),
        ("Face Shield with Bracket", "Nos", 20), ("Welding Face Shield", "Nos", 10),
        ("Ear Plug (Corded)", "Pair", 200), ("Ear Muff", "Nos", 20),
        ("Dust Mask (Disposable)", "Nos", 500), ("Half Face Respirator", "Nos", 20),
        ("Respirator Filter Cartridge", "Pair", 40), ("Reflective Safety Jacket", "Nos", 50),
        ("Fire Retardant Coverall", "Nos", 20), ("Cotton Boiler Suit", "Nos", 30),
        ("Rain Coat / Rain Suit", "Nos", 20), ("Rope Grab Fall Arrester", "Nos", 20),
        ("Retractable Fall Arrester Block 6 Mtr", "Nos", 5), ("Anchorage Webbing Sling 1.5 Mtr", "Nos", 30),
        ("Screw Lock Karabiner", "Nos", 50), ("Vertical Life Line Rope 16mm PP", "Mtr", 300),
        ("First Aid Kit (Site Type)", "Set", 5), ("Fire Extinguisher ABC 4.5 Kg", "Nos", 10),
        ("Fire Extinguisher CO2 4.5 Kg", "Nos", 5), ("Safety Signage Board", "Nos", 30),
        ("Barricading Tape Roll 250 Mtr", "Roll", 20), ("Barricading Net Roll 50 Mtr", "Roll", 10),
    ],
    "Roof Sheeting Material": [
        ("Colour Coated Profile Sheet 0.50mm", "SqMtr", 100), ("Galvalume Bare Sheet 0.47mm", "SqMtr", 100),
        ("GI Plain Sheet 0.8mm", "SqMtr", 50), ("Polycarbonate Sheet 2mm", "SqMtr", 30),
        ("Ridge Cap (Plain)", "Mtr", 50), ("North Light Curve", "Nos", 20),
        ("Apron / Corner Flashing", "Mtr", 50), ("Rainwater Gutter 600mm Girth", "Mtr", 30),
        ("Barge Board", "Mtr", 30), ("Self Drilling Screw 25mm with EPDM", "Nos", 2000),
        ("Self Drilling Screw 55mm with EPDM", "Nos", 2000), ("Self Drilling Screw 75mm with EPDM", "Nos", 1000),
        ("J / L Hook Bolt with Washer", "Nos", 500), ("EPDM Bonded Washer 19mm", "Nos", 2000),
        ("Foam Filler (Profile)", "Mtr", 100), ("Butyl Sealant Tape Roll", "Roll", 20),
        ("Silicone Sealant Cartridge 280ml", "Nos", 24), ("Turbo Ventilator 24 inch with Base", "Nos", 5),
        ("Aluminium Louver", "Nos", 10), ("Aluminium Blind Rivet 4x12mm", "Nos", 2000),
        ("Down Take Pipe PVC 110mm", "Mtr", 30),
    ],
    "Consumables": [
        ("Welding Electrode E6013 (3.15mm)", "Kg", 50), ("Welding Electrode E7018 (3.15mm)", "Kg", 50),
        ("Cutting Wheel 4 inch", "Nos", 100), ("Cutting Wheel 14 inch (Chop Saw)", "Nos", 30),
        ("Grinding Wheel 4 inch", "Nos", 100), ("Grinding Wheel 7 inch", "Nos", 50),
        ("Flap Disc 4 inch 80 Grit", "Nos", 50), ("Wire Brush (Hand)", "Nos", 30),
        ("Emery Paper 80 Grit", "Nos", 100), ("Hacksaw Blade 12 inch", "Nos", 50),
        ("HSS Drill Bit Set 1-13mm", "Set", 5), ("Masonry Drill Bit 10mm", "Nos", 20),
        ("Binding Wire 18G", "Kg", 100), ("Cotton Waste (Cleaning)", "Kg", 50),
        ("Masking Tape 1 inch", "Nos", 50), ("PTFE / Teflon Tape", "Nos", 50),
        ("Insulation Tape (Electrical)", "Nos", 50), ("WD-40 Spray 400ml", "Nos", 12),
        ("Multipurpose Grease", "Kg", 20), ("Engine Oil 20W-40", "Ltr", 20),
        ("Diesel (HSD)", "Ltr", 200), ("Petrol", "Ltr", 50),
        ("Oxygen Cylinder Refill", "Nos", 4), ("DA / Acetylene Cylinder Refill", "Nos", 2),
        ("LPG Cylinder Commercial 19 Kg", "Nos", 2), ("Anti-Spatter Spray", "Nos", 12),
        ("Marking Chalk / Crayon", "Nos", 50), ("Permanent Marker", "Nos", 24),
    ],
    "Painting Material": [
        ("Red Oxide Zinc Chromate Primer", "Ltr", 100), ("Zinc Phosphate Primer", "Ltr", 100),
        ("Epoxy Zinc Rich Primer", "Ltr", 50), ("Epoxy MIO Intermediate Coat", "Ltr", 50),
        ("Epoxy Finish Paint", "Ltr", 100), ("PU Finish Paint", "Ltr", 100),
        ("Synthetic Enamel Paint", "Ltr", 50), ("Aluminium Paint (Heat Resistant)", "Ltr", 30),
        ("GP Thinner", "Ltr", 100), ("Epoxy Thinner", "Ltr", 50),
        ("PU Thinner", "Ltr", 50), ("Paint Brush 2 inch", "Nos", 50),
        ("Paint Brush 4 inch", "Nos", 50), ("Paint Roller 9 inch with Handle", "Nos", 30),
        ("Roller Refill 9 inch", "Nos", 50), ("Putty Knife 3 inch", "Nos", 20),
        ("Sand Paper 120 Grit", "Nos", 100), ("Paint Tray", "Nos", 20),
        ("Paint Mixing Paddle", "Nos", 10), ("Empty Bucket 20 Ltr", "Nos", 20),
    ],
    "Rope Access Equipment": [
        ("Static Kernmantle Rope 11mm", "Mtr", 500), ("Dynamic Rope 10.5mm", "Mtr", 100),
        ("Descender (ID / Stop)", "Nos", 10), ("Hand Ascender (Jumar)", "Nos", 10),
        ("Chest Ascender (Croll)", "Nos", 10), ("Foot Loop / Footape", "Nos", 10),
        ("Rope Access Sit Harness", "Nos", 10), ("Work Seat (Bosun Chair)", "Nos", 8),
        ("Rope Access Helmet (Chin Strap)", "Nos", 12), ("Triple Lock Karabiner", "Nos", 30),
        ("Back-up Device (ASAP)", "Nos", 10), ("Rope Protector Sleeve", "Nos", 20),
        ("Anchor Sling 120cm Dyneema", "Nos", 20), ("Single Pulley (Fixed)", "Nos", 8),
        ("Rope Kit Bag 40 Ltr", "Nos", 8),
    ],
    "Tools and Tackles": [
        ("Angle Grinder 4 inch (AG4)", "Nos", 10), ("Angle Grinder 7 inch (AG7)", "Nos", 5),
        ("Electric Drill Machine 13mm", "Nos", 5), ("Hammer Drill / Rotary Hammer", "Nos", 3),
        ("Welding Machine 400A (ARC)", "Nos", 3), ("Chop Saw Machine 14 inch", "Nos", 2),
        ("Chipping Hammer", "Nos", 10), ("Ball Peen Hammer 1 Kg", "Nos", 10),
        ("Sledge Hammer 5 Kg", "Nos", 5), ("Double Ended Spanner Set 6-32mm", "Set", 5),
        ("Ring Spanner Set 6-32mm", "Set", 5), ("Pipe Wrench 24 inch", "Nos", 5),
        ("Adjustable Wrench 12 inch", "Nos", 5), ("Screwdriver Set (6 Pc)", "Set", 5),
        ("Combination Plier 8 inch", "Nos", 10), ("Allen Key Set (mm)", "Set", 5),
        ("Measuring Tape 5 Mtr", "Nos", 20), ("Measuring Tape 30 Mtr", "Nos", 5),
        ("Spirit Level 600mm", "Nos", 5), ("Chain Pulley Block 1 Ton", "Nos", 4),
        ("Chain Pulley Block 3 Ton", "Nos", 2), ("D-Shackle 2 Ton", "Nos", 20),
        ("Wire Rope Sling 12mm x 2 Mtr", "Nos", 10), ("Webbing Sling 2 Ton x 2 Mtr", "Nos", 20),
        ("Ratchet Tie Down / Lashing Belt 5 Ton", "Nos", 10), ("Torque Wrench 1/2 inch", "Nos", 2),
        ("Bench Vice 6 inch", "Nos", 2), ("Hydraulic Jack 10 Ton", "Nos", 2),
        ("Crow Bar 1.5 Mtr", "Nos", 5), ("Bolt Cutter 24 inch", "Nos", 2),
        ("Heat Gun 2000W", "Nos", 2), ("Extension Board 30 Mtr (3 Core)", "Nos", 10),
    ],
    "Machinery and Equipment": [
        ("Air Compressor 250 CFM", "Nos", 1), ("DG Set 62.5 KVA", "Nos", 1),
        ("Airless Spray Painting Machine", "Nos", 2), ("Grit Blasting Pot 200 Ltr", "Nos", 2),
        ("Bar Bending Machine", "Nos", 1), ("Bar Cutting Machine", "Nos", 1),
        ("Concrete Mixer 10/7 CFT", "Nos", 1), ("Water Pump 2 inch (Diesel)", "Nos", 2),
        ("Monkey Hoist / Winch Machine 500 Kg", "Nos", 2), ("Passenger cum Material Hoist", "Nos", 1),
        ("Boom Lift 45 ft", "Nos", 1), ("Scissor Lift 19 ft", "Nos", 1),
        ("Welding Generator 500A (Diesel)", "Nos", 1), ("Plate Compactor", "Nos", 1),
        ("High Pressure Washer", "Nos", 1),
    ],
    "Vehicle/Logistics Items": [
        ("Hydra Crane 14 Ton", "Nos", 1), ("Pickup Truck (Bolero/DI)", "Nos", 1),
        ("Mini Truck (Tata Ace)", "Nos", 1), ("Truck 10 Wheeler", "Nos", 1),
        ("Flatbed Trailer 40 ft", "Nos", 1), ("Tractor with Trolley", "Nos", 1),
        ("Forklift 3 Ton", "Nos", 1), ("Diesel Bowser 2 KL", "Nos", 1),
        ("Tool Van / Service Van", "Nos", 1), ("Site Ambulance", "Nos", 1),
    ],
    "Office/Administrative Items": [
        ("A4 Copier Paper Ream 75 GSM", "Ream", 20), ("Printer Toner Cartridge", "Nos", 4),
        ("Ball Pen (Blue)", "Nos", 100), ("Notebook / Register 200 Pages", "Nos", 20),
        ("Box File / Lever Arch File", "Nos", 30), ("Stapler with Pins No.10", "Nos", 10),
        ("Punching Machine (Double Hole)", "Nos", 5), ("Whiteboard 4x3 ft", "Nos", 3),
        ("Whiteboard Marker", "Nos", 24), ("Calculator 12 Digit", "Nos", 5),
        ("Attendance Register", "Nos", 10), ("Envelope A4 (Laminated)", "Nos", 100),
        ("Sticky Notes 3x3", "Nos", 30), ("Scissors 8 inch", "Nos", 5),
        ("Cello Tape 2 inch Roll", "Roll", 30),
    ],
    "IT Items": [
        ("Desktop Computer (i5/16GB/512SSD)", "Nos", 1), ("Laptop (i5/16GB/512SSD)", "Nos", 1),
        ("Monitor 24 inch LED", "Nos", 2), ("USB Keyboard", "Nos", 5),
        ("USB Mouse", "Nos", 5), ("Laser Printer (Mono)", "Nos", 1),
        ("All-in-One Printer (Print/Scan/Copy)", "Nos", 1), ("UPS 1 KVA", "Nos", 2),
        ("WiFi Router (Dual Band)", "Nos", 2), ("Network Switch 8 Port Gigabit", "Nos", 2),
        ("LAN Cable Cat6", "Mtr", 100), ("External Hard Disk 1 TB", "Nos", 2),
        ("Pen Drive 64 GB", "Nos", 5), ("HD Webcam", "Nos", 2),
    ],
    "Office Furniture": [
        ("Executive Office Chair", "Nos", 2), ("Visitor Chair", "Nos", 4),
        ("Office Table 5x2.5 ft", "Nos", 2), ("Workstation Desk (Modular)", "Nos", 4),
        ("Conference Table 8 Seater", "Nos", 1), ("Steel Almirah (Full Height)", "Nos", 2),
        ("File Cabinet 4 Drawer", "Nos", 2), ("Book Shelf / Rack", "Nos", 2),
        ("Sofa 3 Seater (Reception)", "Nos", 1), ("Plastic Chair", "Nos", 20),
        ("Folding Table 6x2 ft", "Nos", 4),
    ],
}

CODE_PREFIX = {
    "Scaffolding Material": "SCF", "PPE and Safety Items": "PPE", "Roof Sheeting Material": "RSM",
    "Consumables": "CON", "Painting Material": "PNT", "Rope Access Equipment": "RAE",
    "Tools and Tackles": "TLT", "Machinery and Equipment": "MEQ", "Vehicle/Logistics Items": "VEH",
    "Office/Administrative Items": "OFA", "IT Items": "ITM", "Office Furniture": "FUR",
}


async def main():
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    now = datetime.now(timezone.utc).isoformat()

    cats_added = 0
    for cat in NEW_CATEGORIES:
        existing = await db.inv_categories.find_one({"name": cat["name"]})
        if not existing:
            await db.inv_categories.insert_one({
                "id": str(uuid.uuid4()), "code": cat["code"], "name": cat["name"],
                "sub_categories": cat["sub_categories"], "active": True,
                "created_by": "seed_item_master", "created_at": now,
            })
            cats_added += 1

    items_added, items_skipped = 0, 0
    for category, items in ITEMS.items():
        prefix = CODE_PREFIX[category]
        for idx, (name, uom, min_stock) in enumerate(items, start=1):
            code = f"{prefix}-{idx:03d}"
            doc = {
                "id": str(uuid.uuid4()), "code": code, "name": name, "category": category,
                "uom": uom, "unit": uom, "quantity": 0, "rate": 0, "min_stock": min_stock,
                "location": "Main Store", "created_by": "seed_item_master", "created_at": now,
            }
            res = await db.inventory.update_one({"code": code}, {"$setOnInsert": doc}, upsert=True)
            if res.upserted_id:
                items_added += 1
            else:
                items_skipped += 1

    total = await db.inventory.count_documents({})
    print(f"Categories added: {cats_added} | Items inserted: {items_added} | Already existed (skipped): {items_skipped} | Total items now: {total}")


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
