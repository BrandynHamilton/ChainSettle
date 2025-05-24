import os
import time
import requests
import click

from dotenv import load_dotenv
load_dotenv()

from concurrent.futures import ThreadPoolExecutor, as_completed
from statistics import mean

@click.command()
@click.option('--settlement-id', required=True)
@click.option('--local',      is_flag=True, default=False)
@click.option('--workers',    default=50, help='Number of parallel threads')
@click.option('--num-requests',   default=1000, help='Total number of requests to send')
def main(settlement_id, local, workers, num_requests):
    url = os.getenv('LOCAL_URL') if local else os.getenv('BACKEND_URL')
    endpoint = f"{url}/api/get_settlement/{settlement_id}"
    print(f"► Stress-testing {endpoint} with {workers} workers, {num_requests} total calls…")

    start_all = time.monotonic()

    def call(i):
        start = time.monotonic()
        r = requests.get(endpoint)
        dt = time.monotonic() - start
        return i, r.status_code, dt

    latencies = []
    errors = 0

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(call, i) for i in range(num_requests)]
        for future in as_completed(futures):
            i, code, dt = future.result()
            latencies.append(dt)
            if code != 200:
                errors += 1
            # optional live log
            print(f"[{i:4d}] {code} {dt*1000:6.1f}ms")

    total_time = time.monotonic() - start_all

    print("\n=== Results ===")
    print(f"Total time     : {total_time:.2f}s")
    print(f"Total requests : {num_requests}")
    print(f"Errors         : {errors}")
    print(f"Avg latency    : {mean(latencies)*1000:.1f}ms")
    print(f"Max latency    : {max(latencies)*1000:.1f}ms")
    print(f"P95 latency    : {sorted(latencies)[int(0.95*len(latencies))]*1000:.1f}ms")

if __name__ == "__main__":
    main()
