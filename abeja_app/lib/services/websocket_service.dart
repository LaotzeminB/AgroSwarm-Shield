import 'dart:convert';
import 'package:web_socket_channel/web_socket_channel.dart';
import 'api_service.dart';

/// Canal de telemetría en vivo del enjambre (posición de cada dron,
/// avisos de misión iniciada, kill-switch, intrusiones bloqueadas y
/// detecciones del sensor de campo). Un solo mensaje JSON por evento,
/// igual que lo consume el panel web del backend.
class WebSocketService {
  WebSocketChannel? _channel;

  void conectar(void Function(Map<String, dynamic> evento) onEvento) {
    desconectar();
    try {
      _channel = WebSocketChannel.connect(Uri.parse(ApiService.wsUrl));
      _channel!.stream.listen(
        (mensaje) {
          try {
            final evento = jsonDecode(mensaje as String) as Map<String, dynamic>;
            onEvento(evento);
          } catch (_) {
            // Mensaje que no se pudo leer como JSON: se ignora.
          }
        },
        onError: (_) {},
        onDone: () {},
        cancelOnError: false,
      );
    } catch (_) {
      // No se pudo abrir el canal (servidor apagado, red equivocada, etc.)
    }
  }

  void desconectar() {
    _channel?.sink.close();
    _channel = null;
  }
}
