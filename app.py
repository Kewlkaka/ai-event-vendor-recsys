from flask import Flask
from flask_cors import CORS
import os
from services.vendors import vendors_bp
from services.events import events_bp
from services.recommendations import recommendations_bp

app = Flask(__name__)
CORS(app)

app.register_blueprint(vendors_bp)
app.register_blueprint(events_bp)
app.register_blueprint(recommendations_bp)

if __name__ == "__main__":
    app.run(
        host="0.0.0.0", port=5000, debug=os.getenv("FLASK_DEBUG", "False") == "True"
    )
