import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:latlong2/latlong.dart';
import '../providers/dron_provider.dart';

class PanelControles extends StatefulWidget {
  const PanelControles({super.key});

  @override
  State<PanelControles> createState() => _PanelControlesState();
}

class _PanelControlesState extends State<PanelControles> {
  bool _isExpanded = true;
  bool _enviando = false;

  Future<void> _desplegarRapido(DronProvider dronProvider) async {
    // Sin un polígono dibujado a mano: despliega un terreno pequeño
    // alrededor de la colmena actual, para que el botón funcione también
    // sin tener que ir primero a "delimitar terreno".
    final base = LatLng(dronProvider.colmenaLat, dronProvider.colmenaLng);
    const delta = 0.0015;
    final poligono = [
      LatLng(base.latitude - delta, base.longitude - delta),
      LatLng(base.latitude + delta, base.longitude - delta),
      LatLng(base.latitude + delta, base.longitude + delta),
      LatLng(base.latitude - delta, base.longitude + delta),
    ];
    await _ejecutar(
      () => dronProvider.desplegarEnjambre(
        terrenoId: 'TERRENO-RAPIDO-${DateTime.now().millisecondsSinceEpoch}',
        poligono: poligono,
        numDrones: 5,
      ),
      mensajeExito: '🚀 Enjambre desplegado',
      colorExito: Colors.green,
    );
  }

