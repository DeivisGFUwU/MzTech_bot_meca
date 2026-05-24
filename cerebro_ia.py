import os
import json
import time
from google import genai
from google.genai import types
from dotenv import load_dotenv

# Ignición del Entorno
load_dotenv()

# Extracción de los Isótopos Cognitivos
KEY_PRINCIPAL = os.getenv("GEMINI_API_KEY1")
KEY_SECUNDARIA = os.getenv("GEMINI_API_KEY2")

# Inicialización de Clientes Globales para optimizar sockets y CPU
CLIENTE_PRINCIPAL = None
CLIENTE_SECUNDARIO = None

if KEY_PRINCIPAL:
    try:
        CLIENTE_PRINCIPAL = genai.Client(api_key=KEY_PRINCIPAL)
    except Exception as e:
        print(f"⚠️ [INICIALIZACIÓN] Error al instanciar cliente principal: {e}")

if KEY_SECUNDARIA:
    try:
        CLIENTE_SECUNDARIO = genai.Client(api_key=KEY_SECUNDARIA)
    except Exception as e:
        print(f"⚠️ [INICIALIZACIÓN] Error al instanciar cliente secundario: {e}")

def limpiar_y_cargar_json(texto):
    """Limpia el texto de respuestas de la IA por si contiene bloques markdown de tipo ```json."""
    if not texto:
        return None
    texto_limpio = texto.strip()
    if texto_limpio.startswith("```"):
        # Remover bloques markdown
        lineas = texto_limpio.splitlines()
        if lineas[0].startswith("```json") or lineas[0].startswith("```"):
            lineas = lineas[1:]
        if lineas and lineas[-1].startswith("```"):
            lineas = lineas[:-1]
        texto_limpio = "\n".join(lineas).strip()
    try:
        return json.loads(texto_limpio)
    except json.JSONDecodeError as jde:
        print(f"❌ [JSON ERROR] Error al decodificar JSON de la respuesta: {jde}. Contenido: {texto_limpio}")
        return None

# =========================================================
# MOTOR DE INFERENCIA CUÁNTICA (CON CONMUTADOR DE FALLOS)
# =========================================================
def ejecutar_inferencia_cuantica(prompt_text, forzar_json=True):
    """
    Intenta usar la Key 1 (Gemini 3.1). Si falla tras 3 intentos,
    conmuta a la Key 2 (Gemini 2.5) como respaldo de emergencia.
    """
    configuracion = types.GenerateContentConfig(response_mime_type="application/json") if forzar_json else None
    
    # 1. Bucle de Resiliencia (Núcleo Principal 3.1)
    if CLIENTE_PRINCIPAL:
        for intento in range(3):
            try:
                respuesta = CLIENTE_PRINCIPAL.models.generate_content(
                    model='gemini-3.1-flash-lite',
                    contents=prompt_text,
                    config=configuracion
                )
                if forzar_json:
                    parsed = limpiar_y_cargar_json(respuesta.text)
                    if parsed is not None:
                        return parsed
                    # Si no pudimos parsear el JSON, reintentamos o fallamos al secundario
                    print(f"⚠️ [NÚCLEO 3.1] Respuesta no era JSON válido en intento {intento + 1}")
                else:
                    return respuesta.text.strip()
            except Exception as e:
                print(f"⚠️ [NÚCLEO 3.1] Falla temporal en intento {intento + 1}: {e}")
                time.sleep(1)
            
    # 2. Conmutación de Emergencia (Núcleo Secundario 2.5)
    print("🔄 [CONMUTADOR] Núcleo 3.1 colapsado o no disponible. Transfiriendo energía a Núcleo Secundario (2.5)...")
    if CLIENTE_SECUNDARIO:
        try:
            respuesta_secundaria = CLIENTE_SECUNDARIO.models.generate_content(
                model='gemini-2.5-flash-lite',
                contents=prompt_text,
                config=configuracion
            )
            if forzar_json:
                parsed = limpiar_y_cargar_json(respuesta_secundaria.text)
                if parsed is not None:
                    return parsed
            else:
                return respuesta_secundaria.text.strip()
        except Exception as e:
            print(f"❌ [COLAPSO TOTAL] La red neuronal de respaldo también falló: {e}")
            
    return None

