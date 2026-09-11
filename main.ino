#include <Arduino.h>
#include <WiFi.h>
#include <WiFiUdp.h>
#include <ArduinoOTA.h>
#include "driver/i2s.h"
#include <Adafruit_NeoPixel.h>

// ==========================================
//           CONFIGURACIÓN DE MODO
// ==========================================
// Descomentar la siguiente línea para activar el modo silencioso (sin audio, LEDs y botones funcionales)
//#define MODO_SILENCIOSO

// ==========================================
//           CABECERAS DE AUDIO (TODAS ADPCM)
// ==========================================
// Comunes
#include "gogo_audio.h"       // power_cut_wav / power_cut_wav_len
#include "metamorphosis.h"    // metamorphosis_wav / metamorphosis_wav_len

// Archivos de audio generados en la carpeta
#include "red.h"              // red_adpcm_raw
#include "black.h"            // black_adpcm_raw
#include "yellow.h"           // yellow_adpcm_raw
#include "white.h"            // white_adpcm_raw
#include "blue.h"             // blue_adpcm_raw
#include "pink.h"             // pink_adpcm_raw

#include "red_t1.h"           // red_t1_adpcm_raw
#include "black_t1.h"         // black_t1_adpcm_raw
#include "yellow_t1.h"        // yellow_t1_adpcm_raw
#include "white_t1.h"         // white_t1_adpcm_raw
#include "blue_t1.h"          // blue_t1_adpcm_raw
#include "pink_t1.h"          // pink_t1_adpcm_raw

#include "megazord.h"         // megazord_adpcm_raw / megazord_adpcm_raw_len

// ==========================================
//           DATOS DE RED & IP FIJA
// ==========================================
const char* WIFI_SSID = "RED_C";
const char* WIFI_PASS = "C0030DAA8702E";

IPAddress local_IP(192, 168, 10, 17);
IPAddress gateway(192, 168, 10, 1);
IPAddress subnet(255, 255, 255, 0);
IPAddress primaryDNS(8, 8, 8, 8);

// Configuración UDP para comunicación con la Estantería
IPAddress ESTANTERIA_IP(192, 168, 10, 12);
const uint16_t ESTANTERIA_UDP_PORT = 5005;
WiFiUDP udp;

// ==========================================
//           MAPEO DE PINES (XIAO C3)
// ==========================================
// I2S (MAX98357A)
#define I2S_BCLK_PIN   3  // D1 (GPIO 3)
#define I2S_LRC_PIN    4  // D2 (GPIO 4)
#define I2S_DOUT_PIN   5  // D3 (GPIO 5)

// WS2812B LEDs
#define LED_PIN        D8 // D8 (GPIO 8)
#define NUM_LEDS       6  // 6 LEDs en círculo
Adafruit_NeoPixel strip(NUM_LEDS, LED_PIN, NEO_GRB + NEO_KHZ800);

// Entradas Morpher
const int PIN_APERTURA = D0; // 0: Abierto, 1: Cerrado
const int PIN_M_D4     = D4; // Bit 0
const int PIN_M_D5     = D5; // Bit 1
const int PIN_M_D6     = D6; // Bit 2
const int PIN_TOP      = D7; // 1: Pulsado, 0: Reposo

// Configuración Audio I2S
#define SAMPLE_RATE_AUDIO 11025
#define BUFFER_SIZE       128

// Factor de ganancia ADPCM aumentado para máximo volumen
#define ADPCM_VOLUME_SCALE 1.35f

// Control de estados y debounce
int estadoAperturaConfirmado = 1;
int ultimoAperturaTransitorio = 1;
unsigned long tiempoUltimoCambioApertura = 0;

int estadoTopConfirmado = 0;
int ultimoTopTransitorio = 0;
unsigned long tiempoUltimoCambioTop = 0;

int codigoMonedaConfirmado = 0;
int ultimoCodigoTransitorio = 0;
unsigned long tiempoUltimoCambioMoneda = 0;

const unsigned long DEBOUNCE_APERTURA = 80;
const unsigned long DEBOUNCE_BOTON    = 50;
const unsigned long DEBOUNCE_MONEDA   = 300;

// Paleta de colores
const uint32_t COLOR_ROJO_TIRANO   = strip.Color(255, 0, 0);
const uint32_t COLOR_MORADO_MASTO  = strip.Color(160, 0, 255);
const uint32_t COLOR_AZUL_TRICE    = strip.Color(0, 60, 255);
const uint32_t COLOR_AMARILLO_SAB  = strip.Color(255, 200, 0);
const uint32_t COLOR_ROSA_PTERO    = strip.Color(255, 15, 140);
const uint32_t COLOR_BLANCO_TIGRE  = strip.Color(255, 255, 255);
const uint32_t COLOR_VERDE_DRAGON  = strip.Color(0, 255, 0);
const uint32_t COLOR_APAGADO       = strip.Color(0, 0, 0);

