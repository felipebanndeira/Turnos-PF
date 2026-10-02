"""
app.py — Entry point de la aplicación Flask
"""
from flask import Flask
from config import SECRET_KEY

from routes.auth_routes import auth_bp
from routes.cliente_routes import cliente_bp
from routes.admin_routes import admin_bp

app = Flask(__name__)
app.secret_key = SECRET_KEY

# Registrar blueprints
app.register_blueprint(auth_bp)
app.register_blueprint(cliente_bp)
app.register_blueprint(admin_bp)

# Filtro Jinja2: formatear precio en pesos
@app.template_filter("pesos")
def pesos_filter(value):
    try:
        return f"${float(value):,.0f}".replace(",", ".")
    except (ValueError, TypeError):
        return value

# Filtro Jinja2: nombre del día en español
DIAS_ES = {0:"Lunes",1:"Martes",2:"Miércoles",3:"Jueves",4:"Viernes",5:"Sábado",6:"Domingo"}

@app.template_filter("dia_semana")
def dia_semana_filter(fecha_str):
    from datetime import date
    try:
        d = date.fromisoformat(fecha_str)
        return DIAS_ES.get(d.weekday(), "")
    except Exception:
        return ""

@app.template_filter("fecha_es")
def fecha_es_filter(fecha_str):
    from datetime import date
    MESES = ["","ene","feb","mar","abr","may","jun","jul","ago","sep","oct","nov","dic"]
    try:
        d = date.fromisoformat(fecha_str)
        return f"{d.day} {MESES[d.month]} {d.year}"
    except Exception:
        return fecha_str


if __name__ == "__main__":
    app.run(debug=True)
