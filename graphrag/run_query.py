import os
import subprocess
import sys
import argparse
from dotenv import load_dotenv

# Load root .env to get OPENAI_API_KEY
root_env = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '.env'))
load_dotenv(root_env)

api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    print("Error: OPENAI_API_KEY not found in root .env file.")
    sys.exit(1)

os.environ["GRAPHRAG_API_KEY"] = api_key

def run_query(query: str, method: str):
    print(f"Running {method} search with GraphRAG for: '{query}'")
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    try:
        # Run graphrag query
        subprocess.run(
            [sys.executable, "-m", "graphrag", "query", "--root", script_dir, "--method", method, query],
            check=True,
            env=os.environ
        )
    except subprocess.CalledProcessError as e:
        print(f"\nError during query: {e}")
        sys.exit(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Query GraphRAG")
    parser.add_argument("query", type=str, help="Search query")
    parser.add_argument("--method", type=str, default="local", choices=["local", "global", "drift"], help="Query method (local, global, drift)")
    args = parser.parse_args()
    
    run_query(args.query, args.method)