// ==========================================
//    SEGUIMIENTO DE LOS 5 ZORDS PRINCIPALES
// ==========================================
bool zordInvocadoRojo = false;
bool zordInvocadoAzul = false;
bool zordInvocadoAmarillo = false;
bool zordInvocadoRosa = false;
bool zordInvocadoNegro = false;
bool megazordListo = false;

bool todosLosZordsInvocados() {
  return zordInvocadoRojo && zordInvocadoAzul && zordInvocadoAmarillo && zordInvocadoRosa && zordInvocadoNegro;
}

void registrarZordInvocado(int d4, int d5, int d6) {
  int codigo = (d6 << 2) | (d5 << 1) | d4;
  switch (codigo) {
    case 0b010: zordInvocadoRojo = true; Serial.println("[ZORDS] -> Tiranosaurio (Rojo) registrado."); break;
    case 0b101: zordInvocadoAzul = true; Serial.println("[ZORDS] -> Triceratops (Azul) registrado."); break;
    case 0b111: zordInvocadoAmarillo = true; Serial.println("[ZORDS] -> Dientes de Sable (Amarillo) registrado."); break;
    case 0b100: zordInvocadoRosa = true; Serial.println("[ZORDS] -> Pterodactilo (Rosa) registrado."); break;
    case 0b110: zordInvocadoNegro = true; Serial.println("[ZORDS] -> Mastodonte (Negro) registrado."); break;
    default:    break;
  }

  int total = (zordInvocadoRojo ? 1 : 0) + (zordInvocadoAzul ? 1 : 0) +
              (zordInvocadoAmarillo ? 1 : 0) + (zordInvocadoRosa ? 1 : 0) +
              (zordInvocadoNegro ? 1 : 0);

  Serial.printf("[ZORDS] Progreso: %d/5 Zords principales invocados.\n", total);

  if (!megazordListo && todosLosZordsInvocados()) {
    megazordListo = true;
    Serial.println("\n⭐⭐⭐ ¡¡LOS 5 ZORDS PRINCIPALES HAN SIDO INVOCADOS!! ⭐⭐⭐");
    Serial.println("⚡ En la siguiente pulsación con el Morpher abierto se invocará al MEGAZORD.");
  }
}

void resetearZordsInvocados() {
  zordInvocadoRojo = false;
  zordInvocadoAzul = false;
  zordInvocadoAmarillo = false;
  zordInvocadoRosa = false;
  zordInvocadoNegro = false;
  megazordListo = false;
  Serial.println("[ZORDS] Contador de 5 Zords reseteado.");
}

// ==========================================
//          FUNCIONES DE ILUMINACIÓN
// ==========================================
void setAllLeds(uint32_t color) {
  for (int i = 0; i < NUM_LEDS; i++) {
    strip.setPixelColor(i, color);
  }
  strip.show();
}

void secuenciaGiro(uint32_t color, int vueltas, int velocidadMs) {
  for (int v = 0; v < vueltas; v++) {
    for (int i = 0; i < NUM_LEDS; i++) {
      strip.clear();
      strip.setPixelColor(i, color);
      strip.show();
      delay(velocidadMs);
    }
  }
  setAllLeds(COLOR_APAGADO);
}

uint32_t obtenerColorMoneda(int d4, int d5, int d6) {
  int codigo = (d6 << 2) | (d5 << 1) | d4;
  switch (codigo) {
    case 0b110: return COLOR_MORADO_MASTO;
    case 0b111: return COLOR_AMARILLO_SAB;
    case 0b101: return COLOR_AZUL_TRICE;
    case 0b100: return COLOR_ROSA_PTERO;
    case 0b010: return COLOR_ROJO_TIRANO;
    case 0b011: return COLOR_BLANCO_TIGRE;
    case 0b001: return COLOR_VERDE_DRAGON;
    default:    return COLOR_ROJO_TIRANO;
  }
}

const char* obtenerNombreRanger(int d4, int d5, int d6) {
  int codigo = (d6 << 2) | (d5 << 1) | d4;
  switch (codigo) {
    case 0b110: return "BLACK";
    case 0b111: return "YELLOW";
    case 0b101: return "BLUE";
    case 0b100: return "PINK";
    case 0b010: return "RED";
    case 0b011: return "WHITE";
    case 0b001: return "WHITE";
    default:    return "RED";
  }
}

