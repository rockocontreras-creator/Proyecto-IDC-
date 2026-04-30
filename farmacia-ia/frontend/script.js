/**
 * Gestiona el cambio de pestañas/secciones en la interfaz.
 * @param {string} id - El identificador de la sección a mostrar.
 * @param {HTMLElement} btn - El botón de la barra lateral que fue presionado.
 */
function showSection(id, btn) {
    // Selecciona todas las secciones de contenido y les quita la clase de visibilidad
    document.querySelectorAll('.content-section').forEach(s => s.classList.remove('active-section'));
    // Selecciona todos los botones de navegación y les quita el estado visual activo
    document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
    // Busca la sección específica por su ID y le añade la clase para hacerla visible
    document.getElementById(id + '-section').classList.add('active-section');
    // Si se pasó un botón como argumento, le añade la clase 'active' para resaltarlo
    if(btn) btn.classList.add('active');
    
    // Condición especial: Si la sección activada es el mapa, dispara la función de carga de mapa
    if(id === 'map') {
        actualizarMapa('hospitales');
    }
}

/**
 * Consulta el endpoint de historial en el backend y renderiza los datos en una tabla.
 */
async function cargarHistorial() {
    // Obtiene el contenedor donde se mostrará el historial
    const div = document.getElementById('history-content');
    // Muestra un mensaje de carga temporal mientras se espera la respuesta del servidor
    div.innerHTML = "<div style='text-align:center;'>Cargando base de datos...</div>";
    try {
        // Realiza una petición GET asíncrona al servidor local de Flask
        const r = await fetch('http://127.0.0.1:5000/obtener_historial');
        // Convierte la respuesta recibida en un objeto JSON manejable
        const data = await r.json();
        
        // Valida si la base de datos devolvió registros
        if(data.length === 0) {
            div.innerHTML = "<p style='text-align:center;'>Aún no hay registros. Realiza una búsqueda primero.</p>";
            return;
        }

        // Define la estructura de cabecera de la tabla utilizando Template Literals de JS
        let html = `<table style="width:100%; border-collapse:collapse; font-size:0.85rem;">
            <tr style="background:#f1f5f9; border-bottom:2px solid #e2e8f0;">
                <th style="padding:12px; text-align:left;">FECHA</th>
                <th style="padding:12px; text-align:left;">FARMACIA</th>
                <th style="padding:12px; text-align:left;">PRODUCTO</th>
                <th style="padding:12px; text-align:right;">PRECIO</th>
            </tr>`;
        
        // Itera sobre cada registro obtenido de la base de datos
        data.forEach(row => {
            // Convierte el timestamp de la base de datos a un formato de fecha local chileno
            const fecha = new Date(row[4]).toLocaleDateString('es-CL');
            // Concatena las filas de la tabla con los datos de farmacia, producto y precio formateado
            html += `<tr style="border-bottom:1px solid #eee;">
                <td style="padding:12px; color:#64748b;">${fecha}</td>
                <td style="padding:12px; font-weight:bold;">${row[1]}</td>
                <td style="padding:12px;">${row[2]}</td>
                <td style="padding:12px; text-align:right; font-weight:bold;">$${row[3].toLocaleString('es-CL')}</td>
            </tr>`;
        });
        // Inyecta el código HTML generado en el contenedor del DOM
        div.innerHTML = html + "</table>";
    } catch(e) { 
        // Captura errores de red (ej: si app.py no está corriendo) y muestra advertencia al usuario
        div.innerHTML = "<p style='color:red; text-align:center;'>Error al conectar con la base de datos (app.py apagado).</p>"; 
    }
}

/**
 * Utiliza la API de Geolocalización del navegador para centrar el mapa y mostrar servicios.
 * @param {string} tipo - El tipo de establecimiento a buscar (hospitales, farmacias).
 */
