from flask import Blueprint, jsonify
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from db import get_db_connection
import json

recommendations_bp = Blueprint("recommendations", __name__)

SERVICE_CONFIG = {
    "Venue Selection": {
        "event_budget_key": "budget",
        "event_capacity_key": "guest_count",
        "vendor_capacity_key": "Guest Count",
    },
    "Catering & Cuisine": {
        "event_budget_key": "catering_budget",
        "event_capacity_key": "catering_guests",
        "vendor_capacity_key": "Catering Guest Count",
    },
    "Event Decoration": {
        "event_budget_key": "decoration_budget",
        "event_capacity_key": None,
        "vendor_capacity_key": None,
    },
    "Media & Coverage": {
        "event_budget_key": "photo_video_budget",
        "event_capacity_key": None,
        "vendor_capacity_key": None,
    },
    "Invitations & Announcements": {
        "event_budget_key": "invite_budget",
        "event_capacity_key": None,
        "vendor_capacity_key": None,
    },
    "Performances & Entertainment": {
        "event_budget_key": "entertainment_budget",
        "event_capacity_key": None,
        "vendor_capacity_key": None,
    },
    "Technical Equipment": {
        "event_budget_key": "tech_budget",
        "event_capacity_key": None,
        "vendor_capacity_key": None,
    },
}


def preprocess_text(data):
    text_parts = []

    keys = ["preferred_area", "cuisine", "theme", "description"]

    if "photo_style" in data:
        keys.extend(["photo_style", "video_edit_style"])

    if "invite_format" in data:
        keys.extend(["invite_format", "invite_theme"])

    if "entertainment_type" in data:
        keys.extend(["entertainment_type", "special_requests"])

    if "equipment_required" in data:
        keys.extend(["equipment_required", "installation"])

    for key in keys:
        value = str(data.get(key, "")).strip()
        if value:
            text_parts.append(value.lower())

    if "attributes" in data and data["attributes"]:
        for attr, val in data["attributes"].items():
            if isinstance(val, str):
                val_clean = val.strip('"')
            elif isinstance(val, list):
                val_clean = " ".join(map(str, val))
            else:
                val_clean = str(val)
            text_parts.append(f"{attr.lower()}_{val_clean.lower()}")
    return " ".join(text_parts) or ""


@recommendations_bp.route("/api/events/<int:event_id>/recommendations", methods=["GET"])
def get_recommendations(event_id):
    try:
        print(f"Received request for event {event_id}")
        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute(
            """
            SELECT e.event_type, e.event_location, ep.seats, e.privacy, e.event_date,
                   s.name AS service_name, es.id AS es_id
            FROM events e
            LEFT JOIN event_promotion_data ep ON e.id = ep.event_id
            JOIN event_services es ON e.id = es.event_id
            JOIN services s ON es.service_id = s.id
            WHERE e.id = %s
            """,
            (event_id,),
        )
        event_services = cur.fetchall()
        if not event_services:
            return jsonify({"error": "Event not found"}), 404

        event_date = event_services[0][4]

        all_recommendations = {}
        for service in event_services:
            service_name = service[5]
            event_service_id = service[6]

            config = SERVICE_CONFIG.get(service_name, {})
            event_budget_key = config.get("event_budget_key", "budget")
            event_capacity_key = config.get("event_capacity_key")
            vendor_capacity_key = config.get("vendor_capacity_key")

            table_name = (
                service_name.lower().replace(" & ", "_").replace(" ", "_") + "_data"
            )
            cur.execute(
                f"""
                SELECT * 
                FROM {table_name}
                WHERE event_service_id = %s
                """,
                (event_service_id,),
            )
            service_data = cur.fetchone()
            if not service_data:
                all_recommendations[service_name] = []
                continue

            service_columns = [desc[0] for desc in cur.description]
            service_dict = dict(zip(service_columns, service_data))

            try:
                service_budget = float(service_dict.get(event_budget_key, 0))
            except ValueError:
                service_budget = 0.0

            required_capacity = (
                int(service_dict.get(event_capacity_key, 0))
                if event_capacity_key and service_dict.get(event_capacity_key)
                else None
            )

            event_text = preprocess_text(service_dict)

            cur.execute(
                """
                SELECT vs.id, vs.name, vs.description, vs.price, vs.city, vs.address, vs.images,
                       s.name AS service_type, 
                       COALESCE(json_object_agg(sa.attribute_name, sa.attribute_value::text), '{}'::json) AS attributes
                FROM vendor_service vs
                LEFT JOIN service_attributes sa ON vs.id = sa.vservice_id
                LEFT JOIN services s ON vs.service_id = s.id
                WHERE s.name = %s 
                  AND vs.status_id = (SELECT id FROM status WHERE status_title = 'Approved')
                GROUP BY vs.id, s.name
                """,
                (service_name,),
            )
            vendors = cur.fetchall()
            if not vendors:
                all_recommendations[service_name] = []
                continue

            vendor_texts = []
            for v in vendors:
                vendor_attr = v[8] if v[8] else {}
                vendor_text = preprocess_text(
                    {
                        "description": v[2],
                        "city": v[4],
                        "price": v[3],
                        "attributes": vendor_attr,
                    }
                )
                vendor_texts.append(vendor_text)

            if not event_text.strip() and not any(vt.strip() for vt in vendor_texts):
                all_recommendations[service_name] = []
                continue

            corpus = vendor_texts + [event_text]
            vectorizer = TfidfVectorizer()
            tfidf_matrix = vectorizer.fit_transform(corpus)
            similarities = cosine_similarity(
                tfidf_matrix[-1], tfidf_matrix[:-1]
            ).flatten()

            recommendations = []
            for idx, v in enumerate(vendors):
                vendor_price = v[3]
                vendor_attr = v[8] if v[8] else {}
                if vendor_capacity_key:
                    capacity_str = vendor_attr.get(vendor_capacity_key, "0").strip('"')
                    vendor_capacity = int(capacity_str) if capacity_str.isdigit() else 0
                else:
                    vendor_capacity = None

                capacity_ok = True
                if required_capacity is not None:
                    capacity_ok = (
                        vendor_capacity is not None
                        and vendor_capacity >= required_capacity
                    )

                cur.execute(
                    """
                    SELECT 1 FROM booking 
                    WHERE vservice_id = %s 
                    AND booking_date::date = %s::date
                    LIMIT 1
                    """,
                    (v[0], event_date),
                )
                booking_exists = cur.fetchone()

                if (
                    vendor_price <= service_budget
                    and capacity_ok
                    and not booking_exists
                ):
                    recommendations.append(
                        {
                            "vendor_id": v[0],
                            "name": v[1],
                            "price": vendor_price,
                            "capacity": (
                                vendor_capacity
                                if vendor_capacity is not None
                                else "N/A"
                            ),
                            "location": f"{v[4]}, {v[5]}",
                            "images": json.loads(v[6]) if v[6] else [],
                            "attributes": vendor_attr,
                            "similarity_score": float(similarities[idx]),
                        }
                    )

            recommendations.sort(key=lambda x: x["similarity_score"], reverse=True)
            all_recommendations[service_name] = recommendations[:5]

        cur.close()
        conn.close()
        return jsonify(all_recommendations), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500
