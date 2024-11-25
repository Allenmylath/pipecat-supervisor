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
    title="Airflow Script Control API",
    description="API to control script execution in Airflow",
    version="1.0.0"
)

def run_script(**context):
    """Your script logic goes here"""
    print("Script is running...")
    # Add your script logic here
    while not context.get('task_instance').task.is_stopped():
        # Your script's main loop
        print("Processing...")
        time.sleep(10)  # Prevent CPU overuse

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
    'script_control_dag',
    default_args=default_args,
    description='DAG to control script execution',
    schedule_interval=None,
    catchup=False
)

# Task to run the script
run_script_task = PythonOperator(
    task_id='run_script',
    python_callable=run_script,
    dag=dag,
)

@app.post("/start_script", response_model=Dict[str, str])
async def start_script():
    """
    Start the script by triggering the DAG
    
    Returns:
        Dict containing status and message
    """
    try:
        trigger_dag(dag_id='script_control_dag')
        return {
            "status": "success",
            "message": "Script started successfully"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/stop_script", response_model=Dict[str, str])
async def stop_script():
    """
    Stop the script by setting the stop flag
    
    Returns:
        Dict containing status and message
    """
    try:
        # Get running DAG instances
        dag_runs = DagRun.find(dag_id='script_control_dag', state='running')
        
        if not dag_runs:
            return {
                "status": "warning",
                "message": "No running script instances found"
            }
        
        stopped_count = 0
        for dag_run in dag_runs:
            # Set stop flag for the task
            task_instances = dag_run.get_task_instances()
            for ti in task_instances:
                if ti.task_id == 'run_script':
                    ti.task.stop()
                    stopped_count += 1
        
        return {
            "status": "success",
            "message": f"Stop signal sent to {stopped_count} script instance(s)"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/status", response_model=Dict[str, str])
async def get_status():
    """
    Get the current status of the script
    
    Returns:
        Dict containing status information
    """
    try:
        dag_runs = DagRun.find(dag_id='script_control_dag', state='running')
        if dag_runs:
            return {
                "status": "running",
                "message": f"Script is running with {len(dag_runs)} active instance(s)"
            }
        return {
            "status": "stopped",
            "message": "No running instances found"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