  Future<void> _ejecutar(
    Future<void> Function() accion, {
    required String mensajeExito,
    required Color colorExito,
  }) async {
    setState(() => _enviando = true);
    try {
      await accion();
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(mensajeExito),
          backgroundColor: colorExito,
          duration: const Duration(seconds: 2),
        ),
      );
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('❌ $e'),
          backgroundColor: Colors.red,
          duration: const Duration(seconds: 3),
        ),
      );
    } finally {
      if (mounted) setState(() => _enviando = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<DronProvider>(
      builder: (context, dronProvider, child) {
        return Positioned(
          bottom: 20,
          right: 20,
          child: Container(
            width: _isExpanded ? 220 : 60,
            decoration: BoxDecoration(
              color: Colors.white.withOpacity(0.95),
              borderRadius: BorderRadius.circular(16),
              boxShadow: [
                BoxShadow(
                  color: Colors.black.withOpacity(0.3),
                  blurRadius: 12,
                  offset: const Offset(0, 4),
                ),
              ],
            ),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                InkWell(
                  onTap: () => setState(() => _isExpanded = !_isExpanded),
                  borderRadius: BorderRadius.circular(16),
                  child: Padding(
                    padding: const EdgeInsets.all(12),
                    child: Row(
                      children: [
                        Icon(
                          _isExpanded ? Icons.expand_more : Icons.expand_less,
                          color: Colors.green.shade800,
                        ),
                        if (_isExpanded) ...[
                          const SizedBox(width: 8),
                          Expanded(
                            child: Text(
                              '🎮 Panel de Control',
                              style: TextStyle(
                                fontWeight: FontWeight.bold,
                                color: Colors.green.shade800,
                              ),
                              overflow: TextOverflow.ellipsis,
                            ),
                          ),
                          const Spacer(),
                          Container(
                            width: 10,
                            height: 10,
                            decoration: BoxDecoration(
                              color: dronProvider.conectado ? Colors.green : Colors.red,
                              shape: BoxShape.circle,
                            ),
                          ),
                        ],
                      ],
                    ),
                  ),
                ),
                if (_isExpanded) ...[
                  const Divider(height: 1),
                  Padding(
                    padding: const EdgeInsets.all(12),
                    child: Column(
                      children: [
                        Row(
                          children: [
                            const Icon(Icons.info_outline, size: 16, color: Colors.grey),
                            const SizedBox(width: 8),
                            Expanded(
                              child: Text(
                                'Drones: ${dronProvider.dronesActivos}',
                                style: const TextStyle(fontSize: 12),
                                overflow: TextOverflow.ellipsis,
                              ),
                            ),
                          ],
                        ),
                        const SizedBox(height: 8),
                        Row(
                          children: [
                            const Icon(Icons.battery_6_bar, size: 16, color: Colors.grey),
                            const SizedBox(width: 8),
                            Expanded(
                              child: Text(
                                'Batería prom.: ${dronProvider.bateriaPromedio}%',
                                style: TextStyle(
                                  fontSize: 12,
                                  color: dronProvider.bateriaPromedio > 60 ? Colors.green : Colors.red,
                                ),
                              ),
                            ),
                          ],
                        ),
                        const SizedBox(height: 12),

                        _BotonAccion(
                          icon: Icons.flight_takeoff,
                          label: 'Desplegar Enjambre',
                          color: Colors.green.shade700,
                          enviando: _enviando,
                          onPressed: () => _desplegarRapido(dronProvider),
                        ),
                        const SizedBox(height: 8),

                        _BotonAccion(
                          icon: Icons.pause_circle_filled,
                          label: 'Pausa / Retorno',
                          color: Colors.orange.shade700,
                          enviando: _enviando,
                          onPressed: () => _mostrarDialogoPausa(context, dronProvider),
                        ),
                        const SizedBox(height: 8),

                        _BotonAccion(
                          icon: Icons.power_off,
                          label: 'KILL-SWITCH',
                          color: Colors.red.shade700,
                          enviando: _enviando,
                          onPressed: () => _mostrarDialogoKill(context, dronProvider),
                        ),
                      ],
                    ),
                  ),
                ],
              ],
            ),
          ),
        );
      },
    );
  }

  void _mostrarDialogoPausa(BuildContext context, DronProvider dronProvider) {
    showDialog(
      context: context,
      barrierDismissible: false,
      builder: (BuildContext context) {
        return AlertDialog(
          title: const Text('⏸️ Opciones de Pausa'),
          content: const Text(
            // El backend solo sabe mandar al enjambre de regreso a la
            // colmena (no existe un "pausar en el aire" de verdad todavía).
            '¿Qué deseas hacer con el enjambre?',
            style: TextStyle(fontSize: 16),
          ),
          actions: [
            ElevatedButton.icon(
              onPressed: () {
                Navigator.of(context).pop();
                _ejecutar(
                  () => dronProvider.activarKillSwitch('Pausa solicitada desde la app'),
                  mensajeExito: '⏸️ El enjambre está regresando a la colmena',
                  colorExito: Colors.orange,
                );
              },
              icon: const Icon(Icons.pause),
              label: const Text('Pausar'),
              style: ElevatedButton.styleFrom(
                backgroundColor: Colors.orange.shade700,
                foregroundColor: Colors.white,
              ),
            ),
            const SizedBox(width: 8),
            ElevatedButton.icon(
              onPressed: () {
                Navigator.of(context).pop();
                _ejecutar(
                  () => dronProvider.activarKillSwitch('Retorno a base solicitado desde la app'),
                  mensajeExito: '🏠 Retornando a Base...',
                  colorExito: Colors.blue,
                );
              },
              icon: const Icon(Icons.home),
              label: const Text('Retornar a Base'),
              style: ElevatedButton.styleFrom(
                backgroundColor: Colors.blue.shade700,
                foregroundColor: Colors.white,
              ),
            ),
          ],
        );
      },
    );
  }

  void _mostrarDialogoKill(BuildContext context, DronProvider dronProvider) {
    showDialog(
      context: context,
      barrierDismissible: false,
      builder: (BuildContext context) {
        return AlertDialog(
          title: const Text('🛑 ¡ATENCIÓN!'),
          content: const Text(
            '¿Estás seguro de que quieres activar el KILL-SWITCH?\n\n'
            'Esto detendrá TODOS los drones de inmediato.',
            style: TextStyle(fontSize: 16),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(context).pop(),
              child: const Text('Cancelar'),
            ),
            ElevatedButton(
              style: ElevatedButton.styleFrom(
                backgroundColor: Colors.red.shade700,
                foregroundColor: Colors.white,
              ),
              onPressed: () {
                Navigator.of(context).pop();
                _ejecutar(
                  () => dronProvider.activarKillSwitch('Kill-switch activado desde la app'),
                  mensajeExito: '🔴 KILL-SWITCH ACTIVADO',
                  colorExito: Colors.red,
                );
              },
              child: const Text('¡ACTIVAR!'),
            ),
          ],
        );
      },
    );
  }
}

// ============================================================
// WIDGET DE BOTÓN DE ACCIÓN
// ============================================================
class _BotonAccion extends StatelessWidget {
  final IconData icon;
  final String label;
  final Color color;
  final bool enviando;
  final VoidCallback onPressed;

  const _BotonAccion({
    required this.icon,
    required this.label,
    required this.color,
    required this.enviando,
    required this.onPressed,
  });

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: double.infinity,
      child: ElevatedButton.icon(
        onPressed: enviando ? null : onPressed,
        icon: Icon(icon, color: Colors.white),
        label: Text(
          label,
          style: const TextStyle(
            color: Colors.white,
            fontWeight: FontWeight.bold,
          ),
        ),
        style: ElevatedButton.styleFrom(
          backgroundColor: color,
          foregroundColor: Colors.white,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(10),
          ),
          padding: const EdgeInsets.symmetric(vertical: 12),
          elevation: 2,
        ),
      ),
    );
  }
}
