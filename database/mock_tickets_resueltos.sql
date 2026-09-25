-- ============================================================
-- mock_tickets_resueltos.sql — SHelpDesk Microsoft
-- Corpus de evaluación para el RAG (búsqueda semántica bge-m3 + pgvector)
-- Inserta 60 tickets hipotéticos YA RESUELTOS/CERRADOS con su historial
-- completo, descripciones realistas (síntoma + solución aplicada) y fechas
-- repartidas en los últimos ~60 días.
--
-- Idempotente: si se ejecuta de nuevo, borra primero los mocks anteriores
-- (las FK con ON DELETE CASCADE limpian historial y embeddings).
--
-- Uso (desde la raíz del proyecto):
--   cat mock_tickets_resueltos.sql | docker exec -i helpdesk-db psql -U postgres -d helpdesk_db
--   (o copia el archivo al contenedor y ejecútalo con psql -f)
--
-- Los usuarios (solicitante, agente, coordinador) se resuelven dinámicamente
-- por rol, por lo que funciona en cualquier BD que tenga el seed aplicado.
-- ============================================================

SET client_encoding = 'UTF8';

DO $$
DECLARE
    fila RECORD;
    v_id INTEGER;
    v_soli INTEGER;
    v_ag1 INTEGER;
    v_ag2 INTEGER;
    v_resolver INTEGER;
