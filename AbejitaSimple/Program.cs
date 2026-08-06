using AbejitaSimple.Models;
using AbejitaSimple.Database;
using MongoDB.Bson;

var builder = WebApplication.CreateBuilder(args);
var app = builder.Build();

Mongo mongo = new Mongo();
Random rnd = new Random();

Console.WriteLine("Iniciando Abejita (Simulador + API)...");

Terreno terreno = new Terreno
{
    LatMin = 21.85,
    LatMax = 21.90,
    LonMin = -102.30,
    LonMax = -102.25
};

Task.Run(async () =>
{
    while (true)
    {
        double lat = 21.85 + rnd.NextDouble() * 0.05;
        double lon = -102.30 + rnd.NextDouble() * 0.05;

        Telemetria t = new Telemetria
        {
            Timestamp = DateTime.Now,
            Lat = lat,
            Lon = lon,
            Altura = rnd.Next(1, 20),
            Velocidad = rnd.Next(1, 5),
            PlagaDetectada = rnd.Next(0, 10) == 5
        };

        await mongo.GuardarTelemetria(t);

        Console.WriteLine($"[Sim] Lat:{t.Lat:F5} Lon:{t.Lon:F5} Alt:{t.Altura} Vel:{t.Velocidad} Plaga:{t.PlagaDetectada}");

        await Task.Delay(500);
    }
});

app.MapGet("/", () => "API Abejita funcionando");

app.MapGet("/api/telemetria/ultimos/{cantidad}", async (int cantidad) =>
{
    var datos = await mongo.ObtenerUltimos(cantidad);
    return Results.Json(datos);
});

app.Run();
