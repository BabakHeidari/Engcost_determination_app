from flask import Blueprint, render_template, jsonify, request, session
from utils.auth import login_required
from utils.paths import product_path, material_path, parent_path
from utils.load_data import load_json, load_bom
from utils.updaters import create_product_metadata, category_adder, subcategory_adder, product_adder, directory_tracer, category_weights_updater, capacity_writer
import json

profile_bp = Blueprint("profile", __name__)

@profile_bp.route("/profile/profile")
@login_required
def profile():
    return render_template("profile/profile.html")


# @app.route('/profile')
# @login_required
# def profile():
#     # Get current user from database
#     current_user_data = get_user_from_db(session['user_id'])
    
#     # Get all manageable users based on role hierarchy
#     all_users_data = get_manageable_users(session['user_id'])
    
#     return render_template(
#         'profile.html',
#         current_user=current_user_data,
#         all_users=all_users_data
#     )

# @app.route('/api/profile/update-privileges', methods=['POST'])
# @login_required
# @admin_required
# def update_privileges():
#     data = request.json
    
#     # Validate and update in database
#     success = update_user_privileges_in_db(
#         data['target_user_id'],
#         data['new_privileges'],
#         data.get('new_scope'),
#         data.get('new_factory_id')
#     )
    
#     return jsonify({
#         "success": success,
#         "message": "Privileges updated" if success else "Update failed"
#     })

# Backend endpoint for adding users
# @app.route('/api/profile/add-user', methods=['POST'])
# @login_required
# @admin_required
# def add_user():
#     data = request.json
    
#     # Validate creation permissions
#     if not can_create_role(data['created_by'], data['role']):
#         return jsonify({"success": False, "message": "Cannot create this role"}), 403
    
#     # Create user in database
#     user_id = create_user_in_db(data)
    
#     return jsonify({"success": True, "user_id": user_id})

# @app.route('/api/profile/add-factory', methods=['POST'])
# @login_required
# def add_factory():
#     # Only Official Admin can add factories
#     if session['user_role'] != 'Official Admin':
#         return jsonify({"success": False, "message": "Unauthorized"}), 403
    
#     data = request.json
#     factory_code = data['code']
#     factory_name = data['name']
#     factory_location = data.get('location', '')
    
#     # Add to database
#     success = create_factory_in_db(factory_code, factory_name, factory_location)
    
#     return jsonify({"success": success})