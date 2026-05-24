import os
import json
import threading
import time
from datetime import datetime, timedelta, timezone
import logging
import hmac
import hashlib
from concurrent.futures import ThreadPoolExecutor
from collections import defaultdict
from flask import Flask, request, jsonify
from supabase import create_client, Client
import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry
from dotenv import load_dotenv
from cerebro_ia import procesar_promo_boss, generar_respuesta_rescate, generar_respuesta_ventas, generar_respuesta_seguimiento

# Configuración de Logging de producción
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] (%(filename)s:%(lineno)d) - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger("BotMecanico")

# Ignición del Entorno
load_dotenv()
app = Flask(__name__)

# Extracción de Variables Críticas
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")
NUMERO_JEFE = os.getenv("NUMERO_JEFE")
WHATSAPP_APP_SECRET = os.getenv("WHATSAPP_APP_SECRET")

# Configuración del Pool de Conexiones HTTP
http_session = requests.Session()
retries = Retry(total=3, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
http_session.mount("https://", HTTPAdapter(pool_connections=20, pool_maxsize=40, max_retries=retries))

# Pool de Hilos para procesar webhooks de manera controlada
MAX_WORKERS = int(os.getenv("MAX_WORKERS", "10"))
webhook_executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)

# Limitadores de Tasa (Rate Limiters) thread-safe
class InMemoryRateLimiter:
    def __init__(self, requests_limit, period_seconds):
        self.limit = requests_limit
        self.period = period_seconds
        self.history = defaultdict(list)
        self.lock = threading.Lock()

    def is_allowed(self, key):
        now = time.time()
        with self.lock:
            self.history[key] = [t for t in self.history[key] if now - t < self.period]
            if len(self.history[key]) < self.limit:
                self.history[key].append(now)
                return True
            return False

ip_rate_limiter = InMemoryRateLimiter(requests_limit=60, period_seconds=60)
wa_rate_limiter = InMemoryRateLimiter(requests_limit=15, period_seconds=60)

