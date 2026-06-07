"""
HACER ADMIN — FarmaConnect
---------------------------
Promueve un usuario existente a administrador (o lo quita).

Uso:
    python hacer_admin.py correo@ejemplo.com         # lo hace admin
    python hacer_admin.py correo@ejemplo.com quitar   # le quita el admin
    python hacer_admin.py                             # lista todos los usuarios

El usuario debe haberse registrado antes desde la app.
"""

import sqlite3
import sys


def listar():
    conn = sqlite3.connect('farmacia.db')
    c = conn.cursor()
    c.execute("SELECT id_usuario, nombre, correo, es_admin FROM usuarios ORDER BY id_usuario")
    filas = c.fetchall()
    conn.close()
    if not filas:
        print("No hay usuarios registrados todavía. Regístrate primero desde la app.")
        return
    print(f"\n{'ID':<4} {'NOMBRE':<25} {'CORREO':<30} {'ADMIN'}")
    print("-" * 70)
    for f in filas:
        print(f"{f[0]:<4} {f[1][:24]:<25} {f[2][:29]:<30} {'SÍ' if f[3] else 'no'}")
    print()


def cambiar(correo, hacer=True):
    conn = sqlite3.connect('farmacia.db')
    c = conn.cursor()
    c.execute("SELECT id_usuario, nombre FROM usuarios WHERE correo = ?", (correo.lower().strip(),))
    u = c.fetchone()
    if not u:
        print(f"❌ No se encontró ningún usuario con el correo '{correo}'.")
        print("   Asegúrate de haberte registrado primero desde la app.")
        conn.close()
        return
    c.execute("UPDATE usuarios SET es_admin = ? WHERE id_usuario = ?", (1 if hacer else 0, u[0]))
    conn.commit()
    conn.close()
    estado = "ahora es ADMINISTRADOR ✅" if hacer else "ya NO es administrador"
    print(f"Listo: {u[1]} ({correo}) {estado}.")
    print("Cierra sesión y vuelve a entrar en la app para que se aplique el cambio.")


if __name__ == '__main__':
    if len(sys.argv) == 1:
        listar()
    else:
        correo = sys.argv[1]
        quitar = len(sys.argv) > 2 and sys.argv[2].lower() in ('quitar', 'remove', 'off')
        cambiar(correo, hacer=not quitar)