void enviarComandoUDP(const char* tipo, int d4, int d5, int d6) {
  if (WiFi.status() != WL_CONNECTED) return;
  const char* ranger = obtenerNombreRanger(d4, d5, d6);
  char msg[32];
  snprintf(msg, sizeof(msg), "%s:%s", tipo, ranger);
  udp.beginPacket(ESTANTERIA_IP, ESTANTERIA_UDP_PORT);
  udp.write((const uint8_t*)msg, strlen(msg));
  udp.endPacket();
}

void aplicarColorMoneda(int d4, int d5, int d6) {
  setAllLeds(obtenerColorMoneda(d4, d5, d6));
}

// ==========================================
//      ALGORITMO DECODIFICADOR IMA-ADPCM
// ==========================================
static const int16_t STEP_TABLE[89] = {
  7, 8, 9, 10, 11, 12, 13, 14, 16, 17,
  19, 21, 23, 25, 28, 31, 34, 37, 41, 45,
  50, 55, 60, 66, 73, 80, 88, 97, 107, 118,
  130, 143, 157, 173, 190, 209, 230, 253, 279, 307,
  337, 371, 408, 449, 494, 544, 598, 658, 724, 796,
  876, 963, 1060, 1166, 1282, 1411, 1552, 1707, 1878, 2066,
  2272, 2499, 2749, 3024, 3327, 3660, 4026, 4428, 4871, 5358,
  5894, 6484, 7132, 7845, 8630, 9493, 10442, 11487, 12635, 13899,
  15289, 16818, 18500, 20350, 22385, 24623, 27086, 29794, 32767
};

static const int8_t INDEX_TABLE[16] = {
  -1, -1, -1, -1, 2, 4, 6, 8,
  -1, -1, -1, -1, 2, 4, 6, 8
};

static inline int16_t decodeNibble(uint8_t nibble, int32_t &predictedSample, int8_t &stepIndex) {
  int32_t step = STEP_TABLE[stepIndex];
  int32_t diff = step >> 3;
  if (nibble & 4) diff += step;
  if (nibble & 2) diff += (step >> 1);
  if (nibble & 1) diff += (step >> 2);

  if (nibble & 8) predictedSample -= diff;
  else predictedSample += diff;

  if (predictedSample > 32767) predictedSample = 32767;
  else if (predictedSample < -32768) predictedSample = -32768;

  stepIndex += INDEX_TABLE[nibble & 0x0F];
  if (stepIndex < 0) stepIndex = 0;
  else if (stepIndex > 88) stepIndex = 88;

  return (int16_t)predictedSample;
}

static inline void writeAudioI2S(void *buffer, size_t size, size_t *bytes_written) {
#ifdef MODO_SILENCIOSO
  memset(buffer, 0, size);
#endif
  i2s_write(I2S_NUM_0, buffer, size, bytes_written, portMAX_DELAY);
}

// ==========================================
//      FUNCIONES DE AUDIO CON LIMITADOR
// ==========================================

void playAdpcmAudioWithLedStrobe(const uint8_t *adpcmData, size_t dataLen, uint32_t colorOn, int strobeIntervalMs = 60) {
  i2s_set_sample_rates(I2S_NUM_0, SAMPLE_RATE_AUDIO);

  int32_t predictedSample = 0;
  int8_t stepIndex = 0;

  int16_t buffer[BUFFER_SIZE * 2];
  size_t bytes_written;
  int bufIdx = 0;

  unsigned long lastStrobe = millis();
  bool ledState = true;
  setAllLeds(colorOn);

  for (size_t i = 0; i < dataLen; i++) {
    uint8_t byteVal = pgm_read_byte(&adpcmData[i]);

    int32_t v1 = (int32_t)(decodeNibble(byteVal & 0x0F, predictedSample, stepIndex) * ADPCM_VOLUME_SCALE);
    if (v1 > 32767) v1 = 32767; else if (v1 < -32768) v1 = -32768;
    int16_t s1 = (int16_t)v1;
    buffer[bufIdx++] = s1;
    buffer[bufIdx++] = s1;

    int32_t v2 = (int32_t)(decodeNibble((byteVal >> 4) & 0x0F, predictedSample, stepIndex) * ADPCM_VOLUME_SCALE);
    if (v2 > 32767) v2 = 32767; else if (v2 < -32768) v2 = -32768;
    int16_t s2 = (int16_t)v2;
    buffer[bufIdx++] = s2;
    buffer[bufIdx++] = s2;

    if (bufIdx >= BUFFER_SIZE * 2) {
      writeAudioI2S(buffer, sizeof(buffer), &bytes_written);
      bufIdx = 0;

      if (millis() - lastStrobe >= (unsigned long)strobeIntervalMs) {
        lastStrobe = millis();
        ledState = !ledState;
        setAllLeds(ledState ? colorOn : COLOR_APAGADO);
      }
    }
  }

  if (bufIdx > 0) {
    writeAudioI2S(buffer, bufIdx * sizeof(int16_t), &bytes_written);
  }

  i2s_zero_dma_buffer(I2S_NUM_0);
}

