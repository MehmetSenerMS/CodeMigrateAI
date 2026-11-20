using System.Configuration;

namespace LegacyApp
{
    public class NotificationSettings
    {
        public string GetSenderName()
        {
            return ConfigurationManager.AppSettings["SenderName"]
                ?? "CodeMigrate";
        }
    }
}