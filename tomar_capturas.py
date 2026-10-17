import os
import threading
import time
from app import app
from playwright.sync_api import sync_playwright

CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
OUTPUT_DIR = "capturas_pantallas"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Endpoint especial local solo para la toma de screenshots con sesión admin activa
@app.route('/dev-login-admin')
def dev_login_admin():
    from flask import session, redirect, url_for
    session['rol'] = 'admin'
    session['negocio_id'] = 'barberia-pepe'
    session['negocio_nombre'] = 'Golden Barber Studio'
    session['admin_email'] = 'bandeirafeli06@icloud.com'
    return redirect(url_for('admin.agenda'))

def start_server():
    app.run(port=5015, debug=False, use_reloader=False)

def take_all_screenshots():
    # Iniciar servidor local
    t = threading.Thread(target=start_server, daemon=True)
    t.start()
    time.sleep(2)

    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=CHROME_PATH, headless=True)
        
        # 1. Desktop context para Landing y Paneles Admin (1280x800)
        ctx_desktop = browser.new_context(viewport={'width': 1280, 'height': 820}, device_scale_factor=2)
        page_d = ctx_desktop.new_page()

        # P-01: Landing Page
        print("Capturando P-01: Landing...")
        page_d.goto("http://127.0.0.1:5015/", wait_until="networkidle")
        page_d.wait_for_timeout(1000)
        page_d.screenshot(path=os.path.join(OUTPUT_DIR, "p01_landing.png"))

        # Iniciar sesión de admin
        print("Iniciando sesión admin...")
        page_d.goto("http://127.0.0.1:5015/dev-login-admin", wait_until="networkidle")
        page_d.wait_for_timeout(1000)

        # P-04: Agenda de Administración
        print("Capturando P-04: Agenda...")
        page_d.goto("http://127.0.0.1:5015/admin/agenda", wait_until="networkidle")
        page_d.wait_for_timeout(1000)
        page_d.screenshot(path=os.path.join(OUTPUT_DIR, "p04_agenda.png"))

        # P-05: Caja y Arqueo Diario
        print("Capturando P-05: Caja...")
        page_d.goto("http://127.0.0.1:5015/admin/caja", wait_until="networkidle")
        page_d.wait_for_timeout(1000)
        page_d.screenshot(path=os.path.join(OUTPUT_DIR, "p05_caja.png"))

        # P-06: Configuración del Negocio
        print("Capturando P-06: Configuración...")
        page_d.goto("http://127.0.0.1:5015/admin/configuracion", wait_until="networkidle")
        page_d.wait_for_timeout(1000)
        page_d.screenshot(path=os.path.join(OUTPUT_DIR, "p06_configuracion.png"))

        ctx_desktop.close()

        # 2. Mobile Context para Flujo de Cliente (390x844 - iPhone 14 / Smartphone estándar)
        ctx_mobile = browser.new_context(
            viewport={'width': 420, 'height': 820},
            device_scale_factor=2,
            is_mobile=True,
            has_touch=True
        )
        page_m = ctx_mobile.new_page()

        # P-02: Solicitud de Turno (Reserva Cliente)
        print("Capturando P-02: Solicitud de Turno...")
        page_m.goto("http://127.0.0.1:5015/b/barberia-pepe/solicitar", wait_until="networkidle")
        page_m.wait_for_timeout(1200)
        page_m.screenshot(path=os.path.join(OUTPUT_DIR, "p02_solicitar_turno.png"))

        # P-03: Mis Turnos
        print("Capturando P-03: Mis Turnos...")
        page_m.goto("http://127.0.0.1:5015/b/barberia-pepe/mis-turnos", wait_until="networkidle")
        page_m.wait_for_timeout(1000)
        page_m.screenshot(path=os.path.join(OUTPUT_DIR, "p03_mis_turnos.png"))

        ctx_mobile.close()
        browser.close()

    print("\n¡Todas las capturas se generaron exitosamente en 'capturas_pantallas'!")

if __name__ == "__main__":
    take_all_screenshots()
