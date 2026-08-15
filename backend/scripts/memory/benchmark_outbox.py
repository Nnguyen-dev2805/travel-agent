import sys
import time
import os
import subprocess
from pathlib import Path
from typing import List

# Setup path
project_root = str(Path(__file__).resolve().parent.parent.parent.parent)
if project_root not in sys.path:
    sys.path.append(project_root)

from backend.app.database import SessionLocal, engine, Base
from backend.app.models.memory import MemoryOutbox, UserMemory
from sqlalchemy import select, delete

def setup_benchmark_data(db, num_events: int):
    print(f"Setting up {num_events} benchmark events...")
    
    # 1. Clean existing dummy benchmark data
    db.execute(delete(MemoryOutbox).where(MemoryOutbox.memory_id.like("bench_%")))
    db.execute(delete(UserMemory).where(UserMemory.memory_id.like("bench_%")))
    db.commit()
    
    # 2. Insert UserMemory records
    memories = []
    for i in range(num_events):
        mem = UserMemory(
            memory_id=f"bench_{i}",
            user_id="bench_user",
            fact_type="benchmark",
            fact_key=f"key_{i}",
            content=f"This is a benchmark memory content number {i} with some random text to simulate real data."
        )
        memories.append(mem)
    db.add_all(memories)
    db.commit()
    
    # 3. Insert MemoryOutbox records
    events = []
    for i in range(num_events):
        event = MemoryOutbox(
            memory_id=f"bench_{i}",
            action="UPSERT",
            status="PENDING",
            retry_count=0
        )
        events.append(event)
    db.add_all(events)
    db.commit()
    print(f"Inserted {num_events} PENDING events.")

def run_benchmark(num_events: int):
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    
    try:
        setup_benchmark_data(db, num_events)
        
        # Start worker subprocess
        worker_script = os.path.join(project_root, "backend", "workers", "outbox_worker.py")
        print(f"Starting worker subprocess: python {worker_script}")
        
        # Start timer
        start_time = time.time()
        
        process = subprocess.Popen([sys.executable, worker_script])
        
        # Monitor DB
        while True:
            # Query count of pending events for benchmark
            stmt = select(MemoryOutbox).where(
                MemoryOutbox.memory_id.like("bench_%"),
                MemoryOutbox.status == "PENDING"
            )
            pending_count = len(list(db.scalars(stmt).all()))
            
            if pending_count == 0:
                break
                
            time.sleep(0.5) # Poll every 0.5s
            
        end_time = time.time()
        total_time = end_time - start_time
        
        # Kill worker
        process.terminate()
        process.wait()
        
        throughput = num_events / total_time if total_time > 0 else 0
        latency_per_event = (total_time / num_events) * 1000 if num_events > 0 else 0
        
        print("\n" + "="*50)
        print(f"BENCHMARK RESULTS ({num_events} events)")
        print("="*50)
        print(f"Total Time:      {total_time:.2f} seconds")
        print(f"Throughput:      {throughput:.2f} events/sec")
        print(f"Latency/event:   {latency_per_event:.2f} ms")
        print("="*50 + "\n")
        
    finally:
        # Cleanup
        db.execute(delete(MemoryOutbox).where(MemoryOutbox.memory_id.like("bench_%")))
        db.execute(delete(UserMemory).where(UserMemory.memory_id.like("bench_%")))
        db.commit()
        db.close()

if __name__ == "__main__":
    # We will test 50 events for the baseline.
    run_benchmark(50)
