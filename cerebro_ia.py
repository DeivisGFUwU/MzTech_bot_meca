import os
import json
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
    # Instanciamos el cliente cuántico con la llave activa
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
    
    # Ejecutamos la inferencia con la nueva estructura de configuración
    respuesta = cliente.models.generate_content(
        model='gemini-3.1-flash-lite',
        contents=prompt_sistema + texto_boss,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
        )
    )
    return json.loads(respuesta.text)

def procesar_promo_boss(texto_boss):
    """
    Válvula de Redundancia: Intenta con la Key 1, si falla por cuota o error, usa la Key 2.
    """
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