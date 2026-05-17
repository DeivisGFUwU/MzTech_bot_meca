import os
import threading
from flask import Flask, request, jsonify
from supabase import create_client, Client
import requests
from dotenv import load_dotenv

# Ignición del Entorno
load_dotenv()
app = Flask(__name__)

# Extracción de Variables Críticas
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")
NUMERO_JEFE = os.getenv("NUMERO_JEFE")

# Conexión a la Matriz de Datos
supabase: Client = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

# ==========================================
# VÁLVULA DE SUPERVIVENCIA (UPTIMEROBOT)
# ==========================================
@app.route('/ping', methods=['GET'])
def mantener_vivo():
    supabase.table('campaigns').select('id').limit(1).execute()
    return "¡Reactor LarvaDev latiendo a 120 BPM!", 200

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
        data = request.get_json()
        try:
            cambios = data['entry'][0]['changes'][0]['value']
            if 'messages' in cambios:
                mensaje_info = cambios['messages'][0]
                numero_origen = mensaje_info['from']
                
                # Despachador Asíncrono para evitar colapso térmico por Timeout
                hilo = threading.Thread(target=enrutador_mecanico, args=(numero_origen, mensaje_info, cambios))
                hilo.start()
        except Exception as e:
            pass
        return jsonify({"status": "ok"}), 200

# ==========================================
# FUNCIONES DE TRANSMISIÓN (BRAZOS ROBÓTICOS)
# ==========================================
def enviar_mensaje(numero_destino, texto):
    url = f"https://graph.facebook.com/v25.0/{PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
    payload = {"messaging_product": "whatsapp", "to": numero_destino, "type": "text", "text": {"body": texto}}
    requests.post(url, headers=headers, json=payload)

def reenviar_imagen(numero_destino, image_id, caption):
    url = f"https://graph.facebook.com/v25.0/{PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
    payload = {
        "messaging_product": "whatsapp", "to": numero_destino, "type": "image",
        "image": {"id": image_id, "caption": caption}
    }
    requests.post(url, headers=headers, json=payload)

# ==========================================
# EL NÚCLEO LÓGICO
# ==========================================
def enrutador_mecanico(numero_origen, mensaje_info, cambios):
    tipo_mensaje = mensaje_info.get('type')
    nombre_usuario = cambios['contacts'][0]['profile']['name']

    # ---------------------------------------------------------
    # RADAR DE VOUCHERS (IMÁGENES)
    # ---------------------------------------------------------
    if tipo_mensaje == 'image':
        image_id = mensaje_info['image']['id']
        enviar_mensaje(numero_origen, "¡Comprobante detectado en el escáner! 🧾 Procesando validación...")
        
        # Alerta directa al Boss (Solo funciona gratis si la ventana de 24h está abierta)
        reenviar_imagen(NUMERO_JEFE, image_id, f"⚠️ NUEVO PAGO RECIBIDO\nCliente: {nombre_usuario}\nNúmero: {numero_origen}")
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
            enviar_mensaje(NUMERO_JEFE, "✅ [SISTEMA] Ventana cuántica de 24 horas abierta. Envío de vouchers gratuito activado.")
        elif texto_recibido.startswith("#NUEVA_PROMO:"):
            nueva_promo = texto_recibido.replace("#NUEVA_PROMO:", "").strip()
            try:
                supabase.table('campaigns').update({"texto_promo": nueva_promo}).eq("id", 1).execute()
                enviar_mensaje(NUMERO_JEFE, "✅ [SISTEMA] Promoción inyectada en la base de datos.")
            except Exception as e:
                enviar_mensaje(NUMERO_JEFE, f"❌ Fallo en Supabase: {e}")
        return

    # ---------------------------------------------------------
    # VÁLVULA DEL CLIENTE (EMBUDO MECÁNICO)
    # ---------------------------------------------------------
    if texto_lower in ["hola", "buenas", "info", "menu"]:
        try:
            consulta = supabase.table('campaigns').select('texto_promo').eq('id', 1).execute()
            promo_actual = consulta.data[0]['texto_promo']
            respuesta = f"¡Hola {nombre_usuario}! Bienvenido a Manzano Tech. 🚀\n\n📢 {promo_actual}\n\nEscribe *comprar [producto]* para pedir."
            enviar_mensaje(numero_origen, respuesta)
        except:
            enviar_mensaje(numero_origen, "Hubo un corto circuito. ¡Intenta en un minuto!")
            
    elif texto_lower.startswith("comprar "):
        articulo = texto_lower.replace("comprar ", "").strip()
        try:
            supabase.table('orders').insert({
                "customer_phone": numero_origen, "customer_name": nombre_usuario, 
                "product_requested": articulo, "status": "pendiente"
            }).execute()
            
            enviar_mensaje(numero_origen, f"📦 Separando tu: *{articulo}*.\nYapea al 999-999-999 y envíanos la foto de la captura por aquí.")
            enviar_mensaje(NUMERO_JEFE, f"🔔 NUEVA ORDEN: {nombre_usuario} quiere {articulo}.")
        except:
            enviar_mensaje(numero_origen, "Anomalía al guardar tu pedido.")
    else:
        enviar_mensaje(numero_origen, "🤖 Comandos válidos: *hola* (ver ofertas) o *comprar [producto]*.")

if __name__ == '__main__':
    app.run(port=5000)