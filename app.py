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

@app.before_request
def handle_preflight():
    if request.method == "OPTIONS":
        response = make_response()
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        response.status_code = 200
        return response

@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    return response

app.register_blueprint(bpmn_bp)
app.register_blueprint(tests_bp)
app.register_blueprint(springboot_bp)
app.register_blueprint(react_bp)
app.register_blueprint(rag_bp)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
