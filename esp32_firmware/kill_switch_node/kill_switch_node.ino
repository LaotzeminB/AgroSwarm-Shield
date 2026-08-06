// ============================================================================
// AGROSWARM SHIELD - Nodo ESP32 (Kill-Switch)
// ============================================================================
// Este código va DENTRO del dron (o de la placa ESP32 que simula uno).
// Hace 3 cosas:
//   1. Se conecta al WiFi.
//   2. Se conecta al canal de telemetría del servidor (WebSocket) y se queda
//      escuchando en tiempo real.
//   3. Cuando llega la orden de KILL-SWITCH, verifica su firma HMAC (para
//      asegurarse de que de verdad viene del servidor y no de un hacker) y,
//      si es válida, corta la corriente a los motores.
// ============================================================================

#include <WiFi.h>
#include <ArduinoWebsockets.h>
#include <ArduinoJson.h>
#include "mbedtls/md.h"

using namespace websockets;

// ---------------------------------------------------------------------------
// PASO 1: CONFIGURA ESTOS 4 VALORES ANTES DE SUBIR EL CÓDIGO AL ESP32
// ---------------------------------------------------------------------------

// Nombre y contraseña de tu red WiFi (el ESP32 y la compu que corre el
// servidor deben estar conectados a la MISMA red).
const char* WIFI_SSID = "NOMBRE_DE_TU_WIFI";
const char* WIFI_PASSWORD = "CONTRASEÑA_DE_TU_WIFI";

// La IP de la compu donde corre el servidor (NO uses "127.0.0.1" ni
// "localhost" aquí, porque esos apuntan al propio ESP32, no a tu compu).
// Para encontrar tu IP en Windows: abre PowerShell y escribe "ipconfig",
// busca "Dirección IPv4" (algo como 192.168.1.35).
const char* SERVER_WS_URL = "ws://192.168.1.35:8000/api/v1/ws/telemetry";

// Debe ser EXACTAMENTE igual al valor de MESH_HMAC_SECRET que tienes en tu
// archivo .env del servidor. Ábrelo y copia el valor tal cual.
const char* MESH_HMAC_SECRET = "7843dce7214011e550be737ac81d98bf41039d216a9ba31a244ccb93ff0d0558";

// El pin del ESP32 conectado al relé/transistor que corta la corriente a los
// motores. Cámbialo por el pin que realmente uses en tu cableado.
const int PIN_MOTOR_RELAY = 5;

// ---------------------------------------------------------------------------
// A partir de aquí no necesitas cambiar nada.
// ---------------------------------------------------------------------------

WebsocketsClient client;

// Calcula la firma HMAC-SHA256 de un texto, exactamente igual a como lo hace
// el servidor en Python con hmac.new(clave, texto, sha256).hexdigest().
String calcularFirmaHMAC(const String &mensaje) {
  byte resultado[32];
  mbedtls_md_context_t ctx;
  mbedtls_md_init(&ctx);
  const mbedtls_md_info_t *info = mbedtls_md_info_from_type(MBEDTLS_MD_SHA256);
  mbedtls_md_setup(&ctx, info, 1);
  mbedtls_md_hmac_starts(&ctx, (const unsigned char*)MESH_HMAC_SECRET, strlen(MESH_HMAC_SECRET));
  mbedtls_md_hmac_update(&ctx, (const unsigned char*)mensaje.c_str(), mensaje.length());
  mbedtls_md_hmac_finish(&ctx, resultado);
  mbedtls_md_free(&ctx);

  String firmaHex = "";
  for (int i = 0; i < 32; i++) {
    char byteHex[3];
    sprintf(byteHex, "%02x", resultado[i]);
    firmaHex += byteHex;
  }
  return firmaHex;
}

void cortarMotores() {
  digitalWrite(PIN_MOTOR_RELAY, LOW);
  Serial.println("MOTORES CORTADOS (Kill-Switch ejecutado)");
}

void onMensajeRecibido(WebsocketsMessage message) {
  unsigned long inicioMicros = micros();

  StaticJsonDocument<512> doc;
  DeserializationError error = deserializeJson(doc, message.data());
  if (error) {
    Serial.println("Mensaje no es JSON valido, se ignora.");
    return;
  }

  const char* evento = doc["event"];
  if (evento == nullptr) return;

  if (strcmp(evento, "KILL_SWITCH_ACTIVADO") == 0) {
    const char* firmaRecibida = doc["signature_hmac"];
    if (firmaRecibida == nullptr) {
      Serial.println("ALERTA: Kill-Switch sin firma. Se ignora (posible intrusion).");
      return;
    }

    String comandoEsperado = "KILL_SWITCH_ALL_MOTORS_OFF";
    String firmaCalculada = calcularFirmaHMAC(comandoEsperado);

    if (firmaCalculada.equalsIgnoreCase(String(firmaRecibida))) {
      cortarMotores();
      unsigned long tiempoRespuestaMs = (micros() - inicioMicros) / 1000;
      Serial.print("Tiempo de reaccion del ESP32 (parseo + corte de motores): ");
      Serial.print(tiempoRespuestaMs);
      Serial.println(" ms");
    } else {
      Serial.println("ALERTA DE INTRUSION: Kill-Switch con firma INVALIDA. Se ignora.");
    }
  }
}

void setup() {
  Serial.begin(115200);

  pinMode(PIN_MOTOR_RELAY, OUTPUT);
  digitalWrite(PIN_MOTOR_RELAY, HIGH); // motores encendidos al arrancar

  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.print("Conectando a WiFi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(300);
    Serial.print(".");
  }
  Serial.println();
  Serial.print("WiFi conectado. IP del ESP32: ");
  Serial.println(WiFi.localIP());

  client.onMessage(onMensajeRecibido);
  bool conectado = client.connect(SERVER_WS_URL);
  if (conectado) {
    Serial.println("Conectado al canal de telemetria del servidor.");
  } else {
    Serial.println("ERROR: no se pudo conectar al servidor.");
    Serial.println("Revisa: 1) la IP en SERVER_WS_URL  2) que el servidor este corriendo con --host 0.0.0.0  3) el firewall de Windows.");
  }
}

void loop() {
  client.poll(); // revisa si llego un mensaje nuevo por el WebSocket
  delay(10);
}
