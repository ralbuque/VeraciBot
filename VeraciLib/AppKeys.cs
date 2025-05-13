using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Text.Json;
using System.Threading.Tasks;

namespace VeraciBot
{

    public class AppKeys
    {

        public string xClientId { get; set; } = string.Empty;
        public string xClientSecret { get; set; } = string.Empty;
        public string xApiKey { get; set; } = string.Empty;
        public string xApiSecret { get; set; } = string.Empty;
        public string xAccessToken { get; set; } = string.Empty;
        public string xAccessSecret { get; set; } = string.Empty;
        public string xBearerToken { get; set; } = string.Empty;
        public string xUserId { get; set; } = string.Empty;
        public string xUserName { get; set; } = string.Empty;
        public string openAIKey { get; set; } = string.Empty;
        public string sendGridKey { get; set; } = string.Empty;
        public string dbConnection { get; set; } = string.Empty;

        static AppKeys? appKeys = null;

        static string fileName = "appkeys.json";

        public static AppKeys keys
        {

            get
            {

                if (appKeys == null)
                {

                    if (!File.Exists(fileName))
                    {
                        string dir = Directory.GetCurrentDirectory();
                        throw new FileNotFoundException($"Arquivo \"{dir}/{fileName}\" não encontrado");
                    }

                    string json = File.ReadAllText(fileName);
                    appKeys = JsonSerializer.Deserialize<AppKeys>(json);

                }

                if (appKeys == null)
                    throw (new Exception("AppKeys.json error"));

                return appKeys;

            }

        }

    }

}