void playAdpcmAudioWithDualSpin(const uint8_t *adpcmData, size_t dataLen, uint32_t color, int stepIntervalMs = 45) {
  i2s_set_sample_rates(I2S_NUM_0, SAMPLE_RATE_AUDIO);

  int32_t predictedSample = 0;
  int8_t stepIndex = 0;

  int16_t buffer[BUFFER_SIZE * 2];
  size_t bytes_written;
  int bufIdx = 0;

  unsigned long lastStep = millis();
  int pos = 0;

  strip.clear();
  strip.setPixelColor(pos, color);
  strip.setPixelColor((pos + 3) % NUM_LEDS, color);
  strip.show();

  for (size_t i = 0; i < dataLen; i++) {
    uint8_t byteVal = pgm_read_byte(&adpcmData[i]);

    int32_t v1 = (int32_t)(decodeNibble(byteVal & 0x0F, predictedSample, stepIndex) * ADPCM_VOLUME_SCALE);
    if (v1 > 32767) v1 = 32767; else if (v1 < -32768) v1 = -32768;
    int16_t s1 = (int16_t)v1;
    buffer[bufIdx++] = s1;
    buffer[bufIdx++] = s1;

    int32_t v2 = (int32_t)(decodeNibble((byteVal >> 4) & 0x0F, predictedSample, stepIndex) * ADPCM_VOLUME_SCALE);
    if (v2 > 32767) v2 = 32767; else if (v2 < -32768) v2 = -32768;
    int16_t s2 = (int16_t)v2;
    buffer[bufIdx++] = s2;
    buffer[bufIdx++] = s2;

    if (bufIdx >= BUFFER_SIZE * 2) {
      writeAudioI2S(buffer, sizeof(buffer), &bytes_written);
      bufIdx = 0;

      if (millis() - lastStep >= (unsigned long)stepIntervalMs) {
        lastStep = millis();
        pos = (pos + 1) % NUM_LEDS;
        strip.clear();
        strip.setPixelColor(pos, color);
        strip.setPixelColor((pos + 3) % NUM_LEDS, color);
        strip.show();
      }
    }
  }

  if (bufIdx > 0) {
    writeAudioI2S(buffer, bufIdx * sizeof(int16_t), &bytes_written);
  }

  i2s_zero_dma_buffer(I2S_NUM_0);
}

void playAdpcmAudioWithLedSpin(const uint8_t *adpcmData, size_t dataLen, uint32_t spinColor, int stepIntervalMs = 45) {
  i2s_set_sample_rates(I2S_NUM_0, SAMPLE_RATE_AUDIO);

  int32_t predictedSample = 0;
  int8_t stepIndex = 0;

  int16_t buffer[BUFFER_SIZE * 2];
  size_t bytes_written;
  int bufIdx = 0;

  unsigned long lastStep = millis();
  int activePixel = 0;

  strip.clear();
  strip.setPixelColor(activePixel, spinColor);
  strip.show();

  for (size_t i = 0; i < dataLen; i++) {
    uint8_t byteVal = pgm_read_byte(&adpcmData[i]);

    int32_t v1 = (int32_t)(decodeNibble(byteVal & 0x0F, predictedSample, stepIndex) * ADPCM_VOLUME_SCALE);
    if (v1 > 32767) v1 = 32767; else if (v1 < -32768) v1 = -32768;
    int16_t s1 = (int16_t)v1;
    buffer[bufIdx++] = s1;
    buffer[bufIdx++] = s1;

    int32_t v2 = (int32_t)(decodeNibble((byteVal >> 4) & 0x0F, predictedSample, stepIndex) * ADPCM_VOLUME_SCALE);
    if (v2 > 32767) v2 = 32767; else if (v2 < -32768) v2 = -32768;
    int16_t s2 = (int16_t)v2;
    buffer[bufIdx++] = s2;
    buffer[bufIdx++] = s2;

    if (bufIdx >= BUFFER_SIZE * 2) {
      writeAudioI2S(buffer, sizeof(buffer), &bytes_written);
      bufIdx = 0;

      if (millis() - lastStep >= (unsigned long)stepIntervalMs) {
        lastStep = millis();
        activePixel = (activePixel + 1) % NUM_LEDS;
        strip.clear();
        strip.setPixelColor(activePixel, spinColor);
        strip.show();
      }
    }
  }

  if (bufIdx > 0) {
    writeAudioI2S(buffer, bufIdx * sizeof(int16_t), &bytes_written);
  }

  i2s_zero_dma_buffer(I2S_NUM_0);
  setAllLeds(COLOR_APAGADO);
}

