using System;

namespace LegacyApp
{
    public class CustomerService
    {
        public string GetCustomerName(int customerId)
        {
            return "Customer_" + customerId;
        }

        public bool IsCustomerActive(int customerId)
        {
            return customerId > 0;
        }
    }
}
