"""Admin seed + sample data seeding."""
import os
from datetime import datetime, timezone, timedelta

from core import db, hash_password, verify_password, now_iso, new_id, logger
from approval_engine import build_chain


async def seed_admin():
    admin_email = os.environ.get("ADMIN_EMAIL", "admin@erp.com").lower()
    admin_password = os.environ.get("ADMIN_PASSWORD", "Admin@123")
    existing = await db.users.find_one({"email": admin_email})
    if existing is None:
        await db.users.insert_one({
            "id": new_id(),
            "email": admin_email,
            "name": "Super Admin",
            "role": "super_admin",
            "department": "Executive",
            "phone": "+1-000-0000",
            "password_hash": hash_password(admin_password),
            "created_at": now_iso(),
        })
        logger.info(f"Seeded admin user: {admin_email}")
    elif not verify_password(admin_password, existing["password_hash"]):
        await db.users.update_one({"email": admin_email}, {"$set": {"password_hash": hash_password(admin_password)}})
        logger.info(f"Updated admin password for {admin_email}")


async def seed_sample_data():
    if await db.clients.count_documents({}) > 0:
        return

    admin = await db.users.find_one({"role": "super_admin"}, {"_id": 0, "id": 1})
    creator = admin["id"] if admin else "system"

    def _doc(**fields):
        return {"id": new_id(), "created_at": now_iso(), "created_by": creator, **fields}

    clients = [
        _doc(name="Reliance Industries", code="CL-001", contact="Rajesh Sharma", email="rajesh@reliance.in", phone="+91-9810000001", gst="27AAACR5055K1Z5", address="Mumbai, MH", credit_limit=5000000, status="active"),
        _doc(name="Tata Steel", code="CL-002", contact="Anita Verma", email="anita@tata.in", phone="+91-9810000002", gst="20AAACT2727Q1ZZ", address="Jamshedpur, JH", credit_limit=8000000, status="active"),
        _doc(name="Adani Power", code="CL-003", contact="Vikram Singh", email="vikram@adani.in", phone="+91-9810000003", gst="24AAACA4502R1ZZ", address="Mundra, GJ", credit_limit=6000000, status="active"),
        _doc(name="ONGC", code="CL-004", contact="Suresh Kumar", email="suresh@ongc.co.in", phone="+91-9810000004", gst="07AAACO1598A1ZZ", address="Dehradun, UK", credit_limit=10000000, status="active"),
    ]
    await db.clients.insert_many(clients)

    vendors = [
        _doc(name="SteelTech Supplies", code="VN-001", category="material", contact="Manoj Patel", email="manoj@steeltech.in", phone="+91-9820000001", gst="27AAACS0001A1ZZ", rating=4.5, status="approved"),
        _doc(name="SafetyFirst Equip", code="VN-002", category="ppe", contact="Priya Mehta", email="priya@safetyfirst.in", phone="+91-9820000002", gst="27AAACS0002B1ZZ", rating=4.2, status="approved"),
        _doc(name="PaintMaster Co", code="VN-003", category="paint", contact="Amit Desai", email="amit@paintmaster.in", phone="+91-9820000003", gst="27AAACS0003C1ZZ", rating=4.7, status="approved"),
        _doc(name="RopeAccess Gear", code="VN-004", category="rope_access", contact="Ravi Kapoor", email="ravi@ropegear.in", phone="+91-9820000004", gst="27AAACS0004D1ZZ", rating=4.3, status="pending"),
    ]
    await db.vendors.insert_many(vendors)

    employees = [
        _doc(emp_code="E-1001", name="Arjun Reddy", role="project_manager", department="Operations", phone="+91-9830000001", email="arjun@company.in", joining_date="2022-04-01", salary=120000, status="active"),
        _doc(emp_code="E-1002", name="Sneha Iyer", role="site_engineer", department="Operations", phone="+91-9830000002", email="sneha@company.in", joining_date="2023-01-15", salary=75000, status="active"),
        _doc(emp_code="E-1003", name="Karan Malhotra", role="safety_officer", department="HSE", phone="+91-9830000003", email="karan@company.in", joining_date="2021-08-20", salary=85000, status="active"),
        _doc(emp_code="E-1004", name="Deepa Nair", role="accounts_executive", department="Finance", phone="+91-9830000004", email="deepa@company.in", joining_date="2020-06-10", salary=65000, status="active"),
        _doc(emp_code="E-1005", name="Rohit Sharma", role="supervisor", department="Scaffolding", phone="+91-9830000005", email="rohit@company.in", joining_date="2022-11-05", salary=55000, status="active"),
        _doc(emp_code="E-1006", name="Mohan Lal", role="store_incharge", department="Stores", phone="+91-9830000006", email="mohan@company.in", joining_date="2019-03-12", salary=48000, status="active"),
    ]
    await db.employees.insert_many(employees)

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    attendance = []
    for i, e in enumerate(employees):
        attendance.append(_doc(employee_id=e["id"], employee_name=e["name"], date=today, status="present" if i < 5 else "absent", check_in="09:00", check_out="18:00", hours=9))
    await db.attendance.insert_many(attendance)

    projects = [
        _doc(code="PRJ-2025-01", name="Reliance Jamnagar Scaffolding", client=clients[0]["name"], type="scaffolding", site="Jamnagar, GJ", manager="Arjun Reddy", start_date="2025-11-01", end_date="2026-04-30", budget=12500000, status="active", progress=42),
        _doc(code="PRJ-2025-02", name="Tata Steel Rope Access Inspection", client=clients[1]["name"], type="rope_access", site="Jamshedpur, JH", manager="Arjun Reddy", start_date="2025-12-10", end_date="2026-02-28", budget=4500000, status="active", progress=68),
        _doc(code="PRJ-2025-03", name="Adani Painting Works", client=clients[2]["name"], type="painting", site="Mundra, GJ", manager="Sneha Iyer", start_date="2025-09-15", end_date="2026-01-30", budget=6800000, status="active", progress=85),
        _doc(code="PRJ-2024-09", name="ONGC Roof Sheeting", client=clients[3]["name"], type="roof_sheeting", site="Mumbai High, MH", manager="Sneha Iyer", start_date="2024-08-01", end_date="2025-12-15", budget=8200000, status="completed", progress=100),
        _doc(code="PRJ-2026-01", name="Reliance Shutdown Maintenance", client=clients[0]["name"], type="shutdown", site="Hazira, GJ", manager="Arjun Reddy", start_date="2026-03-01", end_date="2026-05-30", budget=22000000, status="planned", progress=0),
    ]
    await db.projects.insert_many(projects)

    inventory = [
        _doc(code="INV-S001", name="Steel Pipe 48mm", category="scaffolding", uom="meter", quantity=2400, min_stock=500, rate=180, location="Warehouse A"),
        _doc(code="INV-S002", name="Cuplock Standard 2m", category="scaffolding", uom="nos", quantity=320, min_stock=400, rate=950, location="Warehouse A"),
        _doc(code="INV-P001", name="Industrial Paint - Grey 20L", category="painting", uom="can", quantity=85, min_stock=30, rate=4200, location="Warehouse B"),
        _doc(code="INV-R001", name="Rope Access Harness", category="rope_access", uom="nos", quantity=42, min_stock=20, rate=8500, location="Warehouse C"),
        _doc(code="INV-PPE001", name="Safety Helmet Class A", category="ppe", uom="nos", quantity=210, min_stock=100, rate=450, location="Warehouse C"),
        _doc(code="INV-PPE002", name="Safety Harness Full Body", category="ppe", uom="nos", quantity=18, min_stock=50, rate=3200, location="Warehouse C"),
        _doc(code="INV-RS001", name="GI Roof Sheet 0.5mm", category="roof_sheeting", uom="sqm", quantity=4500, min_stock=1000, rate=620, location="Warehouse D"),
    ]
    await db.inventory.insert_many(inventory)

    purchase_orders = [
        _doc(po_number="PO-2026-001", vendor=vendors[0]["name"], project=projects[0]["name"], date="2026-01-12", total=485000, status="approved", paid=False, items=[]),
        _doc(po_number="PO-2026-002", vendor=vendors[1]["name"], project=projects[1]["name"], date="2026-01-20", total=128000, status="pending", paid=False, items=[]),
        _doc(po_number="PO-2026-003", vendor=vendors[2]["name"], project=projects[2]["name"], date="2026-02-01", total=315000, status="approved", paid=True, items=[]),
        _doc(po_number="PO-2026-004", vendor=vendors[3]["name"], project=projects[1]["name"], date="2026-02-05", total=72000, status="draft", paid=False, items=[]),
    ]
    await db.purchase_orders.insert_many(purchase_orders)

    quotations = [
        _doc(quote_number="QT-2026-001", client=clients[0]["name"], project="Hazira Maintenance", date="2026-01-25", valid_until="2026-02-25", total=1850000, status="sent", items=[]),
        _doc(quote_number="QT-2026-002", client=clients[1]["name"], project="Plant 2 Inspection", date="2026-02-02", valid_until="2026-03-02", total=620000, status="invoiced", items=[]),
        _doc(quote_number="QT-2026-003", client=clients[2]["name"], project="External Painting Q2", date="2026-02-08", valid_until="2026-03-08", total=1240000, status="draft", items=[]),
    ]
    await db.quotations.insert_many(quotations)

    je_rows = []
    base = datetime.now(timezone.utc).replace(day=15)
    rev_amounts = [3200000, 4100000, 3800000, 5200000, 4600000, 5800000]
    exp_amounts = [2100000, 2400000, 2300000, 3100000, 2800000, 3400000]
    for i in range(6):
        d = (base - timedelta(days=30 * (5 - i))).strftime("%Y-%m-%d")
        je_rows.append(_doc(je_number=f"JE-{i+1:04d}", date=d, type="revenue", account="Project Revenue", amount=rev_amounts[i], narration="Client billing", cost_centre="Operations"))
        je_rows.append(_doc(je_number=f"JE-E{i+1:04d}", date=d, type="expense", account="Materials & Labor", amount=exp_amounts[i], narration="Operational expenses", cost_centre="Operations"))
    await db.journal_entries.insert_many(je_rows)

    safety_reports = [
        _doc(report_id="SR-001", date="2026-02-04", project=projects[0]["name"], type="near_miss", severity="medium", description="Tool dropped from height-3 platform; barricade intact", reporter="Karan Malhotra", status="open"),
        _doc(report_id="SR-002", date="2026-02-08", project=projects[1]["name"], type="observation", severity="low", description="PPE compliance reminder for new crew", reporter="Karan Malhotra", status="closed"),
        _doc(report_id="SR-003", date="2026-02-10", project=projects[2]["name"], type="incident", severity="high", description="Minor injury — finger pinch during scaffold dismantle", reporter="Rohit Sharma", status="under_review"),
    ]
    await db.safety_reports.insert_many(safety_reports)

    assets = [
        _doc(asset_id="AST-001", name="Scissor Lift 12m", category="equipment", purchase_date="2022-05-10", cost=2850000, location="Yard 1", assigned_to=projects[0]["name"], status="in_use", depreciation_rate=15),
        _doc(asset_id="AST-002", name="Air Compressor 7HP", category="equipment", purchase_date="2023-02-18", cost=185000, location="Yard 2", assigned_to=projects[2]["name"], status="in_use", depreciation_rate=20),
        _doc(asset_id="AST-003", name="Welding Machine Inverter", category="equipment", purchase_date="2024-08-22", cost=78000, location="Stores", assigned_to=None, status="available", depreciation_rate=20),
    ]
    await db.assets.insert_many(assets)

    payroll = []
    pay_month = datetime.now(timezone.utc).strftime("%Y-%m")
    for e in employees:
        gross = e["salary"]
        deductions = round(gross * 0.12, 2)
        net = round(gross - deductions, 2)
        payroll.append(_doc(employee_id=e["id"], employee_name=e["name"], month=pay_month, gross=gross, deductions=deductions, net=net, status="processed"))
    await db.payroll.insert_many(payroll)

    vehicles = [
        _doc(reg_number="MH-12-AB-1234", type="truck", capacity="5T", driver="Suresh Yadav", status="active", last_service="2026-01-15", fuel_avg=4.2),
        _doc(reg_number="MH-04-CD-5678", type="pickup", capacity="1T", driver="Ramesh Kumar", status="active", last_service="2026-02-01", fuel_avg=9.8),
        _doc(reg_number="GJ-01-EF-9012", type="crane", capacity="20T", driver="Sanjay Patil", status="maintenance", last_service="2026-02-08", fuel_avg=2.1),
    ]
    await db.vehicles.insert_many(vehicles)

    documents = [
        _doc(doc_id="DOC-001", title="Master Service Agreement - Reliance", category="contract", project=projects[0]["name"], uploaded_by="Admin", expiry="2027-03-31", version="1.0"),
        _doc(doc_id="DOC-002", title="ISO 45001 Certification", category="certification", project=None, uploaded_by="Admin", expiry="2026-09-30", version="2.0"),
        _doc(doc_id="DOC-003", title="Scaffold Design Drawings - Jamnagar", category="drawing", project=projects[0]["name"], uploaded_by="Arjun Reddy", expiry=None, version="3.2"),
    ]
    await db.documents.insert_many(documents)

    approvals = [
        _doc(title="PO-2026-002 Approval", type="purchase_order", reference="PO-2026-002", amount=128000, requested_by="Rohit Sharma", chain=build_chain("purchase_order"), current_step=0, history=[], status="pending"),
        _doc(title="Leave Request - Sneha Iyer", type="leave", reference="LV-2026-008", amount=0, requested_by="Sneha Iyer", chain=build_chain("leave"), current_step=0, history=[], status="pending"),
        _doc(title="Capex - New Welding Machine", type="capex", reference="CAP-2026-001", amount=92000, requested_by="Mohan Lal", chain=build_chain("capex"), current_step=0, history=[], status="pending"),
    ]
    await db.approvals.insert_many(approvals)

    logger.info("Seeded sample ERP data.")
