
namespace LegacyApp
{
    public class PremiumCustomerService : CustomerService
    {
        public bool HasPremiumAccess(int customerId)
        {
            return customerId > 1000;
        }
    }
}
