import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:google_maps_flutter/google_maps_flutter.dart' as gmaps;
import 'package:latlong2/latlong.dart';
import '../providers/usuario_provider.dart';
import '../providers/dron_provider.dart';
import '../services/api_service.dart';

gmaps.LatLng _aGoogle(LatLng p) => gmaps.LatLng(p.latitude, p.longitude);
LatLng _deGoogle(gmaps.LatLng p) => LatLng(p.latitude, p.longitude);

class RegistroScreen extends StatefulWidget {
  const RegistroScreen({super.key});

  @override
  State<RegistroScreen> createState() => _RegistroScreenState();
}

class _RegistroScreenState extends State<RegistroScreen> {
  final _formKey = GlobalKey<FormState>();
  final _usuarioController = TextEditingController();
  final _passwordController = TextEditingController();
  final _ubicacionController = TextEditingController();
  int _densidadOptima = 2; // 1: Baja, 2: Media, 3: Alta
  bool _registrando = false;
  String? _error;

  // --- Delimitación del terreno (mapa dentro del registro) ---
  final List<LatLng> _puntosTerreno = [];
  final LatLng _centroMapa = const LatLng(21.8823, -102.2826); // Aguascalientes
  double _areaM2 = 0;
  int _abejasCalculadas = 0;

  static const double _m2PorAbeja = 15; // 1 abeja por cada 15 m² de terreno

  @override
  void dispose() {
    _usuarioController.dispose();
    _passwordController.dispose();
    _ubicacionController.dispose();
    super.dispose();
  }

  void _tocarMapa(LatLng punto) {
    setState(() {
      _puntosTerreno.add(punto);
      _recalcularAreaYAbejas();
    });
  }

  void _reiniciarTerreno() {
    setState(() {
      _puntosTerreno.clear();
      _areaM2 = 0;
      _abejasCalculadas = 0;
    });
  }

  void _recalcularAreaYAbejas() {
    if (_puntosTerreno.length < 3) {
      _areaM2 = 0;
      _abejasCalculadas = 0;
      return;
    }
    // Fórmula del polígono (Shoelace) en grados, convertida a hectáreas y
    // luego a metros cuadrados (misma conversión que usa el mapa principal).
    double area = 0;
    final n = _puntosTerreno.length;
    for (int i = 0; i < n; i++) {
      final j = (i + 1) % n;
      area += _puntosTerreno[i].latitude * _puntosTerreno[j].longitude;
      area -= _puntosTerreno[j].latitude * _puntosTerreno[i].longitude;
    }
    area = area.abs() / 2;
    final double hectareas = area * 11100;
    _areaM2 = hectareas * 10000;
    _abejasCalculadas = (_areaM2 / _m2PorAbeja).ceil().clamp(1, 30);
  }