// Reproduce la intro permitiendo cancelar la pista al presionar PIN_TOP una segunda vez
bool playAdpcmAudioWithRedLensFXInterruptible(const uint8_t *adpcmData, size_t dataLen, int stepIntervalMs = 35) {
  i2s_set_sample_rates(I2S_NUM_0, SAMPLE_RATE_AUDIO);

  int32_t predictedSample = 0;
  int8_t stepIndex = 0;

  int16_t buffer[BUFFER_SIZE * 2];
  size_t bytes_written;
  int bufIdx = 0;

  unsigned long lastStep = millis();
  int pos = 0;

  bool botonLiberado = false;
  unsigned long tiempoCambioBoton = 0;
  bool cancelado = false;

  for (size_t i = 0; i < dataLen; i++) {
    // 1. Detectar si se ha soltado el botón tras la primera pulsación
    int lecturaBtn = digitalRead(PIN_TOP);
    if (!botonLiberado) {
      if (lecturaBtn == 0) {
        if (tiempoCambioBoton == 0) tiempoCambioBoton = millis();
        if (millis() - tiempoCambioBoton > DEBOUNCE_BOTON) {
          botonLiberado = true;
          tiempoCambioBoton = 0;
        }
      } else {
        tiempoCambioBoton = 0;
      }
    } else {
      // 2. Si ya se soltó, detectar una segunda pulsación para cortar
      if (lecturaBtn == 1) {
        if (tiempoCambioBoton == 0) tiempoCambioBoton = millis();
        if (millis() - tiempoCambioBoton > DEBOUNCE_BOTON) {
          cancelado = true;
          break; // Cortar el audio inmediatamente
        }
      } else {
        tiempoCambioBoton = 0;
      }
    }

    uint8_t byteVal = pgm_read_byte(&adpcmData[i]);

    int32_t v1 = (int32_t)(decodeNibble(byteVal & 0x0F, predictedSample, stepIndex) * ADPCM_VOLUME_SCALE);
    if (v1 > 32767) v1 = 32767; else if (v1 < -32768) v1 = -32768;
    int16_t s1 = (int16_t)v1;
    buffer[bufIdx++] = s1;
    buffer[bufIdx++] = s1;

    int32_t v2 = (int32_t)(decodeNibble((byteVal >> 4) & 0x0F, predictedSample, stepIndex) * ADPCM_VOLUME_SCALE);
    if (v2 > 32767) v2 = 32767; else if (v2 < -32768) v2 = -32768;
    int16_t s2 = (int16_t)v2;
    buffer[bufIdx++] = s2;
    buffer[bufIdx++] = s2;

    if (bufIdx >= BUFFER_SIZE * 2) {
      writeAudioI2S(buffer, sizeof(buffer), &bytes_written);
      bufIdx = 0;

      if (millis() - lastStep >= (unsigned long)stepIntervalMs) {
        lastStep = millis();
        strip.clear();
        strip.setPixelColor(pos, strip.Color(255, 255, 255));
        strip.setPixelColor((pos + 3) % NUM_LEDS, strip.Color(255, 0, 0));
        strip.show();
        pos = (pos + 1) % NUM_LEDS;
      }
    }
  }

  if (!cancelado && bufIdx > 0) {
    writeAudioI2S(buffer, bufIdx * sizeof(int16_t), &bytes_written);
  }

  i2s_zero_dma_buffer(I2S_NUM_0);
  setAllLeds(COLOR_APAGADO);

  // Esperar a que se libere el botón tras cancelar para no reactivarlo al salir
  if (cancelado) {
    while (digitalRead(PIN_TOP) == 1) {
      delay(10);
    }
    delay(50);
  }

  return cancelado;
}

