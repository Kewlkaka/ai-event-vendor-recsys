from flask import Blueprint, jsonify, request
from db import get_db_connection

events_bp = Blueprint("events", __name__)


@events_bp.route("/api/events/<int:event_id>", methods=["GET"])
def get_event_requirements(event_id):
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute(
            """
            SELECT e.event_type, e.event_location, ep.price, ep.seats, e.privacy
            FROM events e
            LEFT JOIN event_promotion_data ep ON e.id = ep.event_id
            WHERE e.id = %s
        """,
            (event_id,),
        )
        event_data = cur.fetchone()

        if not event_data:
            return jsonify({"error": "Event not found"}), 404

        cur.execute(
            """
            SELECT s.name, es.id 
            FROM event_services es
            JOIN services s ON es.service_id = s.id
            WHERE es.event_id = %s
        """,
            (event_id,),
        )
        services = cur.fetchall()

        requirements = {}
        for service in services:
            service_name = service[0]
            es_id = service[1]

            if service_name == "Venue Selection":
                cur.execute(
                    """
                    SELECT budget, guest_count, preferred_area 
                    FROM venue_selection_data 
                    WHERE event_service_id = %s
                """,
                    (es_id,),
                )
                venue_data = cur.fetchone()
                if venue_data:
                    requirements[service_name] = {
                        "budget": venue_data[0],
                        "guest_count": venue_data[1],
                        "preferred_area": venue_data[2],
                    }

            elif service_name == "Catering & Cuisine":
                cur.execute(
                    """
                    SELECT catering_budget, catering_guests, cuisine 
                    FROM catering_cuisine_data 
                    WHERE event_service_id = %s
                """,
                    (es_id,),
                )
                catering_data = cur.fetchone()
                if catering_data:
                    requirements[service_name] = {
                        "budget": catering_data[0],
                        "guests": catering_data[1],
                        "cuisine": catering_data[2],
                    }

        cur.close()
        conn.close()

        return (
            jsonify(
                {
                    "event_type": event_data[0],
                    "location": event_data[1],
                    "budget": float(event_data[2]) if event_data[2] else None,
                    "attendees": event_data[3] if event_data[3] else None,
                    "privacy": event_data[4],
                    "requirements": requirements,
                }
            ),
            200,
        )

    except Exception as e:
        return jsonify({"error": str(e)}), 500
