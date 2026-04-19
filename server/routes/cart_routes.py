from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required
from services.cart_service import CartService

cart_bp = Blueprint("cart", __name__)
cart_service = CartService()


@cart_bp.route("/cart/<user_id>", methods=["GET"])
@jwt_required()
def get_cart(user_id):
    try:
        current_user = get_jwt_identity()

        # Users can only access their own cart
        if current_user != user_id:
            return jsonify({"error": "Unauthorized"}), 403

        cart_items = cart_service.get_cart(user_id)
        return jsonify(cart_items), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@cart_bp.route("/cart/add", methods=["POST"])
@jwt_required()
def add_to_cart():
    try:
        current_user = get_jwt_identity()
        data = request.get_json()
        user_id = data.get("user_id")
        product_id = data.get("product_id")
        quantity = data.get("quantity", 1)

        # Users can only add to their own cart
        if current_user != user_id:
            return jsonify({"error": "Unauthorized"}), 403

        if not user_id or not product_id:
            return jsonify({"error": "user_id and product_id are required"}), 400

        result = cart_service.add_to_cart(user_id, product_id, quantity)
        if not result.get("success"):
            return jsonify(result), 400

        return jsonify(result), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@cart_bp.route("/cart/remove", methods=["DELETE"])
@jwt_required()
def remove_from_cart():
    try:
        current_user = get_jwt_identity()
        data = request.get_json()
        user_id = data.get("user_id")
        item_id = data.get("item_id")

        # Users can only remove from their own cart
        if current_user != user_id:
            return jsonify({"error": "Unauthorized"}), 403

        if not user_id or not item_id:
            return jsonify({"error": "user_id and item_id are required"}), 400

        result = cart_service.remove_from_cart(user_id, item_id)
        if result.get("success"):
            return jsonify(result), 200
        return jsonify(result), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@cart_bp.route("/cart/update", methods=["PUT"])
@jwt_required()
def update_cart_quantity():
    try:
        current_user = get_jwt_identity()
        data = request.get_json()
        user_id = data.get("user_id")
        item_id = data.get("item_id")
        quantity = data.get("quantity")

        # Users can only update their own cart
        if current_user != user_id:
            return jsonify({"error": "Unauthorized"}), 403

        if not user_id or not item_id or quantity is None:
            return jsonify({"error": "user_id, item_id, and quantity are required"}), 400

        if quantity <= 0:
            # Remove item if quantity is 0 or negative
            result = cart_service.remove_from_cart(user_id, item_id)
            if result.get("success"):
                return jsonify(result), 200
            return jsonify(result), 404
        else:
            result = cart_service.update_cart_quantity(user_id, item_id, quantity)
            if result.get("success"):
                return jsonify(result), 200
            return jsonify(result), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@cart_bp.route("/cart/clear", methods=["DELETE"])
@jwt_required()
def clear_cart():
    try:
        current_user = get_jwt_identity()
        data = request.get_json()
        user_id = data.get("user_id")

        # Users can only clear their own cart
        if current_user != user_id:
            return jsonify({"error": "Unauthorized"}), 403

        if not user_id:
            return jsonify({"error": "user_id is required"}), 400

        result = cart_service.clear_cart(user_id)
        if result.get("success"):
            return jsonify(result), 200
        return jsonify(result), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500
