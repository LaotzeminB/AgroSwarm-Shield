import 'package:flutter/material.dart';
import 'package:latlong2/latlong.dart';
import '../services/api_service.dart';
import '../services/websocket_service.dart';

/// Estado en vivo de un dron del enjambre, tal como lo manda el backend
/// por el canal de telemetría (evento "TELEMETRIA").
class DronReal {
  double lat;
  double lng;
  int bateria;
  String estado; // PATRULLANDO, TRATANDO_PLAGA, REGRESANDO_BASE, EN_BASE

  DronReal({
    required this.lat,
    required this.lng,
    required this.bateria,
    required this.estado,
  });
}

class DronProvider extends ChangeNotifier {
  final WebSocketService _ws = WebSocketService();
  bool conectado = false;

  // 🐝 Enjambre real (uno o varios drones, según lo que despliegue el backend)
  final Map<String, DronReal> drones = {};

  // 🏠 Colmena: empieza en Aguascalientes por defecto, y se mueve al centro
  // del terreno en cuanto se despliega una misión real.
  double colmenaLat = 21.8823;
  double colmenaLng = -102.2826;

  // 🤝 "Servicio de Escudo" compartido: si mi colmena atiende a más de un
  // cliente, el enjambre se turna entre ellos. El servidor solo me manda MIS
  // propios datos -nunca los de otro cliente-, aunque usemos la misma
  // colmena física.
  String? miColmenaId; // null = todavía no he desplegado nada (se ve la colmena de demostración)
  bool compartida = false;
  int terrenosEnColmena = 1;
  bool esTuTurno = true;

  // 🚨 Última alerta para mostrar en pantalla (intrusión, plaga real, etc.)
  String? _alertaActiva;
  String? get alerta => _alertaActiva;
  LatLng? ultimaPlagaLatLng;

  int totalIntrusiones = 0;

  // 📜 Actividad en vivo (para mostrar un historial en pantalla)
  final List<String> log = [];

  // 🟢 Zonas de cultivo ilustrativas (el backend todavía no manda un mapa
  // de salud del cultivo real; esto se deja como referencia visual).
  final List<ZonaCultivo> zonas = [
    ZonaCultivo(
      nombre: 'Cultivo Sano',
      estado: 'sano',
      puntos: const [
        LatLng(21.8828, -102.2830),
        LatLng(21.8838, -102.2830),
        LatLng(21.8838, -102.2820),
        LatLng(21.8828, -102.2820),
      ],
    ),
  ];

  int get dronesActivos => drones.length;

  int get bateriaPromedio {
    if (drones.isEmpty) return 0;
    final total = drones.values.fold<int>(0, (acc, d) => acc + d.bateria);
    return (total / drones.length).round();
  }

  // ---------------- CONEXIÓN EN VIVO ----------------

  void conectarTelemetria() {
    if (conectado) return;
    conectado = true;
    _ws.conectar(_manejarEvento);
    _refrescarIntrusiones();
  }

  void desconectarTelemetria() {
    _ws.desconectar();
    conectado = false;
  }

  Future<void> _refrescarIntrusiones() async {
    totalIntrusiones = await ApiService.obtenerTotalIntrusiones();
    notifyListeners();
  }

