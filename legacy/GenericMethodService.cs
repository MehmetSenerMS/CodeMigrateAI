
namespace LegacyApp
{
    public class GenericMethodService
    {
        public T ConvertValue<T>(object value)
        {
            return (T)value;
        }

        public string GetName()
        {
            return "Customer";
        }
    }
}