// ----------------------------------------------------
// 1. REPRODUCIR VOZ AL ABRIR EL MORPHER (usa los audios _t1)
// ----------------------------------------------------
void reproducirVozRangerT1(int d4, int d5, int d6) {
  int codigo = (d6 << 2) | (d5 << 1) | d4;
  uint32_t colorRanger = obtenerColorMoneda(d4, d5, d6);

  switch (codigo) {
    case 0b110: // Mastodonte
      playAdpcmAudioWithLedStrobe(black_t1_adpcm_raw, black_t1_adpcm_raw_len, colorRanger, 70);
      break;

    case 0b111: // Dientes de Sable
      playAdpcmAudioWithLedStrobe(yellow_t1_adpcm_raw, yellow_t1_adpcm_raw_len, colorRanger, 70);
      break;

    case 0b101: // Triceratops
      playAdpcmAudioWithLedStrobe(blue_t1_adpcm_raw, blue_t1_adpcm_raw_len, colorRanger, 70);
      break;

    case 0b100: // Pterodáctilo
      playAdpcmAudioWithLedStrobe(pink_t1_adpcm_raw, pink_t1_adpcm_raw_len, colorRanger, 70);
      break;

    case 0b010: // Tiranosaurio
      playAdpcmAudioWithLedStrobe(red_t1_adpcm_raw, red_t1_adpcm_raw_len, colorRanger, 70);
      break;

    case 0b011: // Tigre Blanco T1
      playAdpcmAudioWithLedStrobe(white_t1_adpcm_raw, white_t1_adpcm_raw_len, colorRanger, 70);
      break;

    case 0b001: // Dragonzord T1
      playAdpcmAudioWithLedStrobe(white_t1_adpcm_raw, white_t1_adpcm_raw_len, colorRanger, 70);
      break;

    default:
      break;
  }
}

// ----------------------------------------------------
// 2. REPRODUCIR INVOCACIÓN ZORD (Botón pulsado abierto / Audios sin _t1)
// ----------------------------------------------------
void reproducirLlamadaZordT2(int d4, int d5, int d6) {
  int codigo = (d6 << 2) | (d5 << 1) | d4;
  uint32_t colorRanger = obtenerColorMoneda(d4, d5, d6);

  switch (codigo) {
    case 0b110: // León Thunderzord
      playAdpcmAudioWithDualSpin(black_adpcm_raw, black_adpcm_raw_len, colorRanger, 45);
      break;

    case 0b111: // Grifo Thunderzord
      playAdpcmAudioWithDualSpin(yellow_adpcm_raw, yellow_adpcm_raw_len, colorRanger, 45);
      break;

    case 0b101: // Unicornio Thunderzord
      playAdpcmAudioWithDualSpin(blue_adpcm_raw, blue_adpcm_raw_len, colorRanger, 45);
      break;

    case 0b100: // Ave de Fuego Thunderzord
      playAdpcmAudioWithDualSpin(pink_adpcm_raw, pink_adpcm_raw_len, colorRanger, 45);
      break;

    case 0b010: // Dragón Rojo Thunderzord
      playAdpcmAudioWithDualSpin(red_adpcm_raw, red_adpcm_raw_len, colorRanger, 45);
      break;

    case 0b011: // Tigerzord Blanco
      playAdpcmAudioWithDualSpin(white_adpcm_raw, white_adpcm_raw_len, colorRanger, 45);
      break;

    case 0b001: // Dragonzord
      playAdpcmAudioWithDualSpin(white_adpcm_raw, white_adpcm_raw_len, colorRanger, 45);
      break;

    default:
      break;
  }
}

// ----------------------------------------------------
// 3. REPRODUCIR MEGAZORD CON GIRO CROMÁTICO COMPLETO
// ----------------------------------------------------
void playAdpcmAudioMegazord(const uint8_t *adpcmData, size_t dataLen, int stepIntervalMs = 35) {
  i2s_set_sample_rates(I2S_NUM_0, SAMPLE_RATE_AUDIO);

  int32_t predictedSample = 0;
  int8_t stepIndex = 0;

  int16_t buffer[BUFFER_SIZE * 2];
  size_t bytes_written;
  int bufIdx = 0;

  unsigned long lastStep = millis();
  int stepCounter = 0;

  const uint32_t PALETA_MEGAZORD[6] = {
    COLOR_ROJO_TIRANO,
    COLOR_AZUL_TRICE,
    COLOR_AMARILLO_SAB,
    COLOR_ROSA_PTERO,
    COLOR_MORADO_MASTO,
    COLOR_BLANCO_TIGRE
  };

  for (size_t i = 0; i < dataLen; i++) {
    uint8_t byteVal = pgm_read_byte(&adpcmData[i]);

    int32_t v1 = (int32_t)(decodeNibble(byteVal & 0x0F, predictedSample, stepIndex) * ADPCM_VOLUME_SCALE);
    if (v1 > 32767) v1 = 32767; else if (v1 < -32768) v1 = -32768;
    int16_t s1 = (int16_t)v1;
    buffer[bufIdx++] = s1;
    buffer[bufIdx++] = s1;

    int32_t v2 = (int32_t)(decodeNibble((byteVal >> 4) & 0x0F, predictedSample, stepIndex) * ADPCM_VOLUME_SCALE);
    if (v2 > 32767) v2 = 32767; else if (v2 < -32768) v2 = -32768;
    int16_t s2 = (int16_t)v2;
    buffer[bufIdx++] = s2;
    buffer[bufIdx++] = s2;

    if (bufIdx >= BUFFER_SIZE * 2) {
      writeAudioI2S(buffer, sizeof(buffer), &bytes_written);
      bufIdx = 0;

      if (millis() - lastStep >= (unsigned long)stepIntervalMs) {
        lastStep = millis();
        stepCounter++;
        for (int l = 0; l < NUM_LEDS; l++) {
          strip.setPixelColor(l, PALETA_MEGAZORD[(l + stepCounter) % 6]);
        }
        strip.show();
      }
    }
  }

  if (bufIdx > 0) {
    writeAudioI2S(buffer, bufIdx * sizeof(int16_t), &bytes_written);
  }

  i2s_zero_dma_buffer(I2S_NUM_0);
  setAllLeds(COLOR_APAGADO);
}

