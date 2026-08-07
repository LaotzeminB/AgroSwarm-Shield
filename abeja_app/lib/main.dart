import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'screens/login_screen.dart';
import 'screens/registro_screen.dart';
import 'screens/dashboard_screen.dart';
import 'screens/mapa_screen.dart';
import 'providers/dron_provider.dart';
import 'providers/usuario_provider.dart'; // ← NUEVO
import 'services/security_service.dart';
import 'services/arduino_service.dart';
import 'services/api_service.dart';

void main() async {
  // Necesario antes de usar cualquier plugin (SharedPreferences, etc.)
  // cuando se hace trabajo asíncrono antes de runApp().
  WidgetsFlutterBinding.ensureInitialized();

  final isSecure = await SecurityService.verifySecurity();
  if (!isSecure) {
    print('❌ Dispositivo no seguro');
    return;
  }

  await ArduinoService.connect();

  // Recupera la dirección del servidor y la sesión guardadas (si las hay)
  // antes de mostrar cualquier pantalla.
  await ApiService.cargarConfiguracion();

  runApp(
    MultiProvider(
      providers: [
        ChangeNotifierProvider(create: (_) => DronProvider()),
        ChangeNotifierProvider(create: (_) => UsuarioProvider()), // ← NUEVO
      ],
      child: const MyApp(),
    ),
  );
}

class MyApp extends StatelessWidget {
  const MyApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: '🐝 Abeja Agrícola',
      theme: ThemeData(
        primarySwatch: Colors.green,
        brightness: Brightness.dark,
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
        '/registro': (context) => const RegistroScreen(),
        '/dashboard': (context) => const DashboardScreen(),
        '/mapa': (context) => const MapaScreen(),
      },
    );
  }
}