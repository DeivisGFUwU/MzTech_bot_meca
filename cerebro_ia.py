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

def configurar_y_generar(api_key, texto_boss):
    """Configura el motor con el nuevo SDK y ejecuta la inferencia estructurada."""
    cliente = genai.Client(api_key=api_key)
    
    prompt_sistema = """
    Eres el Córtex Lógico de MzTech. Analiza el siguiente mensaje de ventas y extrae la información clave.
    Debes devolver un JSON exacto con esta estructura:
    {
      "nombre_producto": "Nombre corto e identificable (ej. AirPods Pro 2)",
      "precio_regular": 0.00,
      "precio_oferta": 0.00,
      "caracteristicas": ["Característica 1", "Característica 2", "Característica 3"]
    }
    Si no encuentras un precio regular, colócale el mismo valor que el de oferta.
    
    Mensaje del Vendedor a procesar:
    """
    
    respuesta = cliente.models.generate_content(
        model='gemini-3.1-flash-lite',
        contents=prompt_sistema + texto_boss,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
        )
    )
    return json.loads(respuesta.text)

def procesar_promo_boss(texto_boss):
    """Válvula de Redundancia: Intenta con la Key 1, si falla por cuota o error, usa la Key 2."""
    try:
        print("🧠 [CEREBRO] Iniciando síntesis con Núcleo Principal (Key 1)...")
        return configurar_y_generar(KEY_PRINCIPAL, texto_boss)
    except Exception as e_principal:
        print(f"⚠️ [ALERTA] Fallo en el Núcleo Principal: {e_principal}")
        print("🔄 [CEREBRO] Conmutando al Núcleo Secundario (Key 2)...")
        try:
            return configurar_y_generar(KEY_SECUNDARIA, texto_boss)
        except Exception as e_secundario:
            print(f"❌ [COLAPSO CRÍTICO] Ambos núcleos fallaron: {e_secundario}")
            return None

def generar_respuesta_rescate(texto_cliente):
    """Red de Seguridad Cognitiva: Se activa cuando el bot mecánico no entiende el mensaje."""
    try:
        cliente = genai.Client(api_key=KEY_PRINCIPAL)
        prompt_rescate = f"""
        Eres un amable asistente de ventas de MzTech. El cliente acaba de escribir esto: '{texto_cliente}'.
        Como eres un sistema automatizado, no lograste procesar su intención, ya que necesitas que use el comando exacto para comprar.
        Responde en 1 o 2 líneas máximo, sé muy empático, usa algún emoji, y dile sutilmente que si desea adquirir un producto, por favor escriba explícitamente: "comprar [nombre del producto]".
        Si parece una queja o una duda compleja, dile que un asesor humano lo contactará en breve.
        """
        respuesta = cliente.models.generate_content(
            model='gemini-3.1-flash-lite',
            contents=prompt_rescate
        )
        return respuesta.text.strip()
    except Exception as e:
        print(f"⚠️ [CEREBRO RESCATE FALLÓ]: {e}")
        return "🤖 Mmm, no logré entenderte del todo. Para realizar tu pedido, por favor escribe: *comprar [nombre del producto]*."

def generar_respuesta_ventas(texto_cliente, fase_actual, datos_producto, nombre_prod):
    """Analiza al cliente y devuelve un JSON con el mensaje persuasivo y la siguiente fase (con 3 reintentos)."""
    cliente_ai = genai.Client(api_key=KEY_PRINCIPAL)
    
    prompt_ventas = f"""
    Eres el vendedor estrella de MzTech. Eres persuasivo, empático, natural y usas emojis (pero sin exagerar).
    El cliente está en la FASE {fase_actual} de un embudo de 5 pasos (1:Saludo, 2:Interés, 3:Cierre/Precio, 4:Objeciones, 5:Ultimátum).
    
    EL PRODUCTO ACTIVO ES: {nombre_prod}
    DATOS DEL PRODUCTO: {json.dumps(datos_producto, ensure_ascii=False)}
    IMPORTANTE: NO inventes precios, características ni promociones que no estén en los datos proporcionados.
    
    El cliente acaba de escribir esto: "{texto_cliente}"
    
    Tu tarea: 
    1. Lee su intención (duda, queja, interés de compra).
    2. Responde persuasivamente. Si muestra interés de comprar, recuérdale que para hacer su pedido debe escribir exactamente: "comprar {nombre_prod}".
    
    Debes devolver ESTRICTAMENTE un JSON con esta estructura:
    {{
      "intencion_detectada": "breve descripcion de lo que quiere el cliente",
      "fase_siguiente": numero (calcula a qué fase del 1 al 5 debe pasar),
      "mensaje_convincente": "tu respuesta persuasiva aquí"
    }}
    """
    for intento in range(3):
        try:
            respuesta = cliente_ai.models.generate_content(
                model='gemini-3.1-flash-lite',
                contents=prompt_ventas,
                config=types.GenerateContentConfig(response_mime_type="application/json")
            )
            return json.loads(respuesta.text)
        except Exception as e:
            print(f"⚠️ [RED AI] Falla en intento {intento + 1}: {e}")
            time.sleep(1)
            
    print("❌ [COLAPSO CRÍTICO] La API de IA no respondió después de 3 intentos.")
    return None