BEGIN
    -- ---------- Resolución dinámica de usuarios (portable entre BD) ----------
    v_soli := (SELECT id_usuario FROM usuarios WHERE rol = 'solicitante' AND estado = 'activo' ORDER BY id_usuario LIMIT 1);
    v_ag1  := (SELECT id_usuario FROM usuarios WHERE rol = 'agente'      AND estado = 'activo' ORDER BY id_usuario LIMIT 1);
    v_ag2  := (SELECT id_usuario FROM usuarios WHERE rol = 'coordinador' AND estado = 'activo' ORDER BY id_usuario LIMIT 1);
    IF v_ag2 IS NULL THEN
        v_ag2 := v_ag1;
    END IF;
    IF v_soli IS NULL OR v_ag1 IS NULL THEN
        RAISE EXCEPTION 'Faltan usuarios base (solicitante/agente). Ejecuta antes seed_usuarios.sql';
    END IF;
    -- ---------- Limpieza de mocks previos (idempotencia) ----------
    DELETE FROM solicitud WHERE asunto IN (
        'Impresora atascada: hoja bloqueada en el rodillo',
        'WiFi se desconecta constantemente en el área de producción',
        'Pantalla azul al arrancar con error de driver de video',
        'Restablecer contraseña del correo corporativo',
        'VPN no conecta desde casa',
        'El PC va muy lento y el disco está al 100 por ciento',
        'Outlook no sincroniza el buzón',
        'El monitor no da señal',
        'Solicitud de instalación de AutoCAD para diseño',
        'Teclado y mouse USB dejan de responder',
        'Sin acceso a la carpeta compartida de Contabilidad',
        'La laptop no enciende sin estar conectada al cargador',
        'Windows Update falla en bucle con error 0x800f0922',
        'Correo sospechoso de phishing recibido',
        'La impresora de red no aparece en Windows',
        'Excel se cierra solo y el archivo quedó corrupto',
        'Alta de empleado nuevo: cuenta y equipo',
        'Se derramó café sobre el teclado',
        'El firewall bloquea el sistema contable',
        'Impresora imprime páginas en blanco',
        'Office pide activación y los documentos quedan en modo lectura',
        'La cámara web no funciona en las videollamadas',
        'El escáner no responde y la digitalización queda en cola',
        'Chrome no abre y el equipo queda sin navegador operativo',
        'El segundo piso pierde el acceso a Internet por completo',
        'Los correos con adjuntos grandes no salen del buzón',
        'El disco externo de respaldos no monta en Windows',
        'Cuenta bloqueada por intentos fallidos tras las vacaciones',
        'El ERP muestra error de licencia al iniciar sesión',
        'La impresora de etiquetas imprime desalineado en el almacén',
        'El portátil se sobrecalienta y se apaga en plena reunión',
        'Accesos al sistema de nómina para el área de RRHH',
        'Los auriculares Bluetooth no emparejan con el equipo',
        'Antivirus alerta cifrado sospechoso en la carpeta de descargas',
        'El sistema de tickets no envía las notificaciones por correo',
        'La tablet de inventario no sincroniza con el servidor',
        'El proyector de la sala de juntas no detecta el portátil',
        'Windows pide activación tras el cambio de placa base',
        'El correo corporativo llega con retraso de horas al celular',
        'Solicitud de monitor adicional para estación de diseño',
        'El portátil se queda sin batería muy rápido',
        'No puedo acceder al portal de proveedores desde la oficina',
        'El servidor de archivos está lleno y no permite guardar',
        'Teams no carga el historial de chats',
        'La impresora multifunción no escanea a correo',
        'Solicitud de alta de correo para práctica',
        'El ratón inalámbrico se desconecta intermitentemente',
        'La base de datos reporta lentitud en horario pico',
        'No se puede iniciar sesión en Windows por error de perfil',
        'El certificado de la web interna está caducado',
        'El repositorio Git corporativo rechaza el push',
        'La VPN se desconecta cada 30 minutos',
        'El escáner de huellas no valida el acceso',
        'Los informes de Power BI no se actualizan',
        'El teléfono IP no marca tono',
        'Solicitud de segundo monitor para analista',
        'El antivirus bloquea un ejecutable del sistema de gestión',
        'La carpeta de red tarda en abrir desde la sucursal',
        'El teclado del portátil tiene teclas que no responden',
        'Fallo al imprimir la nómina mensual por desbordamiento'
    );

    -- ---------- Corpus de tickets resueltos/cerrados ----------
    FOR fila IN
        SELECT * FROM (VALUES
            ('Impresora atascada: hoja bloqueada en el rodillo',
             'La impresora láser de recepción detiene cada impresión marcando atasco de papel en el rodillo de salida. Se retiró la hoja atascada, se limpiaron los rodillos con alcohol isopropílico y quedó operativa. Se recomendó papel de 80 gramos para evitar recurrencias.',
             1, 3, 'resuelto', 1, 1, 52),
            ('WiFi se desconecta constantemente en el área de producción',
             'Los usuarios del área de producción pierden la conexión WiFi cada pocos minutos. Se detectó interferencia de canal con una red vecina, se cambió el canal del router al 6 y se actualizó el firmware del access point. Conexión estable desde entonces.',
             3, 2, 'resuelto', 1, 1, 48),
            ('Pantalla azul al arrancar con error de driver de video',
             'El equipo muestra pantalla azul con VIDEO_TDR_FAILURE al iniciar Windows tras una actualización automática. Se arrancó en modo seguro, se desinstaló el driver de NVIDIA con DDU y se instaló la versión estable certificada. El equipo arranca sin errores.',
             2, 2, 'resuelto', 2, 1, 45),
            ('Restablecer contraseña del correo corporativo',
             'El usuario olvidó la contraseña del correo y tras varios intentos fallidos la cuenta quedó bloqueada. Se restableció la contraseña desde el panel de administración, se desbloqueó la cuenta y se configuró autenticación de dos factores. Acceso recuperado.',
             4, 3, 'cerrado', 1, 1, 60),
            ('VPN no conecta desde casa',
             'Al intentar conectar la VPN corporativa desde casa aparece el error 809 y no se establece el túnel. Se actualizó el cliente VPN, se habilitó el passthrough IPSec en el router doméstico y se regeneró el certificado del usuario. Conexión estable verificada una semana.',
             3, 2, 'resuelto', 1, 1, 41),
            ('El PC va muy lento y el disco está al 100 por ciento',
             'El equipo tarda varios minutos en arrancar y el disco reporta uso del 100 por ciento constante. Se liberaron 120 GB desinstalando programas obsoletos, se vació la carpeta temporal y se desactivaron programas de arranque innecesarios. Rendimiento normalizado.',
             2, 3, 'resuelto', 1, 1, 38),
            ('Outlook no sincroniza el buzón',
             'Outlook queda procesando al sincronizar y no descargan los correos nuevos desde hace dos días. Se recreó el perfil de correo, se reparó el archivo OST con scanpst y se amplió la cuota del buzón que estaba llena. Sincronización restaurada.',
             2, 3, 'cerrado', 2, 1, 35),
            ('El monitor no da señal',
             'El monitor quedó en negro con el indicador de encendido parpadeando aunque el equipo parece arrancar con normalidad. Se cambió el cable HDMI dañado por uno nuevo y se reinstaló el driver de la tarjeta gráfica. Imagen restablecida.',
             1, 4, 'resuelto', 1, 1, 33),
            ('Solicitud de instalación de AutoCAD para diseño',
             'El área de diseño solicita la instalación de AutoCAD con licencia corporativa. Se validó la licencia disponible, se instaló la versión 2024 con las plantillas y configuraciones del área y se activó correctamente. Equipo listo para trabajar.',
             2, 4, 'cerrado', 2, 1, 30),
            ('Teclado y mouse USB dejan de responder',
             'El teclado y el mouse se congelan aleatoriamente aunque el equipo sigue encendido. Se actualizó el driver del chipset USB del fabricante y se probaron los periféricos en otro equipo descartando falla física. Funcionamiento estable tras la actualización.',
             1, 3, 'resuelto', 1, 1, 27),
            ('Sin acceso a la carpeta compartida de Contabilidad',
             'El usuario no puede abrir la carpeta compartida del servidor de Contabilidad y recibe acceso denegado. Se revisaron los grupos de seguridad en el directorio activo, se agregó al usuario al grupo correcto y se propagaron los permisos NTFS. Acceso concedido y verificado.',
             4, 2, 'resuelto', 1, 1, 24),
            ('La laptop no enciende sin estar conectada al cargador',
             'La laptop se apaga al desenchufarla aunque la batería marca carga completa. Diagnóstico: batería degradada con 20 por ciento de su salud original. Se reemplazó por una batería nueva original y se calibró. Autonomía de 5 horas verificada.',
             1, 2, 'resuelto', 2, 1, 21),
            ('Windows Update falla en bucle con error 0x800f0922',
             'La actualización acumulativa de Windows falla repetidamente y revierte los cambios con el código 0x800f0922. Se liberó espacio en la partición del sistema, se repararon los componentes con DISM y SFC, y se instaló la actualización manualmente desde el catálogo. Equipo actualizado.',
             2, 3, 'cerrado', 1, 1, 18),
            ('Correo sospechoso de phishing recibido',
             'El usuario recibió un correo suplantando al banco con un enlace a un sitio falso que pedía credenciales; no se ingresó información. Se reportó el mensaje, se bloqueó el dominio en el gateway de correo y se envió circular de sensibilización a toda la empresa.',
             5, 1, 'resuelto', 2, 1, 15),
            ('La impresora de red no aparece en Windows',
             'La impresora de red del área de ventas no aparece al buscarla y no se puede instalar por IP. Se detectó una IP duplicada por DHCP, se fijó una IP reservada y se instaló el driver universal del fabricante por puerto TCP/IP. Impresión funcionando.',
             3, 3, 'resuelto', 1, 1, 12),
            ('Excel se cierra solo y el archivo quedó corrupto',
             'Excel se cierra inesperadamente al guardar un archivo grande y el libro quedó dañado. Se recuperó el contenido con la función de reparación integrada y la copia de seguridad de la red. Se actualizó Office al canal estable para corregir el bug conocido.',
             2, 2, 'resuelto', 2, 1, 9),
            ('Alta de empleado nuevo: cuenta y equipo',
             'Ingreso de nueva empleada en el área de Compras: se creó la cuenta de correo y el usuario de dominio, se configuró el equipo con la imagen corporativa, Office y VPN, y se otorgaron los accesos a las carpetas del área. Onboarding de TI completado.',
             4, 3, 'cerrado', 1, 1, 7),
            ('Se derramó café sobre el teclado',
             'Se derramó café sobre el teclado y varias teclas quedaron pegajosas y sin responder. Se desmontó el teclado, se limpió con alcohol isopropílico y, ante el daño recurrente de la membrana, se reemplazó el teclado completo por uno nuevo.',
             1, 4, 'resuelto', 1, 1, 5),
            ('El firewall bloquea el sistema contable',
             'El sistema contable no logra conectar con el servidor desde la actualización del firewall y muestra timeout de conexión. Se creó una regla de salida para el ejecutable y el puerto 1433 de SQL en el firewall corporativo. La aplicación vuelve a conectar.',
             3, 1, 'resuelto', 2, 1, 5),
            ('Impresora imprime páginas en blanco',
             'La impresora de recursos humanos imprime páginas en blanco aunque el cartucho de tóner es nuevo. Se realizó una limpieza profunda del cabezal desde el panel, se verificó el sellado del cartucho y se actualizó el firmware. Calidad de impresión restablecida.',
             1, 3, 'resuelto', 1, 1, 5),
            ('Office pide activación y los documentos quedan en modo lectura',
             'Los documentos de Office abren en modo lectura y la barra superior pide activación tras el cambio de equipo. Se cerró la sesión previa de Office, se reactivó con la cuenta corporativa del portal de licencias y se reparó la instalación en línea. Los documentos vuelven a editarse sin restricciones.',
             2, 3, 'resuelto', 1, 1, 58),
            ('La cámara web no funciona en las videollamadas',
             'La cámara web integrada aparece con imagen negra y el LED apagado en las videollamadas de Teams. Se habilitó el dispositivo en el Administrador de dispositivos, se concedieron los permisos de privacidad de Windows y se actualizó el driver del fabricante. Video restablecido en las llamadas.',
             1, 4, 'resuelto', 2, 1, 55),
            ('El escáner no responde y la digitalización queda en cola',
             'El escáner de red de Recursos Humanos no responde a las peticiones y los trabajos de digitalización quedan en cola sin procesar. Se cambió la conexión a red fija, se reinició el servicio de cola del servidor y se actualizó el firmware del equipo. Digitalización fluida de nuevo.',
             1, 3, 'resuelto', 1, 1, 50),
            ('Chrome no abre y el equipo queda sin navegador operativo',
             'Chrome se cierra al momento de abrirse y el equipo queda sin navegador operativo tras una actualización fallida del perfil. Se renombró el perfil de usuario dañado, se reparó la instalación con el instalador offline y se restauraron los marcadores desde la sincronización corporativa. Navegación funcionando.',
             2, 4, 'resuelto', 1, 1, 47),
            ('El segundo piso pierde el acceso a Internet por completo',
             'Los equipos del segundo piso pierden el acceso a Internet de golpe mientras el resto del edificio sigue conectado. El switch del rack intermedio dejó de responder tras un pico eléctrico. Se reemplazó la fuente del switch, se reconfiguraron los puertos VLAN y se etiquetó el cableado. Internet estable en el piso.',
             3, 2, 'resuelto', 2, 1, 42),
            ('Los correos con adjuntos grandes no salen del buzón',
             'Los correos con adjuntos de más de 20 MB quedan estancados en la bandeja de salida y generan retrasos de envío con notificaciones NDR. Se movió el adjunto al repositorio compartido con enlace, se ajustó el límite de tamaño de adjuntos del servidor de correo y se purgó la cola estancada. Envíos fluyendo sin retrasos.',
             2, 3, 'cerrado', 1, 1, 40),
            ('El disco externo de respaldos no monta en Windows',
             'El disco externo de respaldos no monta en el Explorador y el Administrador de discos lo muestra sin letra asignada. Se reasignó la letra de unidad, se revisó la tabla de particiones con chkdsk en modo solo lectura y se actualizó el firmware del enclosure. Copias de seguridad operativas.',
             1, 2, 'resuelto', 1, 1, 36),
            ('Cuenta bloqueada por intentos fallidos tras las vacaciones',
             'La cuenta quedó bloqueada por intentos fallidos de contraseña acumulados durante las vacaciones. Se desbloqueó desde el panel de administración, se restableció la contraseña con cambio obligatorio en el primer acceso y se activó el desbloqueo automático temporal. Acceso recuperado.',
             4, 3, 'resuelto', 2, 1, 34),
            ('El ERP muestra error de licencia al iniciar sesión',
             'El ERP corporativo rechaza el inicio de sesión con un error de licencia agotada a mitad del turno. El servidor de licencias quedó detenido tras un reinicio no programado. Se inició el servicio, se validó el conteo de licencias activas y se ordenó el apagado limpio en el reinicio programado. Sesiones restauradas.',
             2, 2, 'resuelto', 1, 1, 31),
            ('La impresora de etiquetas imprime desalineado en el almacén',
             'La impresora de etiquetas del almacén imprime desalineado y los códigos de barras no leen en el escáner de inventario. Se recalibró el sensor de papel, se ajustó la plantilla de la etiqueta en el driver y se limpió el cabezal térmico. Etiquetas legibles verificadas.',
             1, 3, 'resuelto', 2, 1, 29),
            ('El portátil se sobrecalienta y se apaga en plena reunión',
             'El portátil se apaga por sobrecalentamiento en reuniones largas y el ventilador gira a máxima velocidad. Se desmontó el equipo, se cambió la pasta térmica, se limpió el disipador con aire comprimido y se limitó la potencia máxima del procesador al 85 por ciento. Temperaturas normales verificadas.',
             1, 2, 'resuelto', 1, 1, 26),
            ('Accesos al sistema de nómina para el área de RRHH',
             'El área de RRHH necesita accesos al sistema de nómina para dos analistas nuevas del departamento. Se crearon los perfiles con el rol de consulta, se validaron los permisos de los módulos requeridos y se documentaron las credenciales en la bóveda corporativa. Accesos activos y probados.',
             4, 3, 'cerrado', 2, 1, 23),
            ('Los auriculares Bluetooth no emparejan con el equipo',
             'Los auriculares Bluetooth no emparejan con el equipo aunque aparecen en modo de emparejamiento. Se reinstaló la pila Bluetooth del chipset, se eliminó el emparejamiento previo dañado y se actualizó el driver de radio del fabricante. Emparejamiento estable con audio y micrófono.',
             1, 4, 'resuelto', 1, 1, 20),
            ('Antivirus alerta cifrado sospechoso en la carpeta de descargas',
             'El antivirus disparó alertas de cifrado sospechoso en la carpeta de descargas con archivos renombrados. Se aisló el equipo de la red de inmediato y la revisión confirmó un falso positivo del simulador de cifrado del antivirus. Se actualizó el motor, se restauraron los archivos desde la cuarentena y se documentó el procedimiento de respuesta.',
             5, 1, 'resuelto', 2, 1, 17),
            ('El sistema de tickets no envía las notificaciones por correo',
             'El sistema de tickets dejó de enviar las notificaciones por correo tras el cambio de la contraseña del buzón de servicio. Se actualizó la credencial en la configuración SMTP, se probó el envío de prueba y se agendó la rotación documentada de la contraseña. Notificaciones fluyendo.',
             2, 2, 'resuelto', 1, 1, 14),
            ('La tablet de inventario no sincroniza con el servidor',
             'La tablet de inventario no sincroniza los conteos con el servidor y muestra el stock desactualizado en el almacén. Se verificó que el certificado del agente de sincronización estaba vencido, se renovó y se reprogramó la tarea nocturna que quedó deshabilitada. Sincronización diaria verificada.',
             1, 3, 'resuelto', 2, 1, 11),
            ('El proyector de la sala de juntas no detecta el portátil',
             'El proyector de la sala de juntas no detecta el portátil por HDMI y la pantalla queda con el mensaje sin señal. Se probó con otro cable, se forzó la salida de video duplicada en la configuración de pantalla y se actualizó el firmware del proyector. Proyección funcionando para las reuniones.',
             1, 3, 'resuelto', 1, 1, 8),
            ('Windows pide activación tras el cambio de placa base',
             'Windows marca el equipo como no auténtico y pide activación tras la reparación con cambio de placa base. Se reactivó la licencia digital por teléfono con el ID de instalación, se vinculó la cuenta corporativa y se documentó el número de serie del equipo. Licencia activada de forma permanente.',
             2, 3, 'cerrado', 1, 1, 6),
            ('El correo corporativo llega con retraso de horas al celular',
             'El correo corporativo llega al celular con retrasos de varias horas y las notificaciones se acumulan de golpe. La app quedó con la sincronización en modo manual tras su última actualización. Se configuró la sincronización push, se amplió el plazo de retención de correos y se actualizó la app del proveedor. Notificaciones en tiempo real.',
             2, 4, 'resuelto', 2, 1, 4),
            ('Solicitud de monitor adicional para estación de diseño',
             'El área de diseño solicita un monitor adicional para trabajar con doble pantalla en las maquetas. Se cotizó el modelo compatible con la estación, se instaló en la salida DisplayPort, se configuró la resolución nativa y se actualizó el inventario de activos. Estación con doble pantalla operativa.',
             1, 4, 'cerrado', 1, 1, 2),
            ('El portátil se queda sin batería muy rápido',
             'La batería del portátil apenas dura 40 minutos tras un año de uso y avisa de carga baja constantemente. Se midió el desgaste con la herramienta del fabricante y la salud estaba al 45 por ciento. Se ajustó el plan de energía, se actualizó el firmware de gestión y se sustituyó la batería por una nueva. Autonomía de 4 horas verificada.',
             1, 3, 'resuelto', 1, 1, 64),
            ('No puedo acceder al portal de proveedores desde la oficina',
             'El portal web de proveedores no carga desde la red corporativa aunque sí desde el móvil. El proxy web tenía un certificado SSL caducado que rompía la validación. Se renovó el certificado del proxy, se actualizó la lista de exclusión y se verificó el acceso desde varios puestos.',
             3, 3, 'resuelto', 2, 1, 62),
            ('El servidor de archivos está lleno y no permite guardar',
             'Los usuarios no pueden guardar documentos porque el volumen de datos alcanzó el 100 por ciento. Se archivaron 400 GB de proyectos antiguos a almacenamiento frío, se amplió el volumen en 1 TB y se configuró una alerta al 85 por ciento de uso.',
             2, 2, 'resuelto', 1, 1, 59),
            ('Teams no carga el historial de chats',
             'Microsoft Teams no muestra el historial de conversaciones y se queda en la pantalla de carga. Se limpió la caché de la aplicación, se cerró la sesión y se volvió a iniciar, y se actualizó el cliente. El historial apareció completo.',
             2, 4, 'resuelto', 1, 1, 57),
            ('La impresora multifunción no escanea a correo',
             'La multifunción de Dirección escanea pero los correos nunca llegan al destino. La cuenta SMTP configurada tenía la contraseña caducada. Se actualizó la credencial en el panel de la impresora, se probó el envío y se documentó la rotación de la contraseña del buzón de servicio.',
             1, 3, 'cerrado', 2, 1, 54),
            ('Solicitud de alta de correo para práctica',
             'Se solicita el alta de correo corporativo para un estudiante en prácticas de Marketing con vigencia de tres meses. Se creó la cuenta con buzón reducido, acceso a la carpeta compartida del área y una tarea programada para su baja automática al finalizar el periodo.',
             4, 4, 'cerrado', 1, 1, 51),
            ('El ratón inalámbrico se desconecta intermitentemente',
             'El ratón inalámbrico pierde la conexión cada pocos minutos y el puntero da saltos. Se cambió la pila por una alcalina nueva, se reubicó el receptor USB con un alargador para evitar interferencias del monitor y se actualizó el driver. Uso estable.',
             1, 4, 'resuelto', 1, 1, 49),
            ('La base de datos reporta lentitud en horario pico',
             'La aplicación de gestión consulta muy lento entre las 9 y las 11 de la mañana. Se detectó falta de índices en las consultas más frecuentes y estadísticas desactualizadas. Se crearon dos índices, se ejecutó el mantenimiento de estadísticas y se verificó la mejora con el plan de ejecución.',
             2, 2, 'resuelto', 2, 1, 46),
            ('No se puede iniciar sesión en Windows por error de perfil',
             'Al iniciar sesión Windows informa de que el perfil de usuario no se puede cargar. Se reparó el perfil dañado con una cuenta temporal, se copiaron los datos del perfil corrupto y se recreó el perfil de dominio. El usuario ya inicia sesión con normalidad.',
             2, 3, 'resuelto', 1, 1, 44),
            ('El certificado de la web interna está caducado',
             'La intranet interna muestra un aviso de certificado caducado y los navegadores bloquean el acceso. Se renovó el certificado wildcard del servidor web, se instaló la cadena completa y se reinició el servicio. Acceso seguro restablecido sin avisos.',
             3, 2, 'cerrado', 2, 1, 41),
            ('El repositorio Git corporativo rechaza el push',
             'El desarrollador no puede subir cambios porque el push al repositorio interno falla con un error de autenticación. La clave SSH había sido revocada al cambiar de equipo. Se generó un nuevo par de claves, se registró la clave pública en el servidor Git y se probó un push de prueba.',
             2, 3, 'resuelto', 1, 1, 38),
            ('La VPN se desconecta cada 30 minutos',
             'La conexión VPN se corta cada media hora y obliga a reconectar. El router doméstico aplicaba un tiempo de inactividad bajo. Se amplió el tiempo de concesión del cliente, se habilitó el keepalive en la configuración y se actualizó el cliente VPN. Sesión estable durante toda la jornada.',
             3, 3, 'resuelto', 2, 1, 36),
            ('El escáner de huellas no valida el acceso',
             'El lector biométrico de la entrada no valida las huellas y obliga a usar tarjeta. Se limpió el sensor con el kit homologado, se actualizó el firmware y se volvieron a enrolar las plantillas de los usuarios afectados. Validación biométrica restablecida.',
             1, 3, 'resuelto', 1, 1, 33),
            ('Los informes de Power BI no se actualizan',
             'Los paneles de Power BI muestran datos antiguos porque la actualización programada falla por credenciales caducadas del origen de datos. Se actualizaron las credenciales en el gateway de datos corporativo y se relanzó la actualización programada. Datos al día verificados.',
             2, 3, 'cerrado', 2, 1, 30),
            ('El teléfono IP no marca tono',
             'El teléfono IP de recepción no marca tono ni recibe llamadas aunque la pantalla enciende. Se verificó el cableado PoE, se reasignó la extensión en la centralita y se reinició el teléfono. Llamadas entrantes y salientes funcionando.',
             3, 4, 'resuelto', 1, 1, 27),
            ('Solicitud de segundo monitor para analista',
             'Un analista de datos solicita un segundo monitor para revisar tableros complejos. Se verificó la salida de video disponible, se instaló el monitor configurado a la resolución nativa y se registró en el inventario de activos. Puesto con doble pantalla operativo.',
             1, 4, 'cerrado', 1, 1, 24),
            ('El antivirus bloquea un ejecutable del sistema de gestión',
             'El antivirus pone en cuarentena un componente del sistema de gestión y la aplicación deja de abrir. La firma del nuevo parche coincidía con un falso positivo. Se añadió una exclusión firmada por el fabricante, se restauró el archivo desde la cuarentena y se documentó el cambio.',
             2, 2, 'resuelto', 2, 1, 21),
            ('La carpeta de red tarda en abrir desde la sucursal',
             'Abrir la carpeta compartida desde la sucursal tarda más de un minuto por el enlace WAN saturado en horario laboral. Se habilitó el almacenamiento en caché sin conexión en los equipos de la sucursal y se priorizó el tráfico SMB en el QoS del router. Apertura casi instantánea.',
             3, 3, 'resuelto', 1, 1, 17),
            ('El teclado del portátil tiene teclas que no responden',
             'Varias teclas del portátil no responden correctamente después de un derrame leve de líquido. Se usó un teclado USB externo como solución temporal y, tras confirmar el daño del teclado integrado, se reemplazó el módulo. Escritura restablecida.',
             1, 3, 'resuelto', 2, 1, 12),
            ('Fallo al imprimir la nómina mensual por desbordamiento',
             'El proceso de impresión de la nómina mensual falla a mitad por falta de memoria en el servidor de impresión. Se amplió el spooler, se dividió el lote en tandas y se programó la impresión fuera del horario pico. Nómina impresa completa y verificada.',
             2, 1, 'cerrado', 1, 1, 8)
        -- agente: 1 = agente base, 2 = coordinador | soli: 1 = solicitante del seed
        ) AS t(asunto, descripcion, cat, prio, estado, agente, soli, dias)
    LOOP
        v_resolver := CASE WHEN fila.agente = 2 THEN v_ag2 ELSE v_ag1 END;

        INSERT INTO solicitud (asunto, descripcion, estado, id_categoria, id_prioridad,
                               id_solicitante, id_agente_asignado, fecha_creacion, fecha_actualizacion)
        VALUES (fila.asunto, fila.descripcion, fila.estado, fila.cat, fila.prio,
                v_soli, v_resolver,
                NOW() - (fila.dias || ' days')::interval,
                NOW() - GREATEST(fila.dias - 3, 1) * interval '1 day')
        RETURNING id_solicitud INTO v_id;

        INSERT INTO historial (id_solicitud, estado_anterior, estado_nuevo, comentario, fecha, id_usuario)
        VALUES
            (v_id, NULL, 'nuevo', 'Ticket creado',
             NOW() - (fila.dias || ' days')::interval, v_soli),
            (v_id, 'nuevo', 'asignado', 'Ticket asignado por coordinador',
             NOW() - (GREATEST(fila.dias - 1, 2) || ' days')::interval, v_ag2),
            (v_id, 'asignado', 'en_proceso', 'Movido en tablero',
             NOW() - (GREATEST(fila.dias - 2, 1) * interval '1 day'), v_resolver),
            (v_id, 'en_proceso', fila.estado, 'Solución aplicada y validada',
             NOW() - GREATEST(fila.dias - 3, 1) * interval '1 day', v_resolver);
    END LOOP;

    RAISE NOTICE 'Mocks insertados correctamente';
END $$;

-- ---------- Verificación ----------
SELECT estado, count(*) FROM solicitud GROUP BY estado ORDER BY estado;
SELECT 'historial de mocks' AS detalle, count(*) FROM historial WHERE id_solicitud IN (
    SELECT id_solicitud FROM solicitud WHERE estado IN ('resuelto', 'cerrado')
);
