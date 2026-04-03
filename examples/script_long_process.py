"""Long running script for manual testing of qara.

Usage:
    qara run python examples/script_long_process.py --name "long-process"

Prerequisites:
    None
"""

import time
from datetime import datetime, timezone

def main():
    print("Process started")

    iteration = 0
    start_time = time.time()
    duration = 5 * 60  # 5 minutes in seconds

    while time.time() - start_time < duration:
        iteration += 1

        # Simulated work
        time.sleep(5)

        uptime = int(time.time() - start_time)
        print(
            f"{datetime.now(timezone.utc).isoformat()}Z | iteration={iteration} | uptime={uptime}s"
        )

    print("Process finished after 5 minutes")


if __name__ == "__main__":
    main()