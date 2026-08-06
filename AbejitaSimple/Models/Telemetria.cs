namespace AbejitaSimple.Models
{
    public class Telemetria
    {
        public DateTime Timestamp { get; set; }
        public double Lat { get; set; }
        public double Lon { get; set; }
        public int Altura { get; set; }
        public int Velocidad { get; set; }
        public bool PlagaDetectada { get; set; }
    }
}
