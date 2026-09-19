import argparse
import sys
from pathlib import Path

def main():
    parser = argparse.ArgumentParser(description="Enroll a new face into Argus.")
    parser.add_argument("--name", required=True, help="Name of the person")
    parser.add_argument("--images", required=False, help="Directory containing images of the person")
    
    args = parser.parse_args()
    
    print(f"[*] Enrolling face for: {args.name}")
    print("[!] Face enrollment logic to be implemented using InsightFace.")
    # TODO: Load InsightFace model, process images, generate embeddings, and save to SQLite DB.

if __name__ == "__main__":
    main()