void reproducirMegazord() {
  playAdpcmAudioMegazord(megazord_adpcm_raw, megazord_adpcm_raw_len, 35);
}

// ==========================================
//                  SETUP
// ==========================================
void setup() {
  Serial.begin(115200);
  delay(500);

  strip.begin();
  strip.setBrightness(255);
  setAllLeds(COLOR_APAGADO);

  pinMode(PIN_APERTURA, INPUT_PULLDOWN);
  pinMode(PIN_M_D4,     INPUT_PULLDOWN);
  pinMode(PIN_M_D5,     INPUT_PULLDOWN);
  pinMode(PIN_M_D6,     INPUT_PULLDOWN);
  pinMode(PIN_TOP,      INPUT_PULLDOWN);

  estadoAperturaConfirmado = digitalRead(PIN_APERTURA);
  ultimoAperturaTransitorio = estadoAperturaConfirmado;

  estadoTopConfirmado = digitalRead(PIN_TOP);
  ultimoTopTransitorio = estadoTopConfirmado;

  int d4_init = digitalRead(PIN_M_D4);
  int d5_init = digitalRead(PIN_M_D5);
  int d6_init = digitalRead(PIN_M_D6);
  codigoMonedaConfirmado = (d6_init << 2) | (d5_init << 1) | d4_init;
  ultimoCodigoTransitorio = codigoMonedaConfirmado;

  i2s_config_t i2s_config = {
    .mode = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_TX),
    .sample_rate = SAMPLE_RATE_AUDIO,
    .bits_per_sample = I2S_BITS_PER_SAMPLE_16BIT,
    .channel_format = I2S_CHANNEL_FMT_RIGHT_LEFT,
    .communication_format = I2S_COMM_FORMAT_STAND_I2S,
    .intr_alloc_flags = ESP_INTR_FLAG_LEVEL1,
    .dma_buf_count = 8,
    .dma_buf_len = 64,
    .use_apll = false,
    .tx_desc_auto_clear = true
  };

  i2s_pin_config_t pin_config = {
    .bck_io_num = I2S_BCLK_PIN,
    .ws_io_num = I2S_LRC_PIN,
    .data_out_num = I2S_DOUT_PIN,
    .data_in_num = I2S_PIN_NO_CHANGE
  };

  i2s_driver_install(I2S_NUM_0, &i2s_config, 0, NULL);
  i2s_set_pin(I2S_NUM_0, &pin_config);

  if (!WiFi.config(local_IP, gateway, subnet, primaryDNS)) {
    Serial.println("[WIFI] Fallo al asignar IP estatica.");
  }

  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);

  unsigned long tiempoInicio = millis();
  int ledGiro = 0;
  bool conectado = false;

  while (millis() - tiempoInicio < 8000) {
    if (WiFi.status() == WL_CONNECTED) {
      conectado = true;
      break;
    }
    strip.clear();
    strip.setPixelColor(ledGiro, strip.Color(255, 120, 0));
    strip.show();
    ledGiro = (ledGiro + 1) % NUM_LEDS;
    delay(120);
  }

  if (conectado) {
    secuenciaGiro(strip.Color(0, 255, 0), 2, 40);
    udp.begin(5005);
    ArduinoOTA.setHostname("PowerMorpher-ESP32");
    ArduinoOTA.setPassword("admin");
    ArduinoOTA.setPort(3232);
    ArduinoOTA.begin();
  }

  if (estadoAperturaConfirmado == 0) {
    aplicarColorMoneda(d4_init, d5_init, d6_init);
  }
}

