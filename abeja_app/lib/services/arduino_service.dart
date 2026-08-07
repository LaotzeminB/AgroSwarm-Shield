class ArduinoService {
  // ⬇️ Tu equipo pondrá la conexión aquí
  static Future<bool> connect() async {
    print('🔌 Conectando a Arduino...');
    // Simula conexión exitosa
    await Future.delayed(Duration(seconds: 1));
    print('✅ Conectado a Arduino');
    return true;
  }

  static void sendCommand(String command) {
    print('📤 Comando enviado: $command');
    // Aquí irá la lógica para enviar el comando al Arduino
  }

  static void disconnect() {
    print('🔌 Desconectado de Arduino');
  }
}