def verificar_firma_whatsapp(payload_bytes, signature_header):
    """Verifica criptográficamente que el webhook provenga de Meta utilizando el App Secret."""
    if not WHATSAPP_APP_SECRET:
        logger.warning("🔒 [SEGURIDAD] WHATSAPP_APP_SECRET no está configurado. Omisión temporal de validación de firma.")
        return True
    if not signature_header or not signature_header.startswith("sha256="):
        logger.error("🔒 [SEGURIDAD] Cabecera X-Hub-Signature-256 ausente o inválida.")
        return False
    
    signature = signature_header[7:]
    expected_signature = hmac.new(
        WHATSAPP_APP_SECRET.encode('utf-8'),
        payload_bytes,
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(signature, expected_signature)

# Conexión a la Matriz de Datos
supabase: Client = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

# --- EXTRACCIÓN DE LA MATRIZ DE AUTORIDAD ---
try:
    auth_data = supabase.table('config_empresa').select('*').eq('ruc', '20610576002').execute()
    DATOS_EMPRESA = auth_data.data[0]
except Exception as e:
    logger.error(f"⚠️ [ALERTA] Fallo al extraer datos de autoridad de Supabase: {e}")
    DATOS_EMPRESA = {"nombre_empresa": "MzTech", "web_url": "[https://manzanotech.com/](https://manzanotech.com/)", "ruc": "20610576002", "fecha_fundacion": "2023-02-20"}

# ==========================================
# EL RELOJ CUÁNTICO (MOTOR ASÍNCRONO)
# ==========================================
def motor_seguimiento_asincrono():
    """Hilo infinito que vigila a los clientes inactivos y dispara el retargeting de 30 minutos."""
    while True:
        try:
            ahora = datetime.now(timezone.utc).isoformat()
            tareas = supabase.table('cola_mensajes').select('*').eq('is_processed', False).lte('ejecutar_en', ahora).execute()
            
            for tarea in tareas.data:
                telefono = tarea['customer_phone']
                fase = tarea['fase_programada']
                id_tarea = tarea['id']
                
                try:
                    bloqueo = supabase.table('cola_mensajes').update({'is_processed': True}).eq('id', id_tarea).eq('is_processed', False).execute()
                    if not bloqueo.data:
                        continue
                except Exception as e:
                    logger.error(f"⚠️ [RELOJ CUÁNTICO] Error al intentar bloquear la tarea {id_tarea}: {e}")
                    continue
                
                catalogo = supabase.table('campaigns').select('nombre_producto').eq('is_active', True).execute()
                nombres_activos = [prod['nombre_producto'] for prod in catalogo.data] if catalogo.data else "nuestro catálogo completo"
                
                mensaje_retargeting = generar_respuesta_seguimiento(fase, nombres_activos)
                if mensaje_retargeting:
                    enviar_mensaje(telefono, mensaje_retargeting)
                    logger.info(f"🎯 [RETARGETING] Mensaje asíncrono enviado a {telefono}")
                
        except Exception as e:
            logger.error(f"⚠️ [RELOJ CUÁNTICO] Interferencia en el motor asíncrono: {e}")
            
    time.sleep(60)

hilo_reloj = threading.Thread(target=motor_seguimiento_asincrono, daemon=True)
hilo_reloj.start()

# ==========================================
# VÁLVULA DE SUPERVIVENCIA (UPTIMEROBOT)
# ==========================================
@app.route('/ping', methods=['GET'])
def mantener_vivo():
    ip_cliente = request.remote_addr or "unknown_ip"
    if not ip_rate_limiter.is_allowed(ip_cliente):
        logger.warning(f"🚫 [RATE LIMIT] Peticiones IP excedidas para ping: {ip_cliente}")
        return jsonify({"error": "Demasiadas peticiones"}), 429
    try:
        supabase.table('campaigns').select('id').limit(1).execute()
        return "¡Reactor LarvaDev latiendo a 120 BPM!", 200
    except Exception as e:
        logger.error(f"⚠️ [PING ERROR] Error al interactuar con base de datos: {e}")
        return "¡Reactor LarvaDev experimentando fallos de red!", 500

# ==========================================
# COMPUERTA DE TELEMETRÍA (META WEBHOOK)
# ==========================================
@app.route('/webhook', methods=['GET', 'POST'])
def webhook_whatsapp():
    if request.method == 'GET':
        if request.args.get("hub.verify_token") == VERIFY_TOKEN:
            return request.args.get("hub.challenge"), 200
        return "Acceso denegado", 403

    if request.method == 'POST':
        ip_cliente = request.remote_addr or "unknown_ip"
        
        if not ip_rate_limiter.is_allowed(ip_cliente):
            logger.warning(f"🚫 [RATE LIMIT] IP bloqueada temporalmente: {ip_cliente}")
            return jsonify({"error": "Demasiadas peticiones"}), 429
        
        raw_payload = request.get_data()
        signature = request.headers.get("X-Hub-Signature-256")
        if not verificar_firma_whatsapp(raw_payload, signature):
            logger.warning(f"🔒 [SEGURIDAD] Firma de webhook inválida desde la IP: {ip_cliente}")
            return jsonify({"error": "Acceso denegado. Firma inválida."}), 401
        
        try:
            data = json.loads(raw_payload.decode('utf-8'))
            logger.info(f"📥 [PAYLOAD RECIBIDO]: {json.dumps(data)}")
        except Exception as e:
            logger.error(f"⚠️ [JSON ERROR] Error de parseo en webhook desde IP {ip_cliente}: {e}")
            return jsonify({"error": "JSON malformado"}), 400
            
        try:
            entry = data.get('entry')
            if entry and len(entry) > 0:
                changes = entry[0].get('changes')
                if changes and len(changes) > 0:
                    cambios = changes[0].get('value', {})
                    messages = cambios.get('messages')
                    if messages and len(messages) > 0:
                        mensaje_info = messages[0]
                        numero_origen = mensaje_info.get('from')
                        
                        if numero_origen:
                            if not wa_rate_limiter.is_allowed(numero_origen):
                                logger.warning(f"🚫 [RATE LIMIT] Mensajes de WhatsApp excedidos para {numero_origen}. Ignorando.")
                                return jsonify({"status": "rate_limited"}), 200
                            
                            logger.info(f"🚀 [DESPACHADOR] Enrutando mensaje de {numero_origen} al executor.")
                            webhook_executor.submit(enrutador_mecanico, numero_origen, mensaje_info, cambios)
        except Exception as e:
            logger.error(f"⚠️ [WEBHOOK ERROR] Excepción al procesar webhook: {e}", exc_info=True)
            
        return jsonify({"status": "ok"}), 200

# ==========================================
# FUNCIONES DE TRANSMISIÓN (BRAZOS ROBÓTICOS)
# ==========================================
def enviar_mensaje(numero_destino, texto):
    url = f"[https://graph.facebook.com/v25.0/](https://graph.facebook.com/v25.0/){PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
    payload = {"messaging_product": "whatsapp", "to": numero_destino, "type": "text", "text": {"body": texto}}
    try:
        respuesta = http_session.post(url, headers=headers, json=payload, timeout=5)
        if respuesta.status_code == 200:
            return True
        logger.error(f"❌ [WHATSAPP API] Error al enviar mensaje: {respuesta.status_code} - {respuesta.text}")
    except Exception as e:
        logger.error(f"❌ [WHATSAPP API] Excepción al enviar mensaje a {numero_destino}: {e}")
    return False

def reenviar_imagen(numero_destino, image_id, caption):
    url = f"[https://graph.facebook.com/v25.0/](https://graph.facebook.com/v25.0/){PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
    payload = {
        "messaging_product": "whatsapp", "to": numero_destino, "type": "image",
        "image": {"id": image_id, "caption": caption}
    }
    try:
        respuesta = http_session.post(url, headers=headers, json=payload, timeout=5)
        if respuesta.status_code == 200:
            return True
        logger.error(f"❌ [WHATSAPP API] Error al reenviar imagen: {respuesta.status_code} - {respuesta.text}")
    except Exception as e:
        logger.error(f"❌ [WHATSAPP API] Excepción al reenviar imagen a {numero_destino}: {e}")
    return False

# ==========================================
# EL NÚCLEO LÓGICO
# ==========================================
def enrutador_mecanico(numero_origen, mensaje_info, cambios):
    try:
        tipo_mensaje = mensaje_info.get('type')
        
        nombre_usuario = "Usuario"
        contacts = cambios.get('contacts')
        if contacts and len(contacts) > 0:
            profile = contacts[0].get('profile')
            if profile:
                nombre_usuario = profile.get('name', "Usuario")

        # ---------------------------------------------------------
        # RADAR DE VOUCHERS (IMÁGENES)
        # ---------------------------------------------------------
        if tipo_mensaje == 'image':
            image_id = mensaje_info['image']['id']
            enviar_mensaje(numero_origen, "¡Comprobante detectado en el escáner! 🧾 Procesando validación...")
            
            if numero_origen != NUMERO_JEFE:
                supabase.table('cola_mensajes').update({'is_processed': True}).eq('customer_phone', numero_origen).eq('is_processed', False).execute()
                supabase.table('orders').update({
                    "status": "verificando_voucher", 
                    "voucher_image_id": image_id
                }).eq('customer_phone', numero_origen).eq('status', 'pendiente_pago').execute()
                
                orden_pendiente = supabase.table('orders').select('token_aprobacion').eq('customer_phone', numero_origen).eq('status', 'verificando_voucher').execute()
                
                if orden_pendiente.data:
                    token = orden_pendiente.data[0]['token_aprobacion']
                    enviar_mensaje(NUMERO_JEFE, f"💰 [REVISIÓN DE PAGO] \nEl cliente {nombre_usuario} acaba de enviar un voucher.\n\nPara confirmar escribe:\n#PAGO_OK {token}\n\nPara denegar escribe:\n#PAGO_FAIL {token}")
                    reenviar_imagen(NUMERO_JEFE, image_id, "Voucher recibido del cliente.")
                else:
                    enviar_mensaje(NUMERO_JEFE, f"⚠️ [IMAGEN HUÉRFANA] El cliente {nombre_usuario} envió esta foto, pero no tiene órdenes pendientes de pago en el sistema.")
                    reenviar_imagen(NUMERO_JEFE, image_id, "Imagen sin orden asociada.")
            return

        if tipo_mensaje != 'text':
            return

        texto_recibido = mensaje_info['text']['body'].strip()
        texto_lower = texto_recibido.lower()

        # ---------------------------------------------------------
        # VÁLVULA DEL ADMINISTRADOR (EL BOSS)
        # ---------------------------------------------------------
        if numero_origen == NUMERO_JEFE:
            if texto_recibido == "#INICIAR_TURNO":
                enviar_mensaje(NUMERO_JEFE, "✅ [SISTEMA] Ventana cuántica de 24 horas abierta.")
            elif texto_recibido.startswith("#NUEVA_PROMO:"):
                texto_crudo = texto_recibido.replace("#NUEVA_PROMO:", "").strip()
                enviar_mensaje(NUMERO_JEFE, "⚙️ [SISTEMA] Procesando texto con IA. Sintetizando catálogo...")
                datos_json = procesar_promo_boss(texto_crudo)
                if datos_json:
                    try:
                        supabase.table('campaigns').upsert({
                            "nombre_producto": datos_json['nombre_producto'],
                            "texto_crudo": texto_crudo,
                            "datos_estructurados": datos_json,
                            "is_active": True
                        }).execute()
                        enviar_mensaje(NUMERO_JEFE, f"✅ [ÉXITO] Producto '{datos_json['nombre_producto']}' guardado. Precio Oferta: S/{datos_json['precio_oferta']}")
                    except Exception as e:
                        enviar_mensaje(NUMERO_JEFE, f"❌ [ERROR DB] Fallo al inyectar en Supabase: {e}")
                else:
                    enviar_mensaje(NUMERO_JEFE, "❌ [ERROR IA] Los núcleos cognitivos colapsaron. Revisa tu saldo de API.")
            elif texto_recibido.startswith("#PAGO_OK "):
                token = texto_recibido.replace("#PAGO_OK ", "").strip()
                orden = supabase.table('orders').update({"status": "confirmado"}).eq('token_aprobacion', token).eq('status', 'verificando_voucher').execute()
                if orden.data:
                    celular_cliente = orden.data[0]['customer_phone']
                    enviar_mensaje(celular_cliente, "✅ ¡Pago confirmado exitosamente! 🎉 Por favor, envíanos tu dirección de entrega y distrito para programar el envío.")
                    enviar_mensaje(NUMERO_JEFE, f"✅ Orden {token} confirmada. El cliente ha sido notificado.")
                else:
                    enviar_mensaje(NUMERO_JEFE, f"❌ No se encontró una orden pendiente con el token {token}.")
            elif texto_recibido.startswith("#PAGO_FAIL "):
                token = texto_recibido.replace("#PAGO_FAIL ", "").strip()
                orden = supabase.table('orders').update({"status": "denegado"}).eq('token_aprobacion', token).eq('status', 'verificando_voucher').execute()
                if orden.data:
                    celular_cliente = orden.data[0]['customer_phone']
                    enviar_mensaje(celular_cliente, "⚠️ Tuvimos un problema verificando tu captura de pago. Por favor, revisa tu transferencia o envíanos un comprobante más nítido.")
                    enviar_mensaje(NUMERO_JEFE, f"🚫 Orden {token} denegada. El cliente fue notificado.")
            elif texto_recibido.startswith("#PROMO_TERMINADA:"):
                producto_a_borrar = texto_recibido.replace("#PROMO_TERMINADA:", "").strip()
                try:
                    supabase.table('campaigns').update({"is_active": False}).ilike("nombre_producto", f"%{producto_a_borrar}%").execute()
                    enviar_mensaje(NUMERO_JEFE, f"🗑️ [SISTEMA] La campaña de '{producto_a_borrar}' ha sido desactivada (Soft Delete).")
                except Exception as e:
                    enviar_mensaje(NUMERO_JEFE, f"❌ [ERROR DB] Fallo en la desactivación: {e}")
            return

        # ---------------------------------------------------------
        # VÁLVULA DEL CLIENTE (EMBUDO CRM HÍBRIDO)
        # ---------------------------------------------------------
        if numero_origen != NUMERO_JEFE:
            supabase.table('cola_mensajes').update({'is_processed': True}).eq('customer_phone', numero_origen).eq('is_processed', False).execute()
            
            cliente_db = supabase.table('clientes').select('*').eq('phone', numero_origen).execute()
            fase_resultante = 1 
            
            if not cliente_db.data:
                supabase.table('clientes').insert({'phone': numero_origen, 'name': nombre_usuario, 'fase_actual': 1}).execute()
                msg_bienvenida = (
                    f"¡Hola {nombre_usuario}! 👋 Bienvenido/a a {DATOS_EMPRESA['nombre_empresa']}.\n"
                    f"Respaldados con RUC: {DATOS_EMPRESA['ruc']} | Web: {DATOS_EMPRESA['web_url']}\n\n"
                    f"Gracias por escribirnos 😊. ¿Sobre qué producto deseas información?"
                )
                enviar_mensaje(numero_origen, msg_bienvenida)
                fase_resultante = 1
                
            else:
                fase = cliente_db.data[0]['fase_actual']
                supabase.table('clientes').update({'ultimo_mensaje_at': 'now()'}).eq('phone', numero_origen).execute()

                if texto_lower.startswith("comprar "):
                    try:
                        articulo = texto_lower.replace("comprar ", "").strip()
                        token = numero_origen[-4:]
                        
                        supabase.table('orders').insert({
                            "customer_phone": numero_origen, "product_name": articulo, "token_aprobacion": token
                        }).execute()
                        
                        enviar_mensaje(numero_origen, f"📦 Separando tu: *{articulo}*.\nPor favor, Yapea al 999-999-999 y envíanos la *foto de la captura* por aquí para validar.")
                        enviar_mensaje(NUMERO_JEFE, f"🔔 [NUEVA ORDEN - ESPERANDO PAGO]\nCliente: {nombre_usuario}\nProducto: {articulo}\nToken de validación: {token}")
                        fase_resultante = 5 
                    except Exception as e:
                        logger.error(f"❌ [ERROR FATAL DE TRANSACCIÓN]: {e}")
                        enviar_mensaje(numero_origen, "⚠️ Ocurrió una anomalía temporal en la matriz de pedidos. ¡Por favor, intenta escribir tu pedido una vez más!")
                        fase_resultante = fase
                else:
                    promo_activa = supabase.table('campaigns').select('*').eq('is_active', True).execute()
                    
                    if promo_activa.data:
                        datos_producto = promo_activa.data[0]['datos_estructurados']
                        nombre_prod = promo_activa.data[0]['nombre_producto']
                        
                        respuesta_ia = generar_respuesta_ventas(texto_recibido, fase, datos_producto, nombre_prod)
                        
                        if respuesta_ia:
                            fase_resultante = respuesta_ia.get("fase_siguiente", fase)
                            intencion = respuesta_ia.get("intencion_detectada", "").lower()
                            
                            if fase_resultante == 5 or "comprar" in intencion:
                                try:
                                    token = numero_origen[-4:]
                                    supabase.table('orders').insert({
                                        "customer_phone": numero_origen, "product_name": nombre_prod, "token_aprobacion": token
                                    }).execute()
                                    
                                    supabase.table('clientes').update({'fase_actual': 5}).eq('phone', numero_origen).execute()
                                    enviar_mensaje(numero_origen, f"📦 ¡Excelente decisión! Separando tu: *{nombre_prod}*.\nPor favor, Yapea al 999-999-999 y envíanos la *foto de la captura* por aquí para validar tu compra.")
                                    enviar_mensaje(NUMERO_JEFE, f"🔔 [NUEVA ORDEN - ESPERANDO PAGO]\nCliente: {nombre_usuario}\nProducto: {nombre_prod}\nToken de validación: {token}")
                                    fase_resultante = 5
                                except Exception as e:
                                    logger.error(f"❌ [ERROR FATAL DE TRANSACCIÓN AUTOMÁTICA]: {e}")
                                    enviar_mensaje(numero_origen, "⚠️ Ocurrió una anomalía al procesar tu pedido. ¡Intenta escribir 'comprar' nuevamente!")
                                    fase_resultante = fase
                            else:
                                mensaje_ia = respuesta_ia.get("mensaje_convincente", "¡Hola! ¿En qué te puedo ayudar hoy?")
                                supabase.table('clientes').update({'fase_actual': fase_resultante}).eq('phone', numero_origen).execute()
                                enviar_mensaje(numero_origen, mensaje_ia)
                        else:
                            enviar_mensaje(numero_origen, generar_respuesta_rescate(texto_recibido))
                            fase_resultante = fase
                    else:
                        enviar_mensaje(numero_origen, "En este momento estamos actualizando nuestro catálogo. ¡Vuelve en unos minutos!")
                        fase_resultante = fase

            # REPROGRAMACIÓN AUTOMÁTICA DEL SEGUIMIENTO
            if fase_resultante < 5:
                tiempo_ejecucion = (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat()
                supabase.table('cola_mensajes').insert({
                    'customer_phone': numero_origen,
                    'fase_programada': fase_resultante,
                    'ejecutar_en': tiempo_ejecucion
                }).execute()
                
    except Exception as e:
        logger.error(f"⚠️ [ENRUTADOR MECÁNICO ERROR] Error procesando mensaje de {numero_origen}: {e}", exc_info=True)

if __name__ == '__main__':
    app.run(port=5000)