// ==========================================
//                   LOOP
// ==========================================
void loop() {
  if (WiFi.status() == WL_CONNECTED) {
    ArduinoOTA.handle();
  }

  int lecturaApertura = digitalRead(PIN_APERTURA);
  int d4 = digitalRead(PIN_M_D4);
  int d5 = digitalRead(PIN_M_D5);
  int d6 = digitalRead(PIN_M_D6);
  int lecturaTop = digitalRead(PIN_TOP);

  // 1. APERTURA
  if (lecturaApertura != ultimoAperturaTransitorio) {
    ultimoAperturaTransitorio = lecturaApertura;
    tiempoUltimoCambioApertura = millis();
  }

  if ((millis() - tiempoUltimoCambioApertura) > DEBOUNCE_APERTURA) {
    if (lecturaApertura != estadoAperturaConfirmado) {
      estadoAperturaConfirmado = lecturaApertura;

      if (estadoAperturaConfirmado == 0) {
        Serial.println("\n[EVENTO] -> Morpher Abierto: IT'S MORPHIN TIME!");
        enviarComandoUDP("MORPH_INTRO", d4, d5, d6);
        playAdpcmAudioWithLedSpin(metamorphosis_wav, metamorphosis_wav_len, COLOR_ROJO_TIRANO, 45);
        enviarComandoUDP("MORPH", d4, d5, d6);
        reproducirVozRangerT1(d4, d5, d6);
        aplicarColorMoneda(d4, d5, d6);
      } else {
        Serial.println("[EVENTO] -> Morpher Cerrado.");
        setAllLeds(COLOR_APAGADO);
      }
    }
  }

  // 2. BOTÓN TOP
  if (lecturaTop != ultimoTopTransitorio) {
    ultimoTopTransitorio = lecturaTop;
    tiempoUltimoCambioTop = millis();
  }

  if ((millis() - tiempoUltimoCambioTop) > DEBOUNCE_BOTON) {
    if (lecturaTop != estadoTopConfirmado) {
      estadoTopConfirmado = lecturaTop;

      if (estadoTopConfirmado == 1) {
        if (estadoAperturaConfirmado == 1) {
          Serial.println("[EVENTO] -> Pulsado Cerrado: ¡¡GO GO POWER RANGERS!!");
          resetearZordsInvocados();
          enviarComandoUDP("INTRO_START", d4, d5, d6);
          
          bool interrumpido = playAdpcmAudioWithRedLensFXInterruptible(power_cut_wav, power_cut_wav_len, 35);
          
          if (interrumpido) {
            Serial.println("[EVENTO] -> Intro Interrumpida por el usuario.");
          }
          
          enviarComandoUDP("INTRO_STOP", d4, d5, d6);
          setAllLeds(COLOR_APAGADO);

          // Sincronizar el estado del botón al salir
          estadoTopConfirmado = 0;
          ultimoTopTransitorio = 0;
          tiempoUltimoCambioTop = millis();
        } else {
          // ESTADO APERTURA == 0 (Morpher Abierto)
          if (megazordListo) {
            Serial.println("[EVENTO] -> Pulsado Abierto: ¡¡¡LLAMADA MEGAZORD!!!");
            enviarComandoUDP("MEGAZORD", d4, d5, d6);
            reproducirMegazord();
            resetearZordsInvocados();
            aplicarColorMoneda(d4, d5, d6);
          } else {
            Serial.println("[EVENTO] -> Pulsado Abierto: ¡LLAMADA ZORD!");
            enviarComandoUDP("ZORD", d4, d5, d6);
            reproducirLlamadaZordT2(d4, d5, d6);
            registrarZordInvocado(d4, d5, d6);
            aplicarColorMoneda(d4, d5, d6);
          }
        }
      }
    }
  }

  // 3. CAMBIO DE MONEDA EN CALIENTE
  int codigoLeidoInstantaneo = (d6 << 2) | (d5 << 1) | d4;

  if (codigoLeidoInstantaneo != ultimoCodigoTransitorio) {
    ultimoCodigoTransitorio = codigoLeidoInstantaneo;
    tiempoUltimoCambioMoneda = millis();
  }

  if ((millis() - tiempoUltimoCambioMoneda) > DEBOUNCE_MONEDA) {
    if (codigoLeidoInstantaneo != codigoMonedaConfirmado) {
      codigoMonedaConfirmado = codigoLeidoInstantaneo;

      int bitD4 = (codigoMonedaConfirmado & 0b001) ? 1 : 0;
      int bitD5 = (codigoMonedaConfirmado & 0b010) ? 1 : 0;
      int bitD6 = (codigoMonedaConfirmado & 0b100) ? 1 : 0;

      if (estadoAperturaConfirmado == 0) {
        aplicarColorMoneda(bitD4, bitD5, bitD6);
      }
    }
  }

  delay(10);
}