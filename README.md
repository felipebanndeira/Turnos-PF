# Sistema de Gestión de Turnos y Clientes

Aplicación web multi-rubro para gestión de reservas, desarrollada en Python/Flask.

## Características Principales

- **Panel de Cliente:** Autogestión de turnos (solicitar, ver historial, cancelar).
- **Panel de Administrador:** Gestión general (agenda diaria, clientes, configuración del negocio, reportes).
- **Flexibilidad Multi-rubro:** Desde el panel de administración podés agregar o quitar servicios y horarios, y el panel del cliente se adaptará automáticamente.
- **Persistencia en JSON:** Datos guardados en `data/` de forma modular, preparado para futura migración a bases de datos relacionales (SQLite/PostgreSQL).

## Instalación y Ejecución Local

1. Abrí tu terminal y posicionate en la carpeta del proyecto.
2. Es recomendable (pero opcional) crear un entorno virtual:
   ```bash
   python -m venv venv
   source venv/bin/activate  # En Windows: venv\Scripts\activate
   ```
3. Instalá las dependencias requeridas:
   ```bash
   pip install -r requirements.txt
   ```
4. Iniciá la aplicación:
   ```bash
   python app.py
   ```
5. Abrí tu navegador e ingresá a: `http://127.0.0.1:5000`

## Credenciales de Acceso

- **Acceso Cliente:**
  Podés crear una cuenta nueva desde el botón "Registrarse".
  O usar la cuenta de demostración:
  - Email: `carlos@demo.com`
  - Clave: `123456` *(Nota: Esta clave de ejemplo fallará si no la registrás propiamente. Mejor probá creando una cuenta desde cero).*

- **Acceso Administrador:**
  Para acceder al panel admin, ingresá a `http://127.0.0.1:5000/admin/login`
  - Usuario: `admin`
  - Clave: `admin123`

## Estructura de Archivos

- `app.py`: Archivo principal de ejecución y filtros Jinja.
- `config.py`: Configuraciones globales.
- `core/`: Lógica de negocio (persistencia, disponibilidad de horarios, gestión de turnos y auth).
- `routes/`: Enrutadores Flask separados por panel (auth, cliente, admin).
- `templates/`: Plantillas HTML usando diseño Dark SaaS (HTML, CSS y JS embebido).
- `data/`: Archivos de persistencia de datos (JSON).
