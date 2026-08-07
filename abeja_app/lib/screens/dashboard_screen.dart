import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../providers/usuario_provider.dart';
import '../providers/dron_provider.dart';
import '../services/api_service.dart';

class DashboardScreen extends StatelessWidget {
  const DashboardScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('🐝 Dashboard'),
        backgroundColor: Colors.green.shade800,
        foregroundColor: Colors.white,
        actions: [
          IconButton(
            icon: const Icon(Icons.logout),
            onPressed: () async {
              await ApiService.cerrarSesion();
              if (!context.mounted) return;
              Provider.of<DronProvider>(context, listen: false).desconectarTelemetria();
              Provider.of<UsuarioProvider>(context, listen: false).cerrarSesion();
              Navigator.pushReplacementNamed(context, '/');
            },
          ),
        ],
      ),
      body: Padding(
        padding: const EdgeInsets.all(16.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              'Estado del Enjambre',
              style: TextStyle(
                fontSize: 20,
                fontWeight: FontWeight.bold,
              ),
            ),
            const SizedBox(height: 16),

            // ============================================================
            // 📊 DATOS DEL USUARIO / RANCHO
            // ============================================================
            Consumer<UsuarioProvider>(
              builder: (context, usuarioProvider, child) {
                if (usuarioProvider.usuario.isEmpty) {
                  return const SizedBox.shrink();
                }
                return Container(
                  padding: const EdgeInsets.all(12),
                  margin: const EdgeInsets.only(bottom: 16),
                  decoration: BoxDecoration(
                    color: Colors.green.shade50,
                    borderRadius: BorderRadius.circular(12),
                    border: Border.all(color: Colors.green.shade300),
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        '👤 ${usuarioProvider.usuario}',
                        style: const TextStyle(
                          fontWeight: FontWeight.bold,
                          fontSize: 16,
                          color: Colors.black,
                        ),
                      ),
                      const SizedBox(height: 4),
                      Text(
                        '🏡 ${usuarioProvider.ranchoNombre}',
                        style: const TextStyle(color: Colors.black),
                      ),
                      if (usuarioProvider.abejasRecomendadas > 0) ...[
                        Text(
                          '🐝 ${usuarioProvider.abejasRecomendadas} abejas recomendadas',
                          style: TextStyle(
                            fontWeight: FontWeight.bold,
                            color: Colors.amber.shade700,
                          ),
                        ),
                      ],
                    ],
                  ),
                );
              },
            ),

            // ============================================================
            // TARJETAS DE ESTADO (datos REALES del backend, en vivo)
            // ============================================================
            Consumer<DronProvider>(
              builder: (context, dronProvider, child) {
                return Column(
                  children: [
                    Row(
                      children: [
                        Expanded(
                          child: _TarjetaEstado(
                            icon: Icons.smart_toy,
                            valor: '${dronProvider.dronesActivos}',
                            label: 'Drones Activos',
                            color: Colors.green,
                          ),
                        ),
                        const SizedBox(width: 12),
                        Expanded(
                          child: _TarjetaEstado(
                            icon: Icons.battery_6_bar,
                            valor: '${dronProvider.bateriaPromedio}%',
                            label: 'Batería Promedio',
                            color: Colors.amber,
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 12),
                    Row(
                      children: [
                        Expanded(
                          child: _TarjetaEstado(
                            icon: Icons.shield,
                            valor: '${dronProvider.totalIntrusiones}',
                            label: 'Intrusiones Bloqueadas',
                            color: Colors.blue,
                          ),
                        ),
                        const SizedBox(width: 12),
                        Expanded(
                          child: _TarjetaEstado(
                            icon: Icons.wifi,
                            valor: dronProvider.conectado ? 'En vivo' : 'Sin conexión',
                            label: 'Servidor',
                            color: dronProvider.conectado ? Colors.orange : Colors.red,
                          ),
                        ),
                      ],
                    ),
                    if (dronProvider.compartida) ...[
                      const SizedBox(height: 12),
                      Container(
                        width: double.infinity,
                        padding: const EdgeInsets.all(12),
                        decoration: BoxDecoration(
                          color: dronProvider.esTuTurno
                              ? Colors.green.withOpacity(0.15)
                              : Colors.orange.withOpacity(0.15),
                          borderRadius: BorderRadius.circular(12),
                          border: Border.all(
                            color: dronProvider.esTuTurno ? Colors.green : Colors.orange,
                          ),
                        ),
                        child: Row(
                          children: [
                            Icon(
                              dronProvider.esTuTurno ? Icons.flight_takeoff : Icons.hourglass_bottom,
                              color: dronProvider.esTuTurno ? Colors.green : Colors.orange,
                            ),
                            const SizedBox(width: 8),
                            Expanded(
                              child: Text(
                                dronProvider.esTuTurno
                                    ? '🤝 Colmena compartida (${dronProvider.terrenosEnColmena} clientes) — es tu turno de patrullaje'
                                    : '🤝 Colmena compartida (${dronProvider.terrenosEnColmena} clientes) — esperando tu turno',
                                style: const TextStyle(fontSize: 12, fontWeight: FontWeight.bold),
                              ),
                            ),
                          ],
                        ),
                      ),
                    ],
                  ],
                );
              },
            ),
            const SizedBox(height: 24),

            // Botón "ABRIR MAPA"
            SizedBox(
              width: double.infinity,
              height: 56,
              child: ElevatedButton.icon(
                onPressed: () {
                  Navigator.pushNamed(context, '/mapa');
                },
                icon: const Icon(Icons.map),
                label: const Text(
                  'ABRIR MAPA',
                  style: TextStyle(
                    fontSize: 18,
                    fontWeight: FontWeight.bold,
                  ),
                ),
                style: ElevatedButton.styleFrom(
                  backgroundColor: Colors.amber.shade700,
                  foregroundColor: Colors.white,
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(12),
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

// ============================================================
// WIDGET DE TARJETA DE ESTADO
// ============================================================
class _TarjetaEstado extends StatelessWidget {
  final IconData icon;
  final String valor;
  final String label;
  final Color color;

  const _TarjetaEstado({
    required this.icon,
    required this.valor,
    required this.label,
    required this.color,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: color.withOpacity(0.1),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: color, width: 1),
      ),
      child: Column(
        children: [
          Icon(icon, color: color, size: 32),
          const SizedBox(height: 8),
          Text(
            valor,
            style: TextStyle(
              fontSize: 22,
              fontWeight: FontWeight.bold,
              color: color,
            ),
          ),
          Text(
            label,
            style: TextStyle(
              fontSize: 12,
              color: color,
            ),
          ),
        ],
      ),
    );
  }
}