# =========================================================
# FUNCIONES DE NEGOCIO (USANDO EL MOTOR UNIFICADO)
# =========================================================
def procesar_promo_boss(texto_boss):
    """Sintetiza la campaña enviada por el Boss."""
    print("🧠 [CEREBRO] Iniciando síntesis de catálogo...")
    prompt_sistema = f"""
    Eres el Córtex Lógico de MzTech. Analiza el siguiente mensaje de ventas y extrae la información clave.
    Debes devolver un JSON exacto con esta estructura:
    {{
      "nombre_producto": "Nombre corto e identificable (ej. AirPods Pro 2)",
      "precio_regular": 0.00,
      "precio_oferta": 0.00,
      "caracteristicas": ["Característica 1", "Característica 2", "Característica 3"]
    }}
    Si no encuentras un precio regular, colócale el mismo valor que el de oferta.
    
    Mensaje a procesar: {texto_boss}
    """
    return ejecutar_inferencia_cuantica(prompt_sistema, forzar_json=True)

def generar_respuesta_rescate(texto_cliente):
    """Red de Seguridad cuando el bot mecánico pierde el hilo."""
    prompt_rescate = f"""
    Eres un amable asistente de ventas de MzTech. El cliente escribió esto: '{texto_cliente}'.
    Como eres un bot, no lograste procesar su intención.
    Reglas:
    - Responde en máximo 2 líneas. SÉ MUY CONCISO.
    - Dile sutilmente que si desea adquirir un producto, escriba explícitamente: "comprar [nombre del producto]".
    """
    return ejecutar_inferencia_cuantica(prompt_rescate, forzar_json=False)

def generar_respuesta_ventas(texto_cliente, fase_actual, datos_producto, nombre_prod):
    """Córtex de Ventas Persuasivo: Lee el contexto y decide la siguiente fase (ahora con auto-cierre)."""
    prompt_ventas = f"""
    Eres el vendedor estrella de MzTech.
    
    REGLAS ESTRICTAS:
    1. MONEDA OFICIAL: Los precios siempre se dan en Soles Peruanos (S/ o PEN).
    2. CONCISIÓN EXTREMA: Sé muy breve y persuasivo. Usa emojis.
    3. PODER DE CIERRE: Si el cliente muestra una intención CLARA y directa de querer comprar ahora mismo (ej. "los quiero", "ok los compro", "dámelos", "quiero uno"), NO le pidas que escriba ningún comando. Simplemente debes asignar "fase_siguiente": 5 y en "intencion_detectada" escribe la palabra exacta "comprar".
    
    ESTADO DEL SISTEMA:
    - Fase actual del embudo: FASE {fase_actual}
    - Producto Activo: {nombre_prod}
    - Datos Técnicos: {json.dumps(datos_producto, ensure_ascii=False)}
    
    MENSAJE DEL CLIENTE: "{texto_cliente}"
    
    Devuelve ESTRICTAMENTE un JSON:
    {{
      "intencion_detectada": "breve intencion (usa 'comprar' si acepta llevarlo)",
      "fase_siguiente": numero (del 1 al 5),
      "mensaje_convincente": "tu respuesta persuasiva aquí (déjalo vacío si la intención es 'comprar')"
    }}
    """
    return ejecutar_inferencia_cuantica(prompt_ventas, forzar_json=True)

def generar_respuesta_seguimiento(fase_actual, catalogo_nombres):
    """Córtex de Retargeting: Redacta un mensaje para reenganchar al cliente tras 30 mins."""
    prompt_seguimiento = f"""
    Eres el vendedor estrella de MzTech. 
    Un cliente se quedó en pausa en la FASE {fase_actual} de la compra hace 30 minutos.
    
    Catálogo de productos activos actuales: {catalogo_nombres}
    
    REGLAS:
    1. Redacta un mensaje de seguimiento ULTRA CONCISO (1 o 2 líneas).
    2. Sé empático, no suenes desesperado por vender. Usa emojis.
    3. Pregúntale sutilmente si le quedó alguna duda con el producto que estaba viendo.
    4. Opcional: Menciónale de forma natural que también tenemos otros modelos en stock ({catalogo_nombres}) por si busca otra cosa.
    """
    
    # Aquí NO forzamos JSON, queremos el texto puro para enviarlo directo
    return ejecutar_inferencia_cuantica(prompt_seguimiento, forzar_json=False)