# Load environment variables first - before any other imports
from dotenv import load_dotenv
load_dotenv()

from flask import Flask, request, make_response
from flask_cors import CORS
import os
from modules.bpmn_generator import bpmn_bp
from modules.test_cases import tests_bp
from modules.springboot import springboot_bp
from modules.react_prompt import react_bp
from modules.rag.routes import rag_bp
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "bpmn-agent-secret")
CORS(app)

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, Authorization",
}

@app.after_request
def add_cors_headers(response):
    for key, value in CORS_HEADERS.items():
        response.headers[key] = value
    return response

@app.route("/<path:path>", methods=["OPTIONS"])
@app.route("/", methods=["OPTIONS"])
def handle_options(path=""):
    response = make_response("", 204)
    for key, value in CORS_HEADERS.items():
        response.headers[key] = value
    return response

app.register_blueprint(bpmn_bp)
app.register_blueprint(tests_bp)
app.register_blueprint(springboot_bp)
app.register_blueprint(react_bp)
app.register_blueprint(rag_bp)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
