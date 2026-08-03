import 'package:flutter/material.dart';

class DronProvider extends ChangeNotifier {
  // Datos del dron/abeja
  double lat = 19.4326;
  double lng = -99.1332;
  double altitud = 50.0;
  int bateria = 85;
  String estado = 'idle'; // idle, despegando, patrullando, regresando, cargando

  // Métodos para actualizar
  void actualizarPosicion(double nuevaLat, double nuevoLng, double nuevaAlt) {
    lat = nuevaLat;
    lng = nuevoLng;
    altitud = nuevaAlt;
    bateria -= 1; // Simula consumo de batería
    notifyListeners();
  }

  void cambiarEstado(String nuevoEstado) {
    estado = nuevoEstado;
    notifyListeners();
  }

  void recargarBateria() {
    bateria = 100;
    cambiarEstado('cargando');
    Future.delayed(Duration(seconds: 2), () {
      cambiarEstado('idle');
    });
  }
}