import 'package:flutter/material.dart';
import 'screens/dashboard_screen.dart';
import 'screens/login_screen.dart';
import 'screens/mapa_screen.dart';
import 'services/security_service.dart';
import 'services/arduino_service.dart';
import 'providers/dron_provider.dart';

void main() async {
  // 🔒 Verificar seguridad (anti-hacks)
  final isSecure = await SecurityService.verifySecurity();
  if (!isSecure) {
    print('❌ Dispositivo no seguro');
    return;
  }

  // 🔌 Conectar con Arduino
  await ArduinoService.connect();

  runApp(const MyApp());
}

class MyApp extends StatelessWidget {
  const MyApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: '🐝 Abeja Agrícola',
      theme: ThemeData(
        primaryColor: Colors.green.shade800,
        colorScheme: ColorScheme.dark(
          primary: Colors.green.shade800,
          secondary: Colors.amber.shade700,
        ),
        appBarTheme: const AppBarTheme(
          backgroundColor: Colors.green,
          foregroundColor: Colors.white,
        ),
        elevatedButtonTheme: ElevatedButtonThemeData(
          style: ElevatedButton.styleFrom(
            backgroundColor: Colors.green.shade700,
            foregroundColor: Colors.white,
          ),
        ),
      ),
      debugShowCheckedModeBanner: false,
      initialRoute: '/',
      routes: {
        '/': (context) => const LoginScreen(),
        '/dashboard': (context) => const DashboardScreen(),
        '/mapa': (context) => const MapaScreen(),
      },
    );
  }
}