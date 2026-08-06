using MongoDB.Driver;
using MongoDB.Bson;
using AbejitaSimple.Models;

namespace AbejitaSimple.Database
{
    public class Mongo
    {
        private readonly IMongoCollection<BsonDocument> _telemetria;
        private readonly IMongoClient _client;
        private bool _isConnected;

        public Mongo()
        {
            try
            {
                _client = new MongoClient("mongodb://localhost:27017");
                var db = _client.GetDatabase("AbejitaDB");

                // Intento de ping para verificar conexión
                var command = new BsonDocument("ping", 1);
                db.RunCommand<BsonDocument>(command);

                _telemetria = db.GetCollection<BsonDocument>("Telemetria");
                _isConnected = true;
                Console.WriteLine("MongoDB: conexión establecida correctamente.");
            }
            catch (Exception ex)
            {
                _isConnected = false;
                Console.WriteLine($"MongoDB: no se pudo conectar - {ex.Message}");
                // Crear cliente y colección de todas formas para evitar null refs; las operaciones de escritura comprobarán _isConnected
                _client = new MongoClient("mongodb://localhost:27017");
                var db = _client.GetDatabase("AbejitaDB");
                _telemetria = db.GetCollection<BsonDocument>("Telemetria");
            }
        }

        public async Task GuardarTelemetria(Telemetria t)
        {
            var doc = new BsonDocument
            {
                { "timestamp", t.Timestamp },
                { "lat", t.Lat },
                { "lon", t.Lon },
                { "altura", t.Altura },
                { "velocidad", t.Velocidad },
                { "plagaDetectada", t.PlagaDetectada }
            };

            if (!_isConnected)
            {
                Console.WriteLine("GuardarTelemetria: MongoDB no está conectado. Saltando inserción.");
                return;
            }

            try
            {
                await _telemetria.InsertOneAsync(doc);
            }
            catch (Exception ex)
            {
                Console.WriteLine($"Error al insertar telemetría en MongoDB: {ex.Message}");
            }
        }

        public async Task<List<BsonDocument>> ObtenerUltimos(int cantidad)
        {
            return await _telemetria
                .Find(new BsonDocument())
                .Sort("{ timestamp: -1 }")
                .Limit(cantidad)
                .ToListAsync();
        }
    }
}