  void _manejarEvento(Map<String, dynamic> evento) {
    final tipo = evento['event'] as String?;

    // Filtro de privacidad del lado de la app: el servidor YA solo me manda
    // mis propios datos (eso es lo que de verdad protege la privacidad),
    // pero además nos aseguramos aquí de solo pintar en el mapa lo que le
    // corresponde a mi colmena (o a la de demostración, mientras no haya
    // desplegado nada todavía).
    final colmenaDelEvento = evento['colmena_id'] as String?;
    final esDeMiColmena = miColmenaId == null
        ? colmenaDelEvento == 'COLMENA-DEMO'
        : colmenaDelEvento == miColmenaId;

    switch (tipo) {
      case 'TELEMETRIA':
        if (!esDeMiColmena) return;
        final id = evento['dron_id'] as String;
        final gps = evento['gps'] as Map<String, dynamic>;
        drones[id] = DronReal(
          lat: (gps['lat'] as num).toDouble(),
          lng: (gps['lng'] as num).toDouble(),
          bateria: evento['bateria_pct'] as int,
          estado: evento['estado'] as String,
        );
        break;

      case 'MISION_INICIADA':
        // Este aviso el servidor solo me lo manda a mí (nunca a otros
        // clientes de la misma colmena), así que aquí sí lo tomamos siempre.
        miColmenaId = evento['colmena_id'] as String?;
        compartida = evento['compartida'] as bool? ?? false;
        terrenosEnColmena = evento['terrenos_en_colmena'] as int? ?? 1;
        esTuTurno = true; // al desplegar, entras de inmediato a tu turno
        final colmena = evento['colmena'] as Map<String, dynamic>?;
        if (colmena != null) {
          colmenaLat = (colmena['lat'] as num).toDouble();
          colmenaLng = (colmena['lng'] as num).toDouble();
        }
        drones.clear(); // el enjambre se reinicia desde la nueva colmena
        _agregarLog(
          '🛰️ Misión iniciada en ${evento['terreno_id']} (${evento['drones_desplegados']} drones)'
          '${compartida ? ' · colmena compartida con ${terrenosEnColmena - 1} cliente(s) más' : ''}',
        );
        break;

      case 'TURNO_ROTADO':
        if (colmenaDelEvento != miColmenaId) return;
        esTuTurno = evento['es_tu_turno'] as bool? ?? true;
        terrenosEnColmena = evento['terrenos_compartiendo_colmena'] as int? ?? terrenosEnColmena;
        // Por si alguien se unió a tu colmena DESPUÉS de que ya habías
        // desplegado: en cuanto haya una rotación, aquí nos enteramos de que
        // ya se volvió compartida (antes de eso solo lo sabe el servidor).
        compartida = terrenosEnColmena > 1;
        if (!esTuTurno) {
          // Ya no es mi turno: no voy a recibir más telemetría de esta
          // colmena hasta que me toque otra vez, así que se limpia el mapa.
          drones.clear();
          _agregarLog('⏳ Le toca el turno a otro cliente de la colmena compartida');
        } else {
          _agregarLog('🐝 ¡Ya es tu turno de patrullaje otra vez!');
        }
        break;

      case 'KILL_SWITCH_ACTIVADO':
        if (!esDeMiColmena && colmenaDelEvento != miColmenaId) return;
        _agregarLog('🛑 KILL-SWITCH: ${evento['reason']}');
        break;

      case 'INTENTO_INTRUSION':
        totalIntrusiones += 1;
        _agregarLog('🚨 Intrusión bloqueada: ${evento['motivo']}');
        break;

      case 'PLAGA_DETECTADA_SENSOR':
        final lat = (evento['lat'] as num?)?.toDouble();
        final lng = (evento['lng'] as num?)?.toDouble();
        if (lat != null && lng != null) {
          ultimaPlagaLatLng = LatLng(lat, lng);
        }
        _alertaActiva = '🐛 Plaga detectada por el sensor de campo';
        _agregarLog('🐛 Plaga detectada por el sensor de campo');
        break;
    }
    notifyListeners();
  }

  void _agregarLog(String texto) {
    log.insert(0, texto);
    if (log.length > 30) log.removeLast();
  }

  void limpiarAlerta() {
    _alertaActiva = null;
    notifyListeners();
  }

  // ---------------- ACCIONES REALES CONTRA EL BACKEND ----------------

  Future<void> desplegarEnjambre({
    required String terrenoId,
    required List<LatLng> poligono,
    required int numDrones,
  }) async {
    final puntos = poligono
        .map((p) => [p.latitude, p.longitude])
        .toList(growable: false);
    await ApiService.desplegarMision(
      terrenoId: terrenoId,
      poligono: puntos,
      numDrones: numDrones,
    );
  }

  Future<void> activarKillSwitch(String razon) async {
    await ApiService.activarKillSwitch(razon, colmenaId: miColmenaId);
  }

  @override
  void dispose() {
    _ws.desconectar();
    super.dispose();
  }
}

// ============================================================
// MODELO DE ZONA DE CULTIVO (ilustrativo)
// ============================================================
class ZonaCultivo {
  final String nombre;
  final String estado;
  final List<LatLng> puntos;

  ZonaCultivo({
    required this.nombre,
    required this.estado,
    required this.puntos,
  });

  Color get color {
    switch (estado) {
      case 'sano':
        return Colors.green;
      case 'agua':
        return Colors.amber;
      case 'plaga':
        return Colors.red;
      default:
        return Colors.grey;
    }
  }

  LatLng get centro {
    double lat = 0, lng = 0;
    for (var punto in puntos) {
      lat += punto.latitude;
      lng += punto.longitude;
    }
    return LatLng(lat / puntos.length, lng / puntos.length);
  }
}
