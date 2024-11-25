import os
import sys
import subprocess
import signal
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.models import DagRun
from airflow.api.common.experimental.trigger_dag import trigger_dag
from airflow.utils.dates import days_ago
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from datetime import datetime, timedelta
import uvicorn
import time
from typing import Dict

# Create FastAPI app
app = FastAPI(
    title="Bot Control API",
    description="API to control bot.py execution",
    version="1.0.0"
)

# Global variable to store the bot process
bot_process = None

def run_bot(**context):
    """Run the bot.py script"""
    global bot_process
    
    # Get the directory where this DAG file is located
    current_dir = os.path.dirname(os.path.abspath(__file__))
    bot_path = os.path.join(current_dir, 'bot.py')
    
    if not os.path.exists(bot_path):
        raise FileNotFoundError(f"bot.py not found in {current_dir}")
    
    try:
        # Start bot.py as a subprocess
        bot_process = subprocess.Popen([sys.executable, bot_path],
                                     stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE)
        
        # Monitor the process
        while not context.get('task_instance').task.is_stopped():
            if bot_process.poll() is not None:
                # Process has terminated
                break
            time.sleep(1)
            
        # If we get here and the process is still running, terminate it
        if bot_process.poll() is None:
            bot_process.terminate()
            bot_process.wait(timeout=5)
            
    except Exception as e:
        print(f"Error running bot: {str(e)}")
        if bot_process and bot_process.poll() is None:
            bot_process.terminate()
        raise

default_args = {
    'owner': 'airflow',
    'depends_on_past': False,
    'start_date': days_ago(1),
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
}

# Define the DAG
dag = DAG(
    'bot_control_dag',
    default_args=default_args,
    description='DAG to control bot.py execution',
    schedule_interval=None,
    catchup=False
)

# Task to run the bot
run_bot_task = PythonOperator(
    task_id='run_bot',
    python_callable=run_bot,
    dag=dag,
)

@app.post("/start_bot", response_model=Dict[str, str])
async def start_bot():
    """
    Start the bot by triggering the DAG
    """
    try:
        # Check if bot is already running
        dag_runs = DagRun.find(dag_id='bot_control_dag', state='running')
        if dag_runs:
            return {
                "status": "warning",
                "message": "Bot is already running"
            }
            
        trigger_dag(dag_id='bot_control_dag')
        return {
            "status": "success",
            "message": "Bot started successfully"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/stop_bot", response_model=Dict[str, str])
async def stop_bot():
    """
    Stop the bot by setting the stop flag and terminating the process
    """
    global bot_process
    try:
        dag_runs = DagRun.find(dag_id='bot_control_dag', state='running')
        
        if not dag_runs:
            return {
                "status": "warning",
                "message": "No running bot instances found"
            }
        
        # Stop the bot process if it exists
        if bot_process and bot_process.poll() is None:
            bot_process.terminate()
            try:
                bot_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                bot_process.kill()
        
        # Stop the Airflow task
        for dag_run in dag_runs:
            task_instances = dag_run.get_task_instances()
            for ti in task_instances:
                if ti.task_id == 'run_bot':
                    ti.task.stop()
        
        return {
            "status": "success",
            "message": "Bot stopped successfully"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/status", response_model=Dict[str, str])
async def get_status():
    """
    Get the current status of the bot
    """
    global bot_process
    try:
        dag_runs = DagRun.find(dag_id='bot_control_dag', state='running')
        
        # Check both DAG and process status
        is_dag_running = bool(dag_runs)
        is_process_running = bot_process is not None and bot_process.poll() is None
        
        if is_dag_running and is_process_running:
            return {
                "status": "running",
                "message": "Bot is running"
            }
        elif is_dag_running:
            return {
                "status": "warning",
                "message": "DAG is running but bot process is not active"
            }
        elif is_process_running:
            return {
                "status": "warning",
                "message": "Bot process is running but DAG is not active"
            }
        return {
            "status": "stopped",
            "message": "Bot is not running"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
