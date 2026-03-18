from flask import Flask
import os

from modules.bpmn_generator import bpmn_bp
from modules.test_cases import tests_bp
from modules.springboot import springboot_bp
from modules.react_prompt import react_bp
from modules.rag.routes import rag_bp

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "bpmn-agent-secret")

app.register_blueprint(bpmn_bp)
app.register_blueprint(tests_bp)
app.register_blueprint(springboot_bp)
app.register_blueprint(react_bp)
app.register_blueprint(rag_bp)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
