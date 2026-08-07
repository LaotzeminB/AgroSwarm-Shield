import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../providers/usuario_provider.dart';
import '../providers/dron_provider.dart';
import '../services/api_service.dart';

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _usuarioController = TextEditingController(text: 'rancho_utma');
  final _passwordController = TextEditingController(text: 'agrotech2026');
  bool _cargando = false;
  String? _error;

  @override
  void dispose() {
    _usuarioController.dispose();
    _passwordController.dispose();
    super.dispose();
  }

  Future<void> _iniciarSesion() async {
    setState(() {
      _cargando = true;
      _error = null;
    });
    try {
      final datos = await ApiService.login(
        _usuarioController.text.trim(),
        _passwordController.text,
      );
      if (!mounted) return;
      Provider.of<UsuarioProvider>(context, listen: false).establecerSesion(
        usuario: _usuarioController.text.trim(),
        ranchoNombre: datos['rancho'] as String? ?? '',
      );
      Provider.of<DronProvider>(context, listen: false).conectarTelemetria();
      Navigator.pushReplacementNamed(context, '/dashboard');
    } catch (e) {
      setState(() => _error = e.toString());
    } finally {
      if (mounted) setState(() => _cargando = false);
    }
  }

  void _abrirConfiguracionServidor() {
    final controller = TextEditingController(text: ApiService.baseUrl);
    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('⚙️ Dirección del servidor'),
        content: TextField(
          controller: controller,
          decoration: const InputDecoration(
            labelText: 'http://IP-DE-LA-COMPUTADORA:8000',
            border: OutlineInputBorder(),
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('Cancelar'),
          ),
          ElevatedButton(
            onPressed: () async {
              await ApiService.guardarServidor(controller.text);
              if (context.mounted) Navigator.pop(context);
            },
            child: const Text('Guardar'),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Container(
        decoration: BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topCenter,
            end: Alignment.bottomCenter,
            colors: [Colors.green.shade900, Colors.green.shade700],
          ),
        ),
        child: SafeArea(
          child: Stack(
            children: [
              Align(
                alignment: Alignment.topRight,
                child: IconButton(
                  icon: const Icon(Icons.settings, color: Colors.white70),
                  tooltip: 'Dirección del servidor',
                  onPressed: _abrirConfiguracionServidor,
                ),
              ),
              Center(
                child: SingleChildScrollView(
                  child: Padding(
                    padding: const EdgeInsets.all(24.0),
                    child: Column(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        const Icon(
                          Icons.agriculture,
                          size: 80,
                          color: Colors.white,
                        ),
                        const SizedBox(height: 24),
                        const Text(
                          '🐝 AgroSwarmShield',
                          style: TextStyle(
                            fontSize: 28,
                            fontWeight: FontWeight.bold,
                            color: Colors.white,
                          ),
                        ),
                        const SizedBox(height: 40),
                        TextField(
                          controller: _usuarioController,
                          decoration: InputDecoration(
                            labelText: 'Usuario',
                            labelStyle: const TextStyle(color: Colors.white70),
                            prefixIcon:
                                const Icon(Icons.person, color: Colors.white70),
                            filled: true,
                            fillColor: Colors.white.withOpacity(0.1),
                            border: OutlineInputBorder(
                              borderRadius: BorderRadius.circular(12),
                              borderSide: BorderSide.none,
                            ),
                          ),
                          style: const TextStyle(color: Colors.white),
                        ),
                        const SizedBox(height: 16),
                        TextField(
                          controller: _passwordController,
                          obscureText: true,
                          decoration: InputDecoration(
                            labelText: 'Contraseña',
                            labelStyle: const TextStyle(color: Colors.white70),
                            prefixIcon:
                                const Icon(Icons.lock, color: Colors.white70),
                            filled: true,
                            fillColor: Colors.white.withOpacity(0.1),
                            border: OutlineInputBorder(
                              borderRadius: BorderRadius.circular(12),
                              borderSide: BorderSide.none,
                            ),
                          ),
                          style: const TextStyle(color: Colors.white),
                        ),
                        if (_error != null) ...[
                          const SizedBox(height: 16),
                          Text(
                            _error!,
                            style: const TextStyle(color: Colors.redAccent),
                            textAlign: TextAlign.center,
                          ),
                        ],
                        const SizedBox(height: 32),
                        SizedBox(
                          width: double.infinity,
                          height: 56,
                          child: ElevatedButton(
                            onPressed: _cargando ? null : _iniciarSesion,
                            style: ElevatedButton.styleFrom(
                              backgroundColor: Colors.amber.shade700,
                              foregroundColor: Colors.white,
                              shape: RoundedRectangleBorder(
                                borderRadius: BorderRadius.circular(12),
                              ),
                            ),
                            child: _cargando
                                ? const SizedBox(
                                    width: 22,
                                    height: 22,
                                    child: CircularProgressIndicator(
                                      color: Colors.white,
                                      strokeWidth: 2.5,
                                    ),
                                  )
                                : const Text(
                                    'INGRESAR',
                                    style: TextStyle(
                                      fontSize: 18,
                                      fontWeight: FontWeight.bold,
                                      letterSpacing: 2,
                                    ),
                                  ),
                          ),
                        ),
                        const SizedBox(height: 16),
                        TextButton(
                          onPressed: () {
                            Navigator.pushNamed(context, '/registro');
                          },
                          child: const Text(
                            '¿No tienes cuenta? Regístrate',
                            style: TextStyle(
                              color: Colors.white70,
                              fontSize: 14,
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
