import 'package:flutter/material.dart';

void main() {
  runApp(const MyApp());
}

class MyApp extends StatelessWidget {
  const MyApp({super.key});

  // This widget is the root of your application.
  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'BitBee',
      theme: ThemeData(
        primaryColor: Colors.green.shade800 ,
        colorScheme: ColorScheme.dark(
          primary: Colors.green.shade800,
          secondary: Colors.amber.shade700,
        ),
        
      ),
      home: const Scaffold(
        body:Center(child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(Icons.agriculture,
            size:80,
            color: Colors.green,),
            SizedBox(height: 20),
            Text(
              'Bienvenido',
              style: TextStyle(
                fontSize:24,
                fontWeight: FontWeight.bold,
                color: Colors.green,
              ),
            ),
            SizedBox(height: 10),
            Text(
              '¡Bienvenido a la jardineria!',
              style: TextStyle(fontSize: 18, color: Colors.grey),
            ),
          ],
        ),),
      ),
    );
  }
}