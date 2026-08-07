import 'package:flutter/material.dart';
import 'package:google_maps_flutter/google_maps_flutter.dart' as gmaps;
import 'package:latlong2/latlong.dart';
import 'package:provider/provider.dart';
import '../providers/dron_provider.dart';
import '../widgets/panel_controles.dart';

gmaps.LatLng _aGoogle(LatLng p) => gmaps.LatLng(p.latitude, p.longitude);
LatLng _deGoogle(gmaps.LatLng p) => LatLng(p.latitude, p.longitude);

class MapaScreen extends StatefulWidget {
  const MapaScreen({super.key});

  @override
  State<MapaScreen> createState() => _MapaScreenState();
}

class _MapaScreenState extends State<MapaScreen> {
  final LatLng _centroInicial = const LatLng(21.9417618, -102.2475702);

  // --- Modo delimitación de terreno ---
  bool _modoDelimitacion = false;
  final List<LatLng> _puntosDelimitacion = [];
  bool _desplegando = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      Provider.of<DronProvider>(context, listen: false).conectarTelemetria();
    });
  }

  // ============================================================
  // CÁLCULO DE ÁREA Y DESPLIEGUE REAL DEL ENJAMBRE
  // ============================================================
  Future<void> _calcularAreaYDesplegar(BuildContext context) async {
    if (_puntosDelimitacion.length < 3) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('⚠️ Se necesitan al menos 3 puntos para delimitar'),
          backgroundColor: Colors.orange,
          duration: Duration(seconds: 2),
        ),
      );
      return;
    }

    double area = 0;
    final n = _puntosDelimitacion.length;
    for (int i = 0; i < n; i++) {
      final j = (i + 1) % n;
      area += _puntosDelimitacion[i].latitude * _puntosDelimitacion[j].longitude;
      area -= _puntosDelimitacion[j].latitude * _puntosDelimitacion[i].longitude;
    }
    area = area.abs() / 2;

    final double hectareas = area * 11100;
    final int abejas = ((hectareas * 10000) / 15).ceil(); // 1 dron cada 15 m²
    final int abejasFinal = abejas.clamp(1, 30); // tope de simulación del backend

    final dronProvider = Provider.of<DronProvider>(context, listen: false);
    final terrenoId = 'TERRENO-APP-${DateTime.now().millisecondsSinceEpoch}';
    final puntos = List<LatLng>.from(_puntosDelimitacion);

    setState(() => _desplegando = true);
    String? error;
    try {
      await dronProvider.desplegarEnjambre(
        terrenoId: terrenoId,
        poligono: puntos,
        numDrones: abejasFinal,
      );
    } catch (e) {
      error = e.toString();
    } finally {
      if (mounted) setState(() => _desplegando = false);
    }

    if (!context.mounted) return;

    showDialog(
      context: context,
      barrierDismissible: false,
      builder: (BuildContext context) {
        return AlertDialog(
          title: Text(error == null ? '🛰️ Enjambre Desplegado' : '⚠️ No se pudo desplegar'),
          content: error == null
              ? Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('📐 Área delimitada: ${hectareas.toStringAsFixed(2)} hectáreas'),
                    const SizedBox(height: 8),
                    Text(
                      '🐝 Drones desplegados: $abejasFinal',
                      style: TextStyle(
                        fontSize: 22,
                        fontWeight: FontWeight.bold,
                        color: Colors.amber.shade700,
                      ),
                    ),
                    const SizedBox(height: 8),
                    Text('📦 Paquete: ${_obtenerPaquete(abejasFinal)}'),
                  ],
                )
              : Text(error),
          actions: [
            TextButton(
              onPressed: () {
                Navigator.pop(context);
                setState(() {
                  _puntosDelimitacion.clear();
                  _modoDelimitacion = false;
                });
              },
              child: const Text('Aceptar'),
            ),
          ],
        );
      },
    );
  }

  String _obtenerPaquete(int abejas) {
    if (abejas <= 5) return 'Enjambre Básico';
    if (abejas <= 15) return 'Enjambre Intermedio';
    if (abejas <= 30) return 'Enjambre Avanzado';
    return 'Enjambre Pro';
  }

  gmaps.BitmapDescriptor _iconoPorEstado(String estado) {
    switch (estado) {
      case 'REGRESANDO_BASE':
        return gmaps.BitmapDescriptor.defaultMarkerWithHue(gmaps.BitmapDescriptor.hueAzure);
      case 'EN_BASE':
        return gmaps.BitmapDescriptor.defaultMarkerWithHue(gmaps.BitmapDescriptor.hueViolet);
      case 'TRATANDO_PLAGA':
        return gmaps.BitmapDescriptor.defaultMarkerWithHue(gmaps.BitmapDescriptor.hueRed);
      default:
        return gmaps.BitmapDescriptor.defaultMarkerWithHue(gmaps.BitmapDescriptor.hueYellow);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('🗺️ Mapa Agrícola'),
        backgroundColor: Colors.green.shade800,
        foregroundColor: Colors.white,
        leading: IconButton(
          icon: const Icon(Icons.arrow_back),
          onPressed: () {
            Navigator.pushReplacementNamed(context, '/dashboard');
          },
          tooltip: 'Volver al Dashboard',
        ),
        actions: [
          if (_desplegando)
            const Padding(
              padding: EdgeInsets.symmetric(horizontal: 12),
              child: Center(
                child: SizedBox(
                  width: 20,
                  height: 20,
                  child: CircularProgressIndicator(color: Colors.white, strokeWidth: 2.5),
                ),
              ),
            ),
          IconButton(
            icon: Icon(
              _modoDelimitacion ? Icons.check_circle : Icons.edit_location,
              color: _modoDelimitacion ? Colors.greenAccent : Colors.white,
            ),
            tooltip: _modoDelimitacion ? 'Finalizar y desplegar' : 'Delimitar terreno',
            onPressed: _desplegando
                ? null
                : () {
                    setState(() {
                      _modoDelimitacion = !_modoDelimitacion;
                      if (!_modoDelimitacion && _puntosDelimitacion.isNotEmpty) {
                        _calcularAreaYDesplegar(context);
                      }
                    });
                  },
          ),
        ],
      ),
      body: Consumer<DronProvider>(
        builder: (context, dronProvider, child) {
          if (dronProvider.alerta != null) {
            WidgetsBinding.instance.addPostFrameCallback((_) {
              _mostrarAlerta(context, dronProvider.alerta!, dronProvider);
            });
          }

          final colmena = LatLng(dronProvider.colmenaLat, dronProvider.colmenaLng);

          final marcadores = <gmaps.Marker>{
            gmaps.Marker(
              markerId: const gmaps.MarkerId('colmena'),
              position: _aGoogle(colmena),
              icon: gmaps.BitmapDescriptor.defaultMarkerWithHue(gmaps.BitmapDescriptor.hueGreen),
              infoWindow: const gmaps.InfoWindow(title: 'Colmena Solar'),
            ),
            ...dronProvider.drones.entries.map((entrada) {
              final dron = entrada.value;
              return gmaps.Marker(
                markerId: gmaps.MarkerId('dron-${entrada.key}'),
                position: gmaps.LatLng(dron.lat, dron.lng),
                icon: _iconoPorEstado(dron.estado),
                anchor: const Offset(0.5, 0.5),
                infoWindow: gmaps.InfoWindow(title: entrada.key, snippet: '${dron.bateria}% · ${dron.estado}'),
              );
            }),
            ..._puntosDelimitacion.asMap().entries.map((entrada) {
              return gmaps.Marker(
                markerId: gmaps.MarkerId('punto-${entrada.key}'),
                position: _aGoogle(entrada.value),
                icon: gmaps.BitmapDescriptor.defaultMarkerWithHue(gmaps.BitmapDescriptor.hueBlue),
              );
            }),
            if (dronProvider.ultimaPlagaLatLng != null)
              gmaps.Marker(
                markerId: const gmaps.MarkerId('plaga'),
                position: _aGoogle(dronProvider.ultimaPlagaLatLng!),
                icon: gmaps.BitmapDescriptor.defaultMarkerWithHue(gmaps.BitmapDescriptor.hueRose),
                infoWindow: const gmaps.InfoWindow(title: 'Plaga detectada (sensor real)'),
              ),
          };

          final poligonos = <gmaps.Polygon>{
            ...dronProvider.zonas.map((zona) {
              return gmaps.Polygon(
                polygonId: gmaps.PolygonId('zona-${zona.nombre}'),
                points: zona.puntos.map(_aGoogle).toList(),
                fillColor: zona.color.withOpacity(0.4),
                strokeColor: zona.color,
                strokeWidth: 2,
              );
            }),
            if (_puntosDelimitacion.length >= 3)
              gmaps.Polygon(
                polygonId: const gmaps.PolygonId('delimitacion'),
                points: _puntosDelimitacion.map(_aGoogle).toList(),
                fillColor: Colors.blue.withOpacity(0.25),
                strokeColor: Colors.blue,
                strokeWidth: 2,
              ),
          };

          return Stack(
            children: [
              gmaps.GoogleMap(
                initialCameraPosition: gmaps.CameraPosition(
                  target: _aGoogle(dronProvider.drones.isEmpty ? _centroInicial : colmena),
                  zoom: 17,
                ),
                mapType: gmaps.MapType.satellite,
                markers: marcadores,
                polygons: poligonos,
                onTap: (gmaps.LatLng punto) {
                  if (_modoDelimitacion) {
                    setState(() {
                      _puntosDelimitacion.add(_deGoogle(punto));
                    });
                    ScaffoldMessenger.of(context).showSnackBar(
                      SnackBar(
                        content: Text('📍 Punto ${_puntosDelimitacion.length} añadido'),
                        duration: const Duration(milliseconds: 500),
                      ),
                    );
                  }
                },
              ),

              // 📍 LEYENDA
              Positioned(
                bottom: 20,
                left: 20,
                child: Container(
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(
                    color: Colors.white.withOpacity(0.9),
                    borderRadius: BorderRadius.circular(12),
                    boxShadow: [
                      BoxShadow(color: Colors.black.withOpacity(0.2), blurRadius: 8),
                    ],
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Text(
                        '🌾 Enjambre en vivo',
                        style: TextStyle(fontWeight: FontWeight.bold, fontSize: 12),
                      ),
                      const SizedBox(height: 8),
                      _LeyendaItem(color: Colors.amber, label: '🐝 Patrullando / Tratando'),
                      _LeyendaItem(color: Colors.blue, label: '🐝 Regresando'),
                      _LeyendaItem(color: Colors.deepPurple, label: '🐝 Aterrizado (kill-switch)'),
                      const SizedBox(height: 4),
                      _LeyendaItem(color: Colors.green.shade800, label: '🏠 Colmena'),
                      if (_modoDelimitacion) ...[
                        const Divider(height: 16),
                        const Text(
                          '✏️ Modo delimitación activado',
                          style: TextStyle(color: Colors.blue, fontWeight: FontWeight.bold, fontSize: 12),
                        ),
                        Text(
                          'Puntos: ${_puntosDelimitacion.length} (mínimo 3)',
                          style: const TextStyle(color: Colors.grey, fontSize: 12),
                        ),
                      ],
                      const SizedBox(height: 4),
                      Text(
                        'Drones activos: ${dronProvider.dronesActivos}',
                        style: const TextStyle(fontSize: 12, fontWeight: FontWeight.bold),
                      ),
                      Text(
                        dronProvider.conectado ? 'Conectado en vivo' : 'Sin conexión al servidor',
                        style: TextStyle(
                          fontSize: 12,
                          color: dronProvider.conectado ? Colors.green : Colors.red,
                        ),
                      ),
                      if (dronProvider.compartida) ...[
                        const Divider(height: 12),
                        Text(
                          '🤝 Compartida (${dronProvider.terrenosEnColmena} clientes)',
                          style: const TextStyle(fontSize: 11, fontWeight: FontWeight.bold),
                        ),
                        Text(
                          dronProvider.esTuTurno ? 'Es tu turno ✅' : 'Esperando tu turno ⏳',
                          style: TextStyle(
                            fontSize: 11,
                            color: dronProvider.esTuTurno ? Colors.green : Colors.orange,
                          ),
                        ),
                      ],
                    ],
                  ),
                ),
              ),
              const PanelControles(),
            ],
          );
        },
      ),
    );
  }

  void _mostrarAlerta(BuildContext context, String mensaje, DronProvider provider) {
    if (ModalRoute.of(context)?.isCurrent != true) return;

    Color color = Colors.amber;
    IconData icon = Icons.warning_amber_rounded;
    if (mensaje.contains('Plaga') || mensaje.contains('PLAGA')) {
      color = Colors.red;
      icon = Icons.dangerous;
    }

    showDialog(
      context: context,
      barrierDismissible: false,
      builder: (BuildContext context) {
        return AlertDialog(
          icon: Icon(icon, color: color, size: 48),
          title: Text(
            '🚨 ¡ALERTA!',
            style: TextStyle(color: color, fontWeight: FontWeight.bold, fontSize: 20),
          ),
          content: Text(mensaje, style: const TextStyle(fontSize: 16)),
          actions: [
            TextButton(
              onPressed: () {
                Navigator.of(context).pop();
                provider.limpiarAlerta();
              },
              child: const Text('Entendido'),
            ),
          ],
        );
      },
    );
  }
}

// ============================================================
// WIDGET DE LEYENDA
// ============================================================
class _LeyendaItem extends StatelessWidget {
  final Color color;
  final String label;

  const _LeyendaItem({required this.color, required this.label});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 2),
      child: Row(
        children: [
          Container(
            width: 16,
            height: 16,
            decoration: BoxDecoration(color: color, shape: BoxShape.circle),
          ),
          const SizedBox(width: 8),
          Text(label, style: TextStyle(fontSize: 12, color: Colors.grey.shade800)),
        ],
      ),
    );
  }
}
