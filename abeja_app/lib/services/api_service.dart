import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

/// Habla con el backend real de AgroSwarm Shield (FastAPI de Laotzemin).
/// La dirección del servidor es configurable porque cada quien lo corre
/// en su propia computadora/red durante las pruebas y la demo.
class ApiService {
  static String _baseUrl = 'http://10.0.2.2:8000';
  static String? _token;

  static String get baseUrl => _baseUrl;
  static String? get token => _token;
  static bool get sesionIniciada => _token != null;

  /// Se llama una vez al arrancar la app para recuperar la dirección del
  /// servidor y la sesión guardadas de la última vez.
  static Future<void> cargarConfiguracion() async {
    final prefs = await SharedPreferences.getInstance();
    _baseUrl = prefs.getString('servidor_url') ?? _baseUrl;
    _token = prefs.getString('jwt_token');
  }

  static Future<void> guardarServidor(String url) async {
    _baseUrl = url.trim();
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('servidor_url', _baseUrl);
  }

  static Uri _uri(String path) => Uri.parse('$_baseUrl$path');

  /// La misma dirección del servidor, pero para el canal de telemetría en
  /// vivo (WebSocket en vez de HTTP normal). Manda el token de sesión para
  /// que el servidor identifique quién eres y SOLO te mande tus propios
  /// datos, aunque compartas colmena con otros clientes.
  static String get wsUrl =>
      '${_baseUrl.replaceFirst('http', 'ws')}/api/v1/ws/telemetry?token=$_token';

  static Map<String, String> get _headers => {
        'Content-Type': 'application/json',
        if (_token != null) 'Authorization': 'Bearer $_token',
      };

  static Future<Map<String, dynamic>> _post(
    String path,
    Map<String, dynamic> cuerpo,
  ) async {
    http.Response resp;
    try {
      resp = await http
          .post(_uri(path), headers: _headers, body: jsonEncode(cuerpo))
          .timeout(const Duration(seconds: 10));
    } catch (_) {
      throw ApiException(
        'No se pudo conectar con el servidor ($_baseUrl). '
        'Revisa que esté prendido y que el celular esté en la misma red.',
      );
    }

    Map<String, dynamic> datos;
    try {
      datos = jsonDecode(utf8.decode(resp.bodyBytes)) as Map<String, dynamic>;
    } catch (_) {
      datos = {};
    }

    if (resp.statusCode < 200 || resp.statusCode >= 300) {
      final detalle = datos['detail'];
      final mensaje = detalle is Map
          ? (detalle['motivo'] ?? detalle['alerta'] ?? 'Error del servidor')
              .toString()
          : (detalle?.toString() ?? 'Error del servidor (${resp.statusCode})');
      throw ApiException(mensaje);
    }
    return datos;
  }

  // 1. LOGIN
  static Future<Map<String, dynamic>> login(
      String usuario, String password) async {
    final datos = await _post('/api/v1/auth/login', {
      'username': usuario,
      'password': password,
    });
    await _guardarToken(datos['access_token'] as String);
    return datos;
  }

  // 1B. REGISTRO
  static Future<Map<String, dynamic>> registrar(
      String usuario, String password, String ranchoName) async {
    final datos = await _post('/api/v1/auth/register', {
      'username': usuario,
      'password': password,
      'rancho_name': ranchoName,
    });
    await _guardarToken(datos['access_token'] as String);
    return datos;
  }

  static Future<void> _guardarToken(String token) async {
    _token = token;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('jwt_token', token);
  }

  // 2. DESPLEGAR ENJAMBRE
  static Future<Map<String, dynamic>> desplegarMision({
    required String terrenoId,
    required List<List<double>> poligono,
    required int numDrones,
  }) {
    return _post('/api/v1/mission/start', {
      'terreno_id': terrenoId,
      'polygon_coordinates': poligono,
      'num_drones': numDrones,
    });
  }

  // 3. KILL-SWITCH
  static Future<Map<String, dynamic>> activarKillSwitch(String razon, {String? colmenaId}) {
    return _post('/api/v1/security/kill-switch', {
      'reason': razon,
      if (colmenaId != null) 'colmena_id': colmenaId,
    });
  }

  // 5. BITÁCORA DE INTRUSIONES
  static Future<int> obtenerTotalIntrusiones() async {
    try {
      final resp = await http
          .get(_uri('/api/v1/security/intrusion-log'), headers: _headers)
          .timeout(const Duration(seconds: 10));
      if (resp.statusCode != 200) return 0;
      final datos =
          jsonDecode(utf8.decode(resp.bodyBytes)) as Map<String, dynamic>;
      return datos['total_intentos_bloqueados'] as int? ?? 0;
    } catch (_) {
      return 0;
    }
  }

  static Future<void> cerrarSesion() async {
    _token = null;
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove('jwt_token');
  }
}

class ApiException implements Exception {
  final String mensaje;
  ApiException(this.mensaje);
  @override
  String toString() => mensaje;
}
