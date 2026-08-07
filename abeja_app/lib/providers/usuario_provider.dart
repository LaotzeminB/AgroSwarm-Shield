import 'package:flutter/material.dart';

class UsuarioProvider extends ChangeNotifier {
  // Datos de la sesión (llenados al iniciar sesión o registrarse)
  String usuario = '';
  String ranchoNombre = '';

  // Datos del cálculo de abejas recomendadas (pantalla de registro)
  String ubicacion = '';
  double areaHectareas = 0.0;
  int abejasRecomendadas = 0;
  String paquete = '';

  void establecerSesion({
    required String usuario,
    required String ranchoNombre,
  }) {
    this.usuario = usuario;
    this.ranchoNombre = ranchoNombre;
    notifyListeners();
  }

  void actualizarDatos({
    required String usuario,
    required String ubicacion,
    required double areaHectareas,
    required int abejasRecomendadas,
    required String paquete,
  }) {
    this.usuario = usuario;
    this.ubicacion = ubicacion;
    this.areaHectareas = areaHectareas;
    this.abejasRecomendadas = abejasRecomendadas;
    this.paquete = paquete;
    notifyListeners();
  }

  void cerrarSesion() {
    usuario = '';
    ranchoNombre = '';
    notifyListeners();
  }
}