  String _obtenerPaquete(int abejas) {
    if (abejas <= 5) return 'Enjambre Básico';
    if (abejas <= 15) return 'Enjambre Intermedio';
    if (abejas <= 30) return 'Enjambre Avanzado';
    return 'Enjambre Pro';
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('📝 Registro'),
        backgroundColor: Colors.green.shade800,
        foregroundColor: Colors.white,
      ),
      body: Padding(
        padding: const EdgeInsets.all(16.0),
        child: Form(
          key: _formKey,
          child: ListView(
            children: [
              const SizedBox(height: 12),
              const Icon(Icons.agriculture, size: 64, color: Colors.green),
              const SizedBox(height: 12),
              const Text(
                '🐝 Registro de Cuenta',
                style: TextStyle(
                  fontSize: 24,
                  fontWeight: FontWeight.bold,
                  color: Colors.green,
                ),
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 24),

              TextFormField(
                controller: _usuarioController,
                decoration: const InputDecoration(
                  labelText: 'Usuario',
                  prefixIcon: Icon(Icons.person),
                  border: OutlineInputBorder(),
                ),
                validator: (value) => value!.isEmpty ? 'Ingresa un usuario' : null,
              ),
              const SizedBox(height: 16),

              TextFormField(
                controller: _passwordController,
                decoration: const InputDecoration(
                  labelText: 'Contraseña',
                  prefixIcon: Icon(Icons.lock),
                  border: OutlineInputBorder(),
                ),
                obscureText: true,
                validator: (value) => value!.length < 6 ? 'Mínimo 6 caracteres' : null,
              ),
              const SizedBox(height: 16),

              TextFormField(
                controller: _ubicacionController,
                decoration: const InputDecoration(
                  labelText: 'Ubicación (Ciudad, Estado)',
                  prefixIcon: Icon(Icons.location_on),
                  border: OutlineInputBorder(),
                ),
                validator: (value) => value!.isEmpty ? 'Ingresa tu ubicación' : null,
              ),
              const SizedBox(height: 20),

              Row(
                children: [
                  const Text('Densidad de cultivo:', style: TextStyle(fontSize: 16)),
                  const SizedBox(width: 16),
                  Expanded(
                    child: DropdownButton<int>(
                      value: _densidadOptima,
                      onChanged: (value) => setState(() => _densidadOptima = value!),
                      items: const [
                        DropdownMenuItem(value: 1, child: Text('Baja')),
                        DropdownMenuItem(value: 2, child: Text('Media')),
                        DropdownMenuItem(value: 3, child: Text('Alta')),
                      ],
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 20),

              // ============================================================
              // 📍 DELIMITAR TERRENO (dentro del registro)
              // ============================================================
              Row(
                children: [
                  const Icon(Icons.map, color: Colors.green),
                  const SizedBox(width: 8),
                  const Text(
                    'Delimita tu terreno',
                    style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
                  ),
                  const Spacer(),
                  if (_puntosTerreno.isNotEmpty)
                    TextButton.icon(
                      onPressed: _reiniciarTerreno,
                      icon: const Icon(Icons.refresh, size: 18),
                      label: const Text('Reiniciar'),
                    ),
                ],
              ),
              const Text(
                'Toca el mapa para ir marcando las esquinas de tu terreno (mínimo 3 puntos).',
                style: TextStyle(fontSize: 12, color: Colors.grey),
              ),
              const SizedBox(height: 8),
              ClipRRect(
                borderRadius: BorderRadius.circular(12),
                child: SizedBox(
                  height: 220,
                  child: gmaps.GoogleMap(
                    initialCameraPosition: gmaps.CameraPosition(
                      target: _aGoogle(_centroMapa),
                      zoom: 17,
                    ),
                    mapType: gmaps.MapType.satellite,
                    onTap: (gmaps.LatLng punto) => _tocarMapa(_deGoogle(punto)),
                    polygons: {
                      if (_puntosTerreno.length >= 3)
                        gmaps.Polygon(
                          polygonId: const gmaps.PolygonId('terreno_registro'),
                          points: _puntosTerreno.map(_aGoogle).toList(),
                          fillColor: Colors.blue.withOpacity(0.3),
                          strokeColor: Colors.blue,
                          strokeWidth: 2,
                        ),
                    },
                    markers: _puntosTerreno.asMap().entries.map((entrada) {
                      return gmaps.Marker(
                        markerId: gmaps.MarkerId('punto_registro_${entrada.key}'),
                        position: _aGoogle(entrada.value),
                        icon: gmaps.BitmapDescriptor.defaultMarkerWithHue(gmaps.BitmapDescriptor.hueBlue),
                      );
                    }).toSet(),
                  ),
                ),
              ),
              const SizedBox(height: 12),

              if (_puntosTerreno.length >= 3)
                Container(
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(
                    color: Colors.green.shade50,
                    borderRadius: BorderRadius.circular(12),
                    border: Border.all(color: Colors.green.shade300),
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text('📐 Área delimitada: ${_areaM2.toStringAsFixed(0)} m²',
                          style: const TextStyle(color: Colors.black)),
                      const SizedBox(height: 4),
                      Text(
                        '🐝 Abejas recomendadas: $_abejasCalculadas (1 cada $_m2PorAbeja m²)',
                        style: TextStyle(fontWeight: FontWeight.bold, color: Colors.amber.shade700),
                      ),
                      Text('📦 Paquete: ${_obtenerPaquete(_abejasCalculadas)}',
                          style: TextStyle(fontWeight: FontWeight.bold, color: Colors.green.shade700)),
                    ],
                  ),
                )
              else
                Container(
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(
                    color: Colors.orange.shade50,
                    borderRadius: BorderRadius.circular(12),
                    border: Border.all(color: Colors.orange.shade200),
                  ),
                  child: const Text(
                    '⚠️ Marca al menos 3 puntos en el mapa para calcular tus abejas recomendadas.',
                    style: TextStyle(fontSize: 12, color: Colors.black87),
                  ),
                ),
              const SizedBox(height: 24),

              if (_error != null) ...[
                Text(_error!, style: const TextStyle(color: Colors.red), textAlign: TextAlign.center),
                const SizedBox(height: 12),
              ],

              SizedBox(
                width: double.infinity,
                height: 50,
                child: ElevatedButton.icon(
                  onPressed: _registrando
                      ? null
                      : () {
                          if (_formKey.currentState!.validate()) {
                            _registrarUsuario(context);
                          }
                        },
                  icon: _registrando
                      ? const SizedBox(
                          width: 18,
                          height: 18,
                          child: CircularProgressIndicator(color: Colors.white, strokeWidth: 2.5),
                        )
                      : const Icon(Icons.save),
                  label: Text(_puntosTerreno.length >= 3
                      ? 'Registrar y Desplegar Enjambre'
                      : 'Registrar'),
                  style: ElevatedButton.styleFrom(
                    backgroundColor: Colors.green.shade700,
                    foregroundColor: Colors.white,
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Future<void> _registrarUsuario(BuildContext context) async {
    final String usuario = _usuarioController.text.trim();
    final String password = _passwordController.text;
    final String ubicacion = _ubicacionController.text.trim();
    final bool hayTerreno = _puntosTerreno.length >= 3;
    final double areaHectareas = _areaM2 / 10000;
    final int abejas = hayTerreno ? _abejasCalculadas : 1;
    final String paquete = _obtenerPaquete(abejas);

    setState(() {
      _registrando = true;
      _error = null;
    });

    try {
      // 1. Registro real contra el backend (queda guardado en MongoDB)
      final datos = await ApiService.registrar(usuario, password, ubicacion);
      if (!context.mounted) return;

      final usuarioProvider = Provider.of<UsuarioProvider>(context, listen: false);
      usuarioProvider.establecerSesion(
        usuario: usuario,
        ranchoNombre: datos['rancho'] as String? ?? ubicacion,
      );
      usuarioProvider.actualizarDatos(
        usuario: usuario,
        ubicacion: ubicacion,
        areaHectareas: areaHectareas,
        abejasRecomendadas: abejas,
        paquete: paquete,
      );

      final dronProvider = Provider.of<DronProvider>(context, listen: false);
      dronProvider.conectarTelemetria();

      // 2. Si se delimitó un terreno, desplegar el enjambre real ahí mismo.
      String? errorDespliegue;
      if (hayTerreno) {
        try {
          await dronProvider.desplegarEnjambre(
            terrenoId: 'TERRENO-REGISTRO-${DateTime.now().millisecondsSinceEpoch}',
            poligono: List<LatLng>.from(_puntosTerreno),
            numDrones: abejas,
          );
        } catch (e) {
          errorDespliegue = e.toString();
        }
      }

      if (!context.mounted) return;
      showDialog(
        context: context,
        barrierDismissible: false,
        builder: (BuildContext context) {
          return AlertDialog(
            title: const Text('✅ Registro Completado'),
            content: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('👤 Usuario: $usuario'),
                Text('📍 Ubicación: $ubicacion'),
                if (hayTerreno) ...[
                  Text('📐 Terreno: ${_areaM2.toStringAsFixed(0)} m²'),
                  Text('🐝 Abejas recomendadas: $abejas',
                      style: TextStyle(fontWeight: FontWeight.bold, color: Colors.amber.shade700)),
                  Text('📦 Paquete: $paquete',
                      style: TextStyle(fontWeight: FontWeight.bold, color: Colors.green.shade700)),
                  const SizedBox(height: 8),
                  Text(
                    errorDespliegue == null
                        ? '🛰️ Enjambre desplegado sobre tu terreno.'
                        : '⚠️ No se pudo desplegar el enjambre: $errorDespliegue',
                    style: TextStyle(color: errorDespliegue == null ? Colors.green.shade800 : Colors.red),
                  ),
                ] else
                  const Text('No delimitaste un terreno todavía — puedes hacerlo desde el mapa.'),
              ],
            ),
            actions: [
              ElevatedButton(
                onPressed: () {
                  Navigator.pop(context);
                  Navigator.pushReplacementNamed(context, '/dashboard');
                },
                child: const Text('Ir al Dashboard'),
              ),
            ],
          );
        },
      );
    } catch (e) {
      setState(() => _error = e.toString());
    } finally {
      if (mounted) setState(() => _registrando = false);
    }
  }
}
