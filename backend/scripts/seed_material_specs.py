"""Fill standard material specifications on seeded item master (by code). Idempotent — only sets missing fields."""
import asyncio
import os
import sys

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

# code: (unit_weight_kg, size, material_spec, material_type, grade, hsn_code)
SPECS = {
    # Scaffolding — pipes IS 1161 YSt 240, 48.3 OD x 3.2mm, 3.56 kg/m
    "SCF-001": (21.4, "48.3 OD x 3.2 mm x 6.0 M", "IS 1161", "ERW Steel Tube", "YSt 240", "7306"),
    "SCF-002": (17.8, "48.3 OD x 3.2 mm x 5.0 M", "IS 1161", "ERW Steel Tube", "YSt 240", "7306"),
    "SCF-003": (14.2, "48.3 OD x 3.2 mm x 4.0 M", "IS 1161", "ERW Steel Tube", "YSt 240", "7306"),
    "SCF-004": (10.7, "48.3 OD x 3.2 mm x 3.0 M", "IS 1161", "ERW Steel Tube", "YSt 240", "7306"),
    "SCF-005": (7.1, "48.3 OD x 3.2 mm x 2.0 M", "IS 1161", "ERW Steel Tube", "YSt 240", "7306"),
    "SCF-006": (5.3, "48.3 OD x 3.2 mm x 1.5 M", "IS 1161", "ERW Steel Tube", "YSt 240", "7306"),
    "SCF-007": (3.6, "48.3 OD x 3.2 mm x 1.0 M", "IS 1161", "ERW Steel Tube", "YSt 240", "7306"),
    "SCF-008": (1.1, "48.3 x 48.3 mm", "IS 2306 / BS 1139", "Drop Forged Steel", "Class 1", "7308"),
    "SCF-009": (1.3, "48.3 x 48.3 mm", "IS 2306 / BS 1139", "Drop Forged Steel", "Class 1", "7308"),
    "SCF-010": (1.0, "48.3 mm (internal joint)", "IS 2306 / BS 1139", "Drop Forged Steel", "Class 1", "7308"),
    "SCF-011": (0.75, "48.3 mm single lug", "BS 1139", "Pressed Steel", "-", "7308"),
    "SCF-012": (1.8, "48.3 mm x flange grip", "BS 1139", "Drop Forged Steel", "-", "7308"),
    "SCF-013": (1.1, "150 x 150 x 6 mm", "IS 2062", "MS Plate", "E250", "7308"),
    "SCF-014": (3.5, "38 mm sq. x 600 mm spindle", "IS 2062 / IS 4014", "MS with Cast Nut", "-", "7308"),
    "SCF-015": (4.2, "38 mm sq. x 600 mm + U-head 150 mm", "IS 2062", "MS with Cast Nut", "-", "7308"),
    "SCF-016": (0.8, "38 OD x 300 mm", "IS 1161", "MS Tube Spigot", "-", "7308"),
    "SCF-017": (12.0, "225 x 38 mm x 6 ft", "IS 883", "Seasoned Sal Wood", "Grade 1", "4418"),
    "SCF-018": (13.5, "225 x 38 mm x 2.0 M, galvanized", "EN 12811", "Pre-galvanized Steel", "-", "7308"),
    "SCF-019": (20.0, "225 x 38 mm x 3.0 M, galvanized", "EN 12811", "Pre-galvanized Steel", "-", "7308"),
    "SCF-020": (7.0, "225 x 25 mm x 2.0 M", "IS 2062", "MS / Wood", "-", "7308"),
    "SCF-021": (24.0, "450 mm wide x 6.0 M", "IS 2062", "MS Tube Welded", "-", "7308"),
    "SCF-022": (11.5, "450 mm wide x 12 ft", "IS 3696", "Aluminium Alloy", "HE-30", "7616"),
    "SCF-023": (0.9, "48.3 mm x board grip", "BS 1139", "Pressed Steel", "-", "7308"),
    "SCF-024": (4.5, "200 mm (8 in) with brake", "IS 7167", "Cast Iron + Rubber", "500 kg SWL", "8302"),
    "SCF-025": (17.5, "48.3 OD x 3.2 mm x 3.0 M with cups", "EN 74 / IS 1161", "ERW Steel + Forged Cups", "YSt 240", "7308"),
    "SCF-026": (9.5, "48.3 OD x 3.2 mm x 1.8 M with blades", "EN 74 / IS 1161", "ERW Steel", "YSt 240", "7308"),
    "SCF-027": (14.0, "Dia 40/48 mm, 2.0-3.6 M adjustable", "IS 4014", "MS Prop", "Class B", "7308"),
    "SCF-028": (1.2, "16 mm dia x 1.0 M with wing nut", "IS 2062", "MS Rod Threaded", "-", "7318"),
    "SCF-029": (6.0, "10 x 10 M, 60 gsm mesh", "IS 5175", "HDPE Knotless", "-", "5608"),
    "SCF-030": (9.0, "3 x 50 M roll, 75% shade", "IS 16008", "HDPE Monofilament", "-", "5608"),
    "SCF-031": (0.05, "160 x 90 mm tag + holder", "-", "PVC / ABS", "-", "3926"),
    "SCF-032": (0.35, "24 mm dia (per M)", "IS 1084", "Manila Natural Fibre", "3 Strand", "5607"),
    "SCF-033": (1.0, "18 SWG (per Kg)", "IS 280", "GI Soft Annealed", "-", "7217"),
    # PPE — key items
    "PPE-001": (0.38, "One size, ratchet 53-62 cm", "IS 2925 / EN 397", "HDPE Shell", "Type I", "6506"),
    "PPE-003": (0.9, "Sizes 6-11, steel toe 200 J", "IS 15298 Part 2", "Leather + PU Sole", "S1", "6403"),
    "PPE-004": (1.6, "Sizes 7-11, 13 in height", "IS 12254", "PVC Moulded", "-", "6401"),
    "PPE-005": (1.8, "Universal, dorsal + sternal D-ring", "IS 3521 / EN 361", "Polyester Webbing 44 mm", "Class A", "6307"),
    "PPE-006": (1.2, "2.0 M twin tail with shock absorber", "EN 355", "Polyamide Rope 12 mm", "-", "5609"),
    "PPE-017": (0.01, "Universal, SNR 25 dB", "IS 9167 / EN 352-2", "PU Foam Corded", "-", "3926"),
    "PPE-019": (0.02, "FFP1/FFP2 disposable", "IS 9473 / EN 149", "Non-woven Melt-blown", "FFP2", "6307"),
    "PPE-022": (0.25, "L/XL, 2 in reflective tape", "EN ISO 20471", "Polyester Mesh 120 gsm", "Class 2", "6110"),
    "PPE-026": (0.85, "For 14-16 mm rope, auto-lock", "EN 353-2", "SS 304 / Alu Alloy", "-", "7326"),
    "PPE-030": (0.2, "16 mm dia 3-strand (per M)", "IS 4082 / EN 1891", "Polypropylene / Polyamide", "-", "5607"),
    "PPE-032": (7.5, "ABC Dry Powder, 4.5 Kg, wall mount", "IS 15683", "MS Cylinder Powder", "2A:21B", "8424"),
    # Roof sheeting — key items
    "RSM-001": (4.5, "0.50 mm TCT x 1090 mm cover (per SqM)", "IS 15965 / ASTM A792", "Colour Coated Galvalume", "AZ150, 550 MPa", "7210"),
    "RSM-002": (4.2, "0.47 mm TCT x 1090 mm cover (per SqM)", "ASTM A792", "Bare Galvalume", "AZ150", "7210"),
    "RSM-010": (0.006, "5.5 x 25 mm with EPDM washer", "AS 3566 Class 3", "Carbon Steel Zinc Plated", "Class 3", "7318"),
    "RSM-011": (0.009, "5.5 x 55 mm with EPDM washer", "AS 3566 Class 3", "Carbon Steel Zinc Plated", "Class 3", "7318"),
    "RSM-017": (0.4, "280 ml cartridge, neutral cure", "ASTM C920", "Silicone Neutral Cure", "Class 25", "3214"),
    "RSM-018": (10.0, "600 mm (24 in) throat with base plate", "-", "Aluminium / SS 304", "-", "8414"),
    # Consumables — key items
    "CON-001": (1.0, "3.15 x 350 mm (per Kg ~ 28 pcs)", "IS 814 / AWS E6013", "Rutile Coated MS", "E6013", "8311"),
    "CON-002": (1.0, "3.15 x 350 mm (per Kg ~ 26 pcs)", "IS 814 / AWS E7018", "Low Hydrogen Iron Powder", "E7018", "8311"),
    "CON-003": (0.04, "100 x 1.2 x 16 mm", "EN 12413", "Aluminium Oxide Resinoid", "A60", "6804"),
    "CON-005": (0.06, "100 x 6 x 16 mm", "EN 12413", "Aluminium Oxide Resinoid", "A24", "6804"),
    "CON-013": (1.0, "18 SWG annealed (per Kg)", "IS 280", "MS Soft Annealed", "-", "7217"),
    # Painting — key items
    "PNT-001": (1.4, "Per Ltr, DFT 35-40 micron", "IS 2074", "Alkyd Zinc Chromate", "-", "3208"),
    "PNT-003": (1.4, "Per Ltr, 65-75% zinc in dry film", "IS 14589 / SSPC Paint 20", "Epoxy Zinc Rich", "Level 2", "3208"),
    "PNT-005": (1.4, "Per Ltr, DFT 100-125 micron", "IS 13213", "Epoxy Polyamide 2-pack", "-", "3208"),
    "PNT-006": (1.3, "Per Ltr, DFT 40-50 micron", "IS 13213", "Aliphatic Polyurethane 2-pack", "-", "3208"),
}


async def main():
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    updated = 0
    for code, (wt, size, spec, mtype, grade, hsn) in SPECS.items():
        patch = {}
        item = await db.inventory.find_one({"code": code}, {"_id": 0})
        if not item:
            continue
        for k, v in [("unit_weight_kg", wt), ("size", size), ("material_spec", spec),
                     ("material_type", mtype), ("grade", grade), ("hsn_code", hsn)]:
            if v not in (None, "", "-") and not item.get(k):
                patch[k] = v
        if patch:
            await db.inventory.update_one({"code": code}, {"$set": patch})
            updated += 1
    print(f"Specs filled on {updated} items ({len(SPECS)} in spec library)")


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
