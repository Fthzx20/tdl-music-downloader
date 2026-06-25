import asyncio
import threading
import sys
from tidal_rip.config import Config
from tidal_rip.api import TidalAPI
from tidal_rip.ui import AppUI

def main():
    # 1. Initialize Configuration
    config = Config()

    # 2. Setup background asyncio event loop
    async_loop = asyncio.new_event_loop()
    
    def run_async_loop(loop):
        asyncio.set_event_loop(loop)
        loop.run_forever()

    # Start loop in a daemon thread so it exits with the main process
    async_thread = threading.Thread(target=run_async_loop, args=(async_loop,), daemon=True)
    async_thread.start()

    # 3. Initialize API client
    api = TidalAPI(config)

    # 4. Initialize and launch GUI
    app = AppUI(api, config, async_loop)
    
    # Clean shutdown handler
    def on_closing():
        print("Closing application...")
        # Run cleanup synchronously in the async loop
        async def cleanup():
            # Cancel all running tasks to prevent warnings
            current_task = asyncio.current_task(async_loop)
            tasks = [task for task in asyncio.all_tasks(async_loop) if task is not current_task]
            for task in tasks:
                task.cancel()
            if tasks:
                # Wait for all tasks to acknowledge cancellation
                await asyncio.gather(*tasks, return_exceptions=True)
            await api.close()
        
        future = asyncio.run_coroutine_threadsafe(cleanup(), async_loop)
        try:
            future.result(timeout=2.0)
        except Exception as e:
            print(f"Error during clean shutdown: {e}")
            
        async_loop.call_soon_threadsafe(async_loop.stop)
        app.destroy()
        sys.exit(0)

    app.protocol("WM_DELETE_WINDOW", on_closing)
    app.mainloop()

if __name__ == "__main__":
    main()
