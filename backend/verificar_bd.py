import sqlite3

def revisar_base_de_datos():
    conn = sqlite3.connect('farmacia.db')
    cursor = conn.cursor()
    
    print("--- TABLAS DISPONIBLES ---")
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tablas = cursor.fetchall()
    for tabla in tablas:
        print(f"Tabla detectada: {tabla[0]}")
        
    print("\n--- REGISTROS EN TABLA FARMACIAS ---")
    cursor.execute("SELECT * FROM farmacias")
    farmacias = cursor.fetchall()
    for f in farmacias:
        print(f"ID: {f[0]} | Nombre: {f[1]} | Código Color: {f[2]}")
        
    print("\n--- ÚLTIMOS 5 REGISTROS EN EL HISTORIAL ---")
    try:
        # Consulta corregida usando h.nombre_producto de forma exacta
        cursor.execute("""
            SELECT h.id, m.nombre_buscado, f.nombre, h.nombre_producto, h.precio, h.fecha 
            FROM historial h 
            JOIN farmacias f ON h.farmacia_id = f.id 
            JOIN medicamentos m ON h.medicamento_id = m.id 
            ORDER BY h.fecha DESC LIMIT 5
        """)
        historial = cursor.fetchall()
        if not historial:
            print("El historial está vacío de momento. Realiza búsquedas desde la interfaz para poblarlo.")
        for h in historial:
            print(f"Reg: {h[0]} | Buscado: {h[1]} | Farmacia: {h[2]} | Encontrado: {h[3]} | Precio: ${h[4]} | Fecha: {h[5]}")
    except sqlite3.OperationalError as e:
        print(f"Error operativo en la consulta SQL: {e}")
        
    conn.close()

if __name__ == '__main__':
    revisar_base_de_datos()