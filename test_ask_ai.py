
import asyncio
from dbus_next.aio import MessageBus
from dbus_next import BusType

async def ask_ai_test():
    bus = await MessageBus(bus_type=BusType.SESSION).connect()
    
    introspection = await bus.introspect('com.nervaos.daemon', '/com/nervaos/daemon')
    proxy = bus.get_proxy_object('com.nervaos.daemon', '/com/nervaos/daemon', introspection)
    interface = proxy.get_interface('com.nervaos.daemon')
    
    print("Calling AskAI('hello')...")
    try:
        response = await interface.call_ask_ai("hello")
        print(f"Response: {response}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(ask_ai_test())
