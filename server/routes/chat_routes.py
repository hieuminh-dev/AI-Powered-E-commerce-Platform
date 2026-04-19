from flask import Blueprint, request, jsonify
import traceback
from flask_jwt_extended import jwt_required, get_jwt_identity, verify_jwt_in_request
import logging
import uuid

from services.chat_service import ChatService
from models.chat_session import ChatSession

logger = logging.getLogger(__name__)
chat_bp = Blueprint("chat", __name__)
chat_service = ChatService()


@chat_bp.route("/message", methods=["POST"])
def send_message():
    """Send a message to the chatbot"""
    try:
        request_id = str(uuid.uuid4())
        # log raw body for debugging malformed JSON / client issues
        try:
            raw_body = request.data.decode("utf-8")
        except Exception:
            raw_body = str(request.data)
        safe_body = raw_body.encode("ascii", "backslashreplace").decode("ascii")
        logger.info("chat.message request_id=%s raw_body=%s", request_id, safe_body)

        data = request.get_json()

        if not data or not data.get("message"):
            return jsonify(
                {"success": False, "message": "Message content is required"}
            ), 400

        user_message = data["message"]
        session_id = data.get("session_id", str(uuid.uuid4()))

        user_id = None
        try:
            verify_jwt_in_request(optional=True)
            user_id = get_jwt_identity()
        except:
            pass

        response = chat_service.process_message(session_id, user_message, user_id)
        logger.info(
            "chat.message request_id=%s session_id=%s response_type=%s product_count=%s",
            request_id,
            session_id,
            response.get("type"),
            len(response.get("products", []) or []),
        )

        return jsonify(
            {"success": True, "response": response, "session_id": session_id}
        ), 200

    except Exception as e:
        logger.exception("Error in send_message endpoint")
        return jsonify({"success": False, "message": "Failed to process message"}), 500


@chat_bp.route("/history/<session_id>", methods=["GET"])
def get_chat_history(session_id):
    """Get chat history for a session"""
    try:
        limit = request.args.get("limit", 50, type=int)

        user_id = None
        try:
            verify_jwt_in_request(optional=True)
            user_id = get_jwt_identity()
        except:
            pass

        chat_session = ChatSession.query.get(session_id)
        if not chat_session:
            return jsonify({"success": False, "message": "Chat session not found"}), 404

        if chat_session.user_id and chat_session.user_id != user_id:
            return jsonify({"success": False, "message": "Access denied"}), 403

        history = chat_service.get_chat_history(session_id, limit)

        return jsonify(
            {"success": True, "history": history, "session": chat_session.to_dict()}
        ), 200

    except Exception as e:
        logger.error(f"Error in get_chat_history endpoint: {str(e)}")
        return jsonify({"success": False, "message": "Failed to get chat history"}), 500


@chat_bp.route("/sessions", methods=["GET"])
@jwt_required()
def get_user_sessions():
    """Get all chat sessions for the authenticated user"""
    try:
        current_user_id = get_jwt_identity()

        sessions = (
            ChatSession.query.filter_by(user_id=current_user_id)
            .order_by(ChatSession.updated_at.desc())
            .all()
        )

        return jsonify(
            {"success": True, "sessions": [session.to_dict() for session in sessions]}
        ), 200

    except Exception as e:
        logger.error(f"Error in get_user_sessions endpoint: {str(e)}")
        return jsonify(
            {"success": False, "message": "Failed to get user sessions"}
        ), 500


@chat_bp.route("/sessions/<session_id>", methods=["DELETE"])
def delete_session(session_id):
    """Delete a chat session"""
    try:
        user_id = None
        try:
            verify_jwt_in_request(optional=True)
            user_id = get_jwt_identity()
        except:
            pass

        chat_session = ChatSession.query.get(session_id)
        if not chat_session:
            return jsonify({"success": False, "message": "Chat session not found"}), 404

        if chat_session.user_id and chat_session.user_id != user_id:
            return jsonify({"success": False, "message": "Access denied"}), 403

        chat_service.clear_session_memory(session_id)

        from app import db

        db.session.delete(chat_session)
        db.session.commit()

        return jsonify(
            {"success": True, "message": "Chat session deleted successfully"}
        ), 200

    except Exception as e:
        logger.error(f"Error in delete_session endpoint: {str(e)}")
        return jsonify({"success": False, "message": "Failed to delete session"}), 500


@chat_bp.route("/sessions/<session_id>/clear", methods=["POST"])
def clear_session(session_id):
    """Clear chat history for a session"""
    try:
        user_id = None
        try:
            verify_jwt_in_request(optional=True)
            user_id = get_jwt_identity()
        except:
            pass

        chat_session = ChatSession.query.get(session_id)
        if not chat_session:
            return jsonify({"success": False, "message": "Chat session not found"}), 404

        if chat_session.user_id and chat_session.user_id != user_id:
            return jsonify({"success": False, "message": "Access denied"}), 403

        from models.message import Message
        from app import db

        Message.query.filter_by(chat_session_id=session_id).delete()
        chat_service.clear_session_memory(session_id)

        db.session.commit()

        return jsonify(
            {"success": True, "message": "Chat session cleared successfully"}
        ), 200

    except Exception as e:
        logger.error(f"Error in clear_session endpoint: {str(e)}")
        return jsonify({"success": False, "message": "Failed to clear session"}), 500


@chat_bp.route("/health", methods=["GET"])
def chat_health():
    """Check chat service health"""
    try:
        logger.info("chat.health check started")
        if not chat_service.initialized:
            logger.info("chat.health chat_service not initialized, initializing")
            chat_service.initialize()

        logger.info("chat.health fetching vector stats")
        try:
            raw_vector_stats = chat_service.vector_service.get_index_stats()
            # Pinecone SDK objects may not be directly JSON serializable.
            if hasattr(raw_vector_stats, "to_dict") and callable(raw_vector_stats.to_dict):
                vector_stats = raw_vector_stats.to_dict()
            elif isinstance(raw_vector_stats, dict):
                vector_stats = raw_vector_stats
            elif raw_vector_stats:
                vector_stats = {"raw": str(raw_vector_stats)}
            else:
                vector_stats = {}
        except Exception:
            logger.exception("chat.health get_index_stats failed unexpectedly")
            vector_stats = {}

        logger.info("chat.health fetching vector diagnostics")
        try:
            vector_diagnostics = chat_service.vector_service.get_diagnostics()
        except Exception:
            logger.exception("chat.health get_diagnostics failed unexpectedly")
            vector_diagnostics = {
                "initialized": chat_service.vector_service.initialized,
                "pinecone_available": bool(getattr(chat_service.vector_service, "index", None)),
                "error": "failed_to_collect_diagnostics",
            }

        return jsonify(
            {
                "success": True,
                "status": "healthy",
                "services": {
                    "chat_service": "initialized"
                    if chat_service.initialized
                    else "not_initialized",
                    "vector_service": "initialized"
                    if chat_service.vector_service.initialized
                    else "not_initialized",
                    "llm": "connected" if chat_service.llm else "not_connected",
                    "llm_provider": chat_service.llm_provider or "none",
                },
                "vector_stats": vector_stats,
                "vector_diagnostics": vector_diagnostics,
            }
        ), 200

    except Exception as e:
        logger.exception("Error in chat_health endpoint")
        return jsonify({"success": False, "status": "unhealthy", "error": str(e)}), 500