function actualizarMapa(tipo) {
    // Obtiene el elemento iframe donde se renderiza el mapa de Google
    const iframe = document.getElementById('map-iframe');
    // Verifica si el navegador del usuario tiene permisos o soporte para GPS
    if (navigator.geolocation) {
        // Solicita las coordenadas actuales de forma asíncrona
        navigator.geolocation.getCurrentPosition(p => {
            const lat = p.coords.latitude; // Latitud del usuario
            const lng = p.coords.longitude; // Longitud del usuario
            const q = encodeURIComponent(tipo); // Codifica el texto para que sea seguro en una URL
            
            // Intenta cargar el mapa centrado con marcadores de búsqueda dinámicos
            iframe.src = `https://maps.google.com/?cid=8558870889973429130&g_mp=Cidnb29nbGUubWFwcy5wbGFjZXMudjEuUGxhY2VzLlNlYXJjaFRleHQ{q}&center=${lat},${lng}&zoom=14`;
            
            // Aplica un formato de URL compatible con "Embed" (incrustado) para evitar bloqueos de seguridad de Google
            iframe.src = `https://maps.google.com/maps/contrib/110080353764935262926{q}&ll=${lat},${lng}&z=14&output=embed`;
            
        }, (err) => {
            // Maneja el caso donde el usuario deniega el permiso de ubicación o hay error de señal
            const q = encodeURIComponent(tipo);
            // Carga un mapa general sin coordenadas específicas para no dejar el recuadro vacío
            iframe.src = `https://www.google.com/maps/embed/v1/search?key=TU_API_KEY_AQUI&q=hospitales+y+clinicas&center=$4{q}&z=13&output=embed`;
        });
    }
}

/**
 * Envía el término de búsqueda al backend para iniciar el proceso de Web Scraping multihilo.
 */
async function startScraping() {
    // Captura el nombre del remedio ingresado por el usuario en el buscador
    const query = document.getElementById('manual-search').value;
    const resDiv = document.getElementById('scraping-results');
    // Cancela la ejecución si el campo de búsqueda está vacío
    if(!query) return;
    
    // Muestra una retroalimentación visual de "espera" al usuario
    resDiv.innerHTML = "<div style='text-align:center; padding:20px;'>⏳ Consultando y guardando datos...</div>";
    
    try {
        // Realiza una petición POST enviando el nombre del remedio en el cuerpo (body)
        const r = await fetch('http://127.0.0.1:5000/scraping_manual', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({remedio: query})
        });
        // Espera a que el servidor termine el scraping y devuelva los resultados
        const data = await r.json();
        
        // Inicia la construcción de la tabla de resultados en tiempo real
        let table = `<table style="width:100%; margin-top:20px; border-collapse: collapse;">`;
        // Itera sobre el array de precios devuelto por Python
        data.precios.forEach(p => {
            // Crea filas dinámicas aplicando el color corporativo de cada farmacia
            table += `<tr style="border-bottom:1px solid #eee; height:60px;">
                <td style="font-weight:bold; color:${p.color}; padding:10px;">${p.farmacia}</td>
                <td style="font-size:0.8rem; padding:10px;">${p.nombre}</td>
                <td style="text-align:right; font-weight:bold; padding:10px;">${p.precio}</td>
                <td style="text-align:center; padding:10px;">
                    <a href="${p.link}" target="_blank" style="background:${p.color}; color:${p.farmacia==='Salcobrand'?'black':'white'}; padding:6px 12px; border-radius:6px; text-decoration:none; font-size:0.8rem; font-weight:bold;">Ir ↗</a>
                </td>
            </tr>`;
        });
        // Renderiza la tabla completa con los precios más bajos encontrados
        resDiv.innerHTML = table + "</table>";
    } catch(e) { 
        // Notifica si hay un error de comunicación con el servicio de Flask
        resDiv.innerHTML = "<p style='color:red; text-align:center;'>Error de conexión con el backend.</p>"; 
    }
}