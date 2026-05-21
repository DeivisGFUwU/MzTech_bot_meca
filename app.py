import os
import threading
from flask import Flask, request, jsonify
from supabase import create_client, Client
import requests
from dotenv import load_dotenv
from cerebro_ia import procesar_promo_boss, generar_respuesta_rescate, generar_respuesta_ventas
import time # ¡Asegúrate de tener este import arriba en app.py!

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

# --- EXTRACCIÓN DE LA MATRIZ DE AUTORIDAD ---
try:
    auth_data = supabase.table('config_empresa').select('*').eq('ruc', '20610576002').execute()
    DATOS_EMPRESA = auth_data.data[0]
except Exception as e:
    print(f"⚠️ [ALERTA] Fallo al extraer datos de autoridad: {e}")
    DATOS_EMPRESA = {"nombre_empresa": "MzTech", "web_url": "https://manzanotech.com/", "ruc": "20610576002", "fecha_fundacion": "2023-02-20"}

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
# FUNCIONES DE TRANSMISIÓN (BRAZOS ROBÓTICOS BLINDADOS)
# ==========================================
def enviar_mensaje(numero_destino, texto):
    url = f"https://graph.facebook.com/v25.0/{PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
    payload = {"messaging_product": "whatsapp", "to": numero_destino, "type": "text", "text": {"body": texto}}
    
    for intento in range(3):
        try:
            # Timeout de 5 segundos para que el hilo no se quede congelado
            respuesta = requests.post(url, headers=headers, json=payload, timeout=5)
            if respuesta.status_code == 200:
                return True
        except Exception as e:
            print(f"⚠️ [RED META] Pérdida de paquetes en mensaje (Intento {intento+1}): {e}")
            time.sleep(1)
    return False

def reenviar_imagen(numero_destino, image_id, caption):
    url = f"https://graph.facebook.com/v25.0/{PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
    payload = {
        "messaging_product": "whatsapp", "to": numero_destino, "type": "image",
        "image": {"id": image_id, "caption": caption}
    }
    
    for intento in range(3):
        try:
            respuesta = requests.post(url, headers=headers, json=payload, timeout=5)
            if respuesta.status_code == 200:
                return True
        except Exception as e:
            print(f"⚠️ [RED META] Pérdida de paquetes en imagen (Intento {intento+1}): {e}")
            time.sleep(1)
    return False

# ==========================================
# EL NÚCLEO LÓGICO
# ==========================================
def enrutador_mecanico(numero_origen, mensaje_info, cambios):
    tipo_mensaje = mensaje_info.get('type')
    nombre_usuario = cambios['contacts'][0]['profile']['name']

    # ---------------------------------------------------------
    # RADAR DE VOUCHERS (IMÁGENES) - ¡AQUÍ ESTÁ LA PARTE 4!
    # ---------------------------------------------------------
    if tipo_mensaje == 'image':
        image_id = mensaje_info['image']['id']
        enviar_mensaje(numero_origen, "¡Comprobante detectado en el escáner! 🧾 Procesando validación...")
        
        if numero_origen != NUMERO_JEFE:
            # Actualizamos la última orden pendiente de este cliente
            supabase.table('orders').update({
                "status": "verificando_voucher", 
                "voucher_image_id": image_id
            }).eq('customer_phone', numero_origen).eq('status', 'pendiente_pago').execute()
            
            # Extraemos el token para enviárselo al Boss
            orden_pendiente = supabase.table('orders').select('token_aprobacion').eq('customer_phone', numero_origen).eq('status', 'verificando_voucher').execute()
            
            if orden_pendiente.data:
                token = orden_pendiente.data[0]['token_aprobacion']
                enviar_mensaje(NUMERO_JEFE, f"💰 [REVISIÓN DE PAGO] \nEl cliente {nombre_usuario} acaba de enviar un voucher.\n\nPara confirmar escribe:\n#PAGO_OK {token}\n\nPara denegar escribe:\n#PAGO_FAIL {token}")
                reenviar_imagen(NUMERO_JEFE, image_id, "Voucher recibido del cliente.")
            else:
                # Si el cliente manda una foto sin haber escrito "comprar" antes
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
        cliente_db = supabase.table('clientes').select('*').eq('phone', numero_origen).execute()
        
        # 1. Registro inicial / Cliente Nuevo (Fase 1)
        if not cliente_db.data:
            supabase.table('clientes').insert({'phone': numero_origen, 'name': nombre_usuario, 'fase_actual': 1}).execute()
            
            msg_bienvenida = (
                f"¡Hola {nombre_usuario}! 👋 Bienvenido/a a {DATOS_EMPRESA['nombre_empresa']}.\n"
                f"Respaldados con RUC: {DATOS_EMPRESA['ruc']} | Web: {DATOS_EMPRESA['web_url']}\n\n"
                f"Gracias por escribirnos 😊. ¿Sobre qué producto deseas información?"
            )
            enviar_mensaje(numero_origen, msg_bienvenida)
            return 
            
        else:
            fase = cliente_db.data[0]['fase_actual']
            supabase.table('clientes').update({'ultimo_mensaje_at': 'now()'}).eq('phone', numero_origen).execute()

            # 2. La Transacción Estricta (Mecánica Pura)
            if texto_lower.startswith("comprar "):
                try:
                    articulo = texto_lower.replace("comprar ", "").strip()
                    token = numero_origen[-4:]
                    
                    supabase.table('orders').insert({
                        "customer_phone": numero_origen, 
                        "product_name": articulo, 
                        "token_aprobacion": token
                    }).execute()
                    
                    enviar_mensaje(numero_origen, f"📦 Separando tu: *{articulo}*.\nPor favor, Yapea al 999-999-999 y envíanos la *foto de la captura* por aquí para validar.")
                    enviar_mensaje(NUMERO_JEFE, f"🔔 [NUEVA ORDEN - ESPERANDO PAGO]\nCliente: {nombre_usuario}\nProducto: {articulo}\nToken de validación: {token}")
                
                except Exception as e:
                    print(f"❌ [ERROR FATAL DE TRANSACCIÓN]: {e}")
                    enviar_mensaje(numero_origen, "⚠️ Ocurrió una anomalía temporal en la matriz de pedidos. ¡Por favor, intenta escribir tu pedido una vez más!")

            # 3. El Córtex de Ventas Persuasivo (LLM + JSON)
            else:
                promo_activa = supabase.table('campaigns').select('*').eq('is_active', True).execute()
                
                if promo_activa.data:
                    datos_producto = promo_activa.data[0]['datos_estructurados']
                    nombre_prod = promo_activa.data[0]['nombre_producto']
                    
                    # Invocamos el cerebro de ventas persuasivo para analizar el contexto
                    respuesta_ia = generar_respuesta_ventas(texto_recibido, fase, datos_producto, nombre_prod)
                    
                    if respuesta_ia:
                        nueva_fase = respuesta_ia.get("fase_siguiente", fase)
                        mensaje_ia = respuesta_ia.get("mensaje_convincente", "¡Hola! ¿En qué te puedo ayudar hoy?")
                        
                        # Guardamos el avance del estado del cliente en el CRM
                        supabase.table('clientes').update({'fase_actual': nueva_fase}).eq('phone', numero_origen).execute()
                        
                        # El bot ejecuta el mensaje persuasivo cargado de emojis
                        enviar_mensaje(numero_origen, mensaje_ia)
                    else:
                        # Red de Seguridad de Rescate si la inferencia JSON falla
                        enviar_mensaje(numero_origen, generar_respuesta_rescate(texto_recibido))
                else:
                    enviar_mensaje(numero_origen, "En este momento estamos actualizando nuestro catálogo. ¡Vuelve en unos minutos!")
                    
                
                
if __name__ == '__main__':
    app.run(port=5000)