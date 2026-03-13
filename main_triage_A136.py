import os
import re
import json
import csv
from openai import OpenAI
from dotenv import load_dotenv
from private_prompts_multi import get_triage_prompt

load_dotenv()

# Initialize OpenAI client
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

def load_markdown(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        return f.read()

import re

def smart_chunking(markdown_text, max_chars=3500, overlap_paragraphs=1):
    """Parses the Markdown file safely with Hierarchical Breadcrumbs and Overlap."""
    chunks = []
    header_stack = {}  
    current_section = "Unknown Section"
    paragraphs = markdown_text.split('\n\n')
    
    current_chunk = ""
    recent_paragraphs = [] # Tracks paragraphs in the current chunk for overlap

    for p in paragraphs:
        first_line = p.strip()
        if not first_line:
            continue

        # Update hierarchical breadcrumb if we hit a Markdown header
        # Only accept headers that start with a Roman Numeral, an OMB section number, or a capital letter list item
        header_match = re.match(r'^(#{1,6})\s+([IVX]+\.|[A-Z]\.|\d+\.|Note\s\d+|[A-Za-z\s]+Statement.*|.*Budgetary.*)(.*)', first_line, re.IGNORECASE)
        
        if header_match:
            # 1. FLUSH FIRST: Save the old text under the OLD section name
            if current_chunk.strip():
                chunks.append(f"SECTION: {current_section}\n{current_chunk}")
            
            # Reset chunk and overlap history because we are entering a brand new section
            current_chunk = ""
            recent_paragraphs = [] 
            
            # 2. UPDATE SECOND: Now update the memory with the new header
            level = len(header_match.group(1))
            header_text = (header_match.group(2) + header_match.group(3)).strip()
            
            header_stack[level] = header_text
            keys_to_remove = [k for k in header_stack.keys() if k > level]
            for k in keys_to_remove:
                del header_stack[k]
                
            current_section = " > ".join([header_stack[k] for k in sorted(header_stack.keys())])
            continue
            
        # Skip the overarching "Part I" intro of the circular
        is_part_one = re.match(r'^I\.\d+', first_line) 
        if is_part_one:
            continue

        # Detect if we are in the middle of a list or a Markdown table
        is_list_item = re.match(r'^\s*([a-zA-Z]\.|[ivxIVX]+\.|\d+\.|\*|\-)\s', first_line)
        is_table_row = first_line.startswith('|')

        # Safe Chunking Logic
        if len(current_chunk) + len(p) < max_chars:
            current_chunk += p + "\n\n"
            recent_paragraphs.append(p)
        else:
            # THE OVERRIDE: Do not split if we are in a list or table!
            if (is_list_item or is_table_row) and current_chunk.strip():
                current_chunk += p + "\n\n"
                recent_paragraphs.append(p)
                continue
            
            # Seal the chunk and start a new one
            if current_chunk.strip():
                chunks.append(f"SECTION: {current_section}\n{current_chunk}")
            
            # --- THE OVERLAP INJECTION ---
            # Grab the last paragraph from the sealed chunk to prepend to the new chunk
            overlap_text = ""
            if overlap_paragraphs > 0 and recent_paragraphs:
                overlap_amount = min(overlap_paragraphs, len(recent_paragraphs))
                overlap_text = "\n\n".join(recent_paragraphs[-overlap_amount:]) + "\n\n"
            
            # Start the new chunk with the overlap + the current paragraph
            current_chunk = overlap_text + p + "\n\n"
            recent_paragraphs = [p] # Reset the tracker for the new chunk

    # Catch the final chunk
    if current_chunk.strip():
        chunks.append(f"SECTION: {current_section}\n{current_chunk}")

    return chunks

def run_triage_agent(chunk_text, toc_text):
    """Sends the text chunk to Agent 1 and returns the JSON decision."""
    system_prompt = get_triage_prompt(toc_text)
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini", # Fast, cheap model for triage
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Analyze this chunk:\n\n{chunk_text}"}
            ],
            response_format={"type": "json_object"},
            temperature=0.0
        )
        return json.loads(response.choices[0].message.content)
        
    except Exception as e:
        print(f"[!] Agent 1 Error: {e}")
        return {"contains_rule": False, "toc_section": None, "triage_reasoning": f"API Error: {e}"}

def save_triage_log(chunk_text, triage_data, log_file):
    """Writes the triage decision to a CSV."""
    file_exists = os.path.isfile(log_file)
    
    with open(log_file, mode='a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["Contains Rule", "TOC Section", "Reasoning", "Original Text Chunk"])
            
        writer.writerow([
            triage_data.get("contains_rule"),
            triage_data.get("toc_section"),
            triage_data.get("triage_reasoning"),
            chunk_text.strip()
        ])

def get_resume_index(log_file_path):
    """Reads the CSV log to determine how many chunks have already been processed."""
    if not os.path.exists(log_file_path):
        return 0
    
    try:
        with open(log_file_path, 'r', encoding='utf-8') as f:
            # Count the total number of lines in the CSV and subtract 1 for the header
            row_count = sum(1 for line in f)
        return max(0, row_count - 1)
    except Exception as e:
        print(f"Error reading log file for resume checkpoint: {e}")
        return 0

def run_triage_pipeline(md_file_path, toc_file_path, log_file_path):
    """Loads the document, chunks it, and runs Agent 1 across all chunks with resume capability."""
    print("Loading and chunking document...")
    markdown_text = load_markdown(md_file_path)
    toc_text = load_markdown(toc_file_path)
    
    chunks = smart_chunking(markdown_text)
    print(f"Document split into {len(chunks)} smart chunks.")
    
    # --- CHECKPOINT LOGIC ---
    start_index = get_resume_index(log_file_path)
    
    if start_index > 0:
        if start_index >= len(chunks):
            print("The log file indicates all chunks have already been processed!")
            return
        print(f"Found existing log. Resuming from chunk {start_index + 1} of {len(chunks)}...")
    else:
        print("Starting fresh Triage run...")

    # Start the loop from the resume point
    for i in range(start_index, len(chunks)):
        chunk = chunks[i]
        print(f"Agent 1 processing chunk {i+1} of {len(chunks)}...")
        
        decision = run_triage_agent(chunk, toc_text)
        save_triage_log(chunk, decision, log_file_path)

    print(f"\nTriage phase complete! Please review {os.path.basename(log_file_path)}.")

if __name__ == "__main__":
    # Bulletproof file paths mapping to your current setup
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
    MD_FILE = os.path.join(SCRIPT_DIR, "OMB_A136_FY25_Raw.md")
    TOC_FILE = os.path.join(SCRIPT_DIR, "OMB_TOC.txt")
    LOG_FILE = os.path.join(SCRIPT_DIR, "triage_log.csv")
    
    run_triage_pipeline(MD_FILE, TOC_FILE, LOG_FILE)