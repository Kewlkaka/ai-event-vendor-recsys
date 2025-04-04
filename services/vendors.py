from flask import Blueprint, jsonify
from db import get_db_connection
import json 

vendors_bp = Blueprint('vendors', __name__)
        
@vendors_bp.route('/api/vendors/services', methods=['GET'])
def get_vendor_services():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute('''
            SELECT vs.id, vs.name, s.name AS service_type, vs.description, 
                   vs.price, vs.city, vs.address, vs.images,
                   COALESCE(json_object_agg(sa.attribute_name, sa.attribute_value), '{}') AS attributes
            FROM vendor_service vs
            LEFT JOIN services s ON vs.service_id = s.id
            LEFT JOIN service_attributes sa ON vs.id = sa.vservice_id
            WHERE vs.status_id = (SELECT id FROM status WHERE status_title = 'Approved')
            GROUP BY vs.id, s.name
        ''')
        
        services = cur.fetchall()
        cur.close()
        conn.close()

        return jsonify([{
            'id': s[0],
            'name': s[1],
            'service_type': s[2],
            'description': s[3],
            'price': s[4],
            'location': f"{s[5]}, {s[6]}" if s[5] and s[6] else "Location not specified",
            'images': json.loads(s[7]) if s[7] else [],
            'attributes': s[8] if s[8] else {}
        } for s in services]), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500