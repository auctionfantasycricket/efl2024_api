# stock_alerts.py
from flask import Blueprint, jsonify, request
from bson import ObjectId
from datetime import datetime

# Assuming `db` is initialized and connected to MongoDB
from config import stockdb as db

stock_alerts_bp = Blueprint('stock_alerts', __name__)

@stock_alerts_bp.route('/alerts', methods=['POST'])
def create_alert():
    data = request.json

    symbol = data.get("symbol")
    alert_date = data.get("alertDate")
    comment = data.get("comment")

    if not symbol or not alert_date:
        return jsonify({"error": "symbol and alertDate are required"}), 400

    alert = {
        "symbol": symbol,
        "alertDate": alert_date,
        "comment": comment,
        "createdAt": datetime.utcnow()
    }

    result = db.alerts.insert_one(alert)
    alert["_id"] = str(result.inserted_id)

    return jsonify(alert), 201

@stock_alerts_bp.route('/alerts', methods=['GET'])
def get_all_alerts():
    alerts = list(db.alerts.find())
    for alert in alerts:
        alert["_id"] = str(alert["_id"])
    return jsonify(alerts), 200

@stock_alerts_bp.route('/alerts/<alert_id>', methods=['GET'])
def get_alert_by_id(alert_id):
    try:
        alert = db.alerts.find_one({"_id": ObjectId(alert_id)})
        if not alert:
            return jsonify({"error": "Alert not found"}), 404

        alert["_id"] = str(alert["_id"])
        return jsonify(alert), 200
    except Exception as e:
        return jsonify({"error": "Invalid alert ID"}), 400

@stock_alerts_bp.route('/alerts/<alert_id>', methods=['PUT'])
def update_alert(alert_id):
    try:
        data = request.json
        update_data = {key: value for key, value in data.items() if value is not None}

        result = db.alerts.update_one({"_id": ObjectId(alert_id)}, {"$set": update_data})

        if result.matched_count == 0:
            return jsonify({"error": "Alert not found"}), 404

        updated_alert = db.alerts.find_one({"_id": ObjectId(alert_id)})
        updated_alert["_id"] = str(updated_alert["_id"])

        return jsonify(updated_alert), 200
    except Exception as e:
        return jsonify({"error": "Invalid alert ID"}), 400

@stock_alerts_bp.route('/alerts/<alert_id>', methods=['DELETE'])
def delete_alert(alert_id):
    try:
        result = db.alerts.delete_one({"_id": ObjectId(alert_id)})

        if result.deleted_count == 0:
            return jsonify({"error": "Alert not found"}), 404

        return '', 204
    except Exception as e:
        return jsonify({"error": "Invalid alert ID"}), 400

@stock_alerts_bp.route('/alerts/process', methods=['GET'])
def process_alerts():
    alerts = list(db.alerts.find())
    processed_alerts = []
    today = datetime.utcnow()

    for alert in alerts:
        if alert.get("alertDate"):
            try:
                alert_date = datetime.strptime(alert["alertDate"], "%Y-%m-%d")
                days_left = (alert_date - today).days
                processed_alerts.append({"symbol": alert["symbol"], "daysLeft": days_left})
            except ValueError:
                continue

    processed_alerts.sort(key=lambda x: x["daysLeft"])  # Sort by days left in ascending order

    return jsonify([{"symbol": alert["symbol"], "daysLeft": f"{alert['daysLeft']} days Left"} for alert in processed_alerts]), 200