import os
import subprocess
import sys
from dotenv import load_dotenv

# Load root .env to get OPENAI_API_KEY
root_env = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '.env'))
load_dotenv(root_env)

# GraphRAG expects GRAPHRAG_API_KEY in its environment
api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    print("Error: OPENAI_API_KEY not found in root .env file.")
    sys.exit(1)

os.environ["GRAPHRAG_API_KEY"] = api_key

def run_index():
    print("Starting GraphRAG indexing process...")
    # Add root to PYTHONPATH so we can run graphrag from the virtual environment
    venv_python = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '.venv', 'bin', 'python'))
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    try:
        subprocess.run(
            [venv_python, "-m", "graphrag", "index", "--root", script_dir],
            check=True,
            env=os.environ
        )
        print("\nIndexing completed successfully.")
    except subprocess.CalledProcessError as e:
        print(f"\nError during indexing: {e}")
        sys.exit(1)

if __name__ == "__main__":
    run_index()
