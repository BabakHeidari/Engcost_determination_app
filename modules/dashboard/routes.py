from flask import Blueprint, render_template, jsonify
from utils.auth import login_required
from utils.load_data import load_json
from utils.paths import product_path

dashboard_bp = Blueprint("dashboard", __name__)

@dashboard_bp.route("/dashboard")
@login_required
def dashboard():
    dashboard_data = {"kpis": {
        "revenue": 1250000000,
        "cost": 870000000,
        "profit": 380000000,
        "margin": 30.4
    },
    "monthly": [
        { "month": "2025-02", "revenue": 1100, "cost": 720 },
        { "month": "2025-03", "revenue": 1250, "cost": 870 },
        { "month": "2025-01", "revenue": 900, "cost": 650 },
    ],
    "factories": [
        { "name": "Factory B", "cost": 300 },
        { "name": "Factory C", "cost": 150 },
        { "name": "Factory A", "cost": 420 },
    ]}

    products = load_json(product_path+".json")
    filter_options = {
        "factories": ["Plant Alpha", "Plant Beta", "Plant Gamma"],
        "categories": ["Cathode", "Anode", "Electrolyte", "Separator", "Packaging"]
    }

    return render_template("dashboard/dashboard.html",
                           filter_options=filter_options)

@dashboard_bp.route("/api/cost_analysis")
@login_required
def cost_analysis():

    data = {
    "kpis": {
        "total_cost": 1256000.00,
        "avg_cost_per_product": 83733.33,
        "product_count": 15,
        "top_cost_driver": "Cathode - NMC 811"
    },
    "breakdown_by_category": [
        { "name": "Cathode", "cost": 520000 },
        { "name": "Anode", "cost": 310000 },
        { "name": "Electrolyte", "cost": 185000 },
        { "name": "Separator", "cost": 141000 },
        { "name": "Packaging", "cost": 100000 }
    ],
    "breakdown_by_subcategory": [
        { "name": "NMC 811", "cost": 280000 },
        { "name": "LFP", "cost": 240000 },
        { "name": "Graphite", "cost": 180000 },
        { "name": "Silicon", "cost": 130000 },
        { "name": "LiPF6", "cost": 120000 },
        { "name": "Polymer", "cost": 95000 },
        { "name": "Polyolefin", "cost": 85000 },
        { "name": "Ceramic Coated", "cost": 56000 },
        { "name": "Aluminum Case", "cost": 60000 },
        { "name": "Plastic Wrap", "cost": 40000 }
    ],
    "detail_breakdown": [
        {
        "factory": "Plant Alpha",
        "category": "Cathode",
        "subcategory": "NMC 811",
        "product": "NMC-811 Premium",
        "cost": 145000.00
        },
        {
        "factory": "Plant Alpha",
        "category": "Cathode",
        "subcategory": "LFP",
        "product": "LFP Standard",
        "cost": 135000.00
        },
        {
        "factory": "Plant Beta",
        "category": "Anode",
        "subcategory": "Graphite",
        "product": "Graphite Fine",
        "cost": 95000.00
        },
        {
        "factory": "Plant Beta",
        "category": "Anode",
        "subcategory": "Silicon",
        "product": "Si-C Composite",
        "cost": 85000.00
        },
        {
        "factory": "Plant Gamma",
        "category": "Electrolyte",
        "subcategory": "LiPF6",
        "product": "LiPF6 Solution",
        "cost": 62000.00
        },
        {
        "factory": "Plant Gamma",
        "category": "Separator",
        "subcategory": "Polyolefin",
        "product": "PP Film 25µm",
        "cost": 47000.00
        },
        {
        "factory": "Plant Alpha",
        "category": "Packaging",
        "subcategory": "Aluminum Case",
        "product": "A356 Case 100Ah",
        "cost": 55000.00
        }
    ]
    }

    return data