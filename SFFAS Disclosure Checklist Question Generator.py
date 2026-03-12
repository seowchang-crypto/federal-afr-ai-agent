import os
import json
import re
import csv
import time
from openai import OpenAI
from dotenv import load_dotenv
from private_prompts import get_sffas_prompt

load_dotenv()
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

INPUT_MARKDOWN_FILE = "2025_FASAB_SFFAS_Master.md" 
OUTPUT_JSON_FILE = "2025_SFFAS_Disclosure_Checklist.json"
OUTPUT_CSV_FILE = "2025_SFFAS_Disclosure_Checklist.csv"
CHECKPOINT_FILE = "sffas_checkpoint.txt"

# STANDARDS TO COMPLETELY BYPASS (CFR-Only or Irrelevant)
EXCLUDED_STANDARDS = [
    "SFFAS 32", # Consolidated Financial Report of the US Government
    "SFFAS 36", # Comprehensive Long-Term Projections for the US Government
    # You can add any others here as you find them!
]

def clean_markdown_text(text):
    text = re.sub(r'', '', text, flags=re.DOTALL)
    text = re.sub(r':\s*\n\n', ':\n', text)
    text = re.sub(r'\n\n(?=\s*[\·\*\-])', '\n', text)
    return text

def safe_semantic_chunking(text):
    """
    Slices text robustly by Markdown headers using Regex.
    Includes the fully restored Positive/Negative locks to ruthlessly filter out 
    all Concepts, Executive Summaries, and Glossaries before they hit the API.
    Includes 'Sticky Parent Tracking' to prevent Context Severing in long hierarchical lists.
    """
    import re
    
    # Clean the text to ensure consistent paragraph spacing
    text = re.sub(r':\s*\n\n', ':\n', text)
    text = re.sub(r'\n\n(?=\s*[\·\*\-])', '\n', text)
    
    # ROBUST SPLIT: Slices the document precisely at every header (#)
    raw_sections = re.split(r'\n(?=#+ )', "\n" + text)
    
    chunks = []
    active_headers = {}
    
    for section in raw_sections:
        if not section.strip():
            continue
            
        lines = section.strip().split('\n')
        first_line = lines[0].strip()
        
        if first_line.startswith('#'):
            level = len(first_line) - len(first_line.lstrip('#'))
            header_text = first_line.strip('# ').strip()
            
            # Update breadcrumb trail
            active_headers[level] = header_text
            keys_to_remove = [k for k in active_headers.keys() if k > level]
            for k in keys_to_remove: 
                del active_headers[k]
                
            current_breadcrumb = " > ".join([active_headers[k] for k in sorted(active_headers.keys())])
            
            # --- THE RESTORED AGGRESSIVE NOISE FILTER ---
            lower_crumb = current_breadcrumb.lower()
            
            # 1. Positive Lock: It MUST be a binding GAAP document type
            is_binding = any(kw in lower_crumb for kw in [
                "standard", "interpretation", "technical bulletin", "technical release", "sffas"
            ])
            
            # 2. Negative Lock: It MUST NOT be introductory or philosophical fluff
            is_fluff = any(kw in lower_crumb for kw in [
                "concept", "basis for conclusion", "appendix", "appendices", 
                "executive summary", "table of contents", 
                "summary", "status", "glossary", "materiality", "overview"
            ])
            
            # --- THE CFR EXCLUSION LOCK ---
            # We use 'current_breadcrumb' because it contains the full hierarchy path
            is_excluded = any(excluded_std in current_breadcrumb for excluded_std in EXCLUDED_STANDARDS)
        
            if is_excluded:
                # We silently 'continue' here so we don't spam your console 
                # with hundreds of print statements for every single skipped paragraph.
                continue

            # If it passes the locks, prepare it for the API
            if is_binding and not is_fluff:
                section_text = "\n".join(lines[1:]).strip() # The text under the header
                
                if len(section_text) > 0:
                    # --- THE SMART PARAGRAPH CHUNKER UPDATE ---
                    max_chars = 3500 
                    paragraphs = section_text.split('\n\n')
                    
                    current_chunk = ""
                    active_parent_paragraph = "" 
                    
                    for p in paragraphs:
                        # Track root paragraphs for context
                        if re.match(r'^\[?\d+\]?[\.\\]?\s', p.strip()):
                            active_parent_paragraph = p.strip()[:200] 
                            
                        # NEW: Detect if the current text is a sub-list item (a., i., 1., -, *)
                        is_list_item = re.match(r'^\s*([a-zA-Z]\.|[ivxIVX]+\.|\d+\.|\*|\-)\s', p.strip())
                        
                        if len(current_chunk) + len(p) < max_chars:
                            current_chunk += p + "\n\n"
                        else:
                            # THE OVERRIDE: If we hit 3500, but we are in the middle of a list, DO NOT SPLIT.
                            if is_list_item and current_chunk.strip():
                                current_chunk += p + "\n\n"
                                continue # Bypass the split to keep the list unified
                            
                            # If it's a normal paragraph, it is safe to split
                            if current_chunk.strip():
                                chunks.append(f"SECTION BREADCRUMB: {current_breadcrumb}\n\n{current_chunk.strip()}")
                            
                            current_chunk = ""
                            
                            # Inject sticky parent context for the new chunk
                            if active_parent_paragraph and not p.strip().startswith(active_parent_paragraph[:50]):
                                current_chunk += f"[PARENT PARAGRAPH CONTEXT - DO NOT GENERATE QUESTIONS FOR THIS]: {active_parent_paragraph}...\n\n"
                            
                            current_chunk += p + "\n\n"
                            
                            # --- CRITICAL FIX: STICKY PARENT INJECTION ---
                            # Inject the parent context so the AI doesn't lose the hierarchy!
                            if active_parent_paragraph and not p.strip().startswith(active_parent_paragraph[:50]):
                                current_chunk += f"[PARENT PARAGRAPH CONTEXT - DO NOT GENERATE QUESTIONS FOR THIS]: {active_parent_paragraph}...\n\n"
                            
                            current_chunk += p + "\n\n"
                            
                    # Catch any leftover text
                    if current_chunk.strip():
                        chunks.append(f"SECTION BREADCRUMB: {current_breadcrumb}\n\n{current_chunk.strip()}")

    return chunks

#Location for get_system_prompt

def process_chunk(chunk_text, retries=3):
    for attempt in range(retries):
        try:
            response = client.chat.completions.create(
                model="gpt-4o",  # Restored Senior Model for strict rule adherence
                temperature=0.0,
                max_tokens=4096,
                response_format={ "type": "json_object" },
                messages=[
                    {"role": "system", "content": get_sffas_prompt()},
                    {"role": "user", "content": f"Extract the structured checklist:\n\n{chunk_text}"}
                ]
            )
            raw_output = response.choices[0].message.content
            
            try:
                return json.loads(raw_output).get("Checklist", [])
            except json.JSONDecodeError:
                return []
                
        except Exception as e:
            print(f"    [!] API Error on attempt {attempt + 1}: {e}. Retrying...")
            time.sleep(2)
            if attempt == retries - 1: return []

def export_to_csv(checklist, output_path):
    headers = [
        "Section", "Type", "Original Text", "Audit Question", 
        "Category", "Guidance", "Detailed Ref", "Has Table/Figure", "Table Content",
    ]
    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        for item in checklist:
            main_q = item.get("Main_Requirement_Question", {}).get("Audit_Question", "")
            if not main_q: continue
            
            table = item.get("Illustrative_Table")
            figure = item.get("Illustrative_Figure_Path")
            has_visual = "Yes" if (table and str(table).lower() != "null") or (figure and str(figure).lower() != "null") else "No"
            
            writer.writerow({
                "Section": item.get("Section", ""),
                "Type": "Main",
                "Original Text": item.get("Original_Requirement_Text", ""),
                "Audit Question": main_q,
                "Category": item.get("Category", ""),
                "Guidance": item.get("Authoritative_Guidance", ""),
                "Detailed Ref": item.get("Detailed_Reference", ""),
                "Has Table/Figure": has_visual,
                "Table Content": item.get("Illustrative_Table", "")
            })
            for sub in item.get("Granular_Sub_Questions", []):
                writer.writerow({
                    "Section": item.get("Section", ""),
                    "Type": "Sub",
                    "Original Text": sub.get("Original_Requirement_Text", item.get("Original_Requirement_Text", "")),
                    "Audit Question": sub.get("Audit_Question", ""),
                    "Category": item.get("Category", ""),
                    "Guidance": item.get("Authoritative_Guidance", ""),
                    "Detailed Ref": item.get("Detailed_Reference", ""),
                    "Has Table/Figure": "N/A"
                })

def main():
    if not os.path.exists(INPUT_MARKDOWN_FILE):
        print(f"[!] File {INPUT_MARKDOWN_FILE} not found.")
        return

    with open(INPUT_MARKDOWN_FILE, 'r', encoding='utf-8') as f:
        raw_text = f.read()
        
    print("[*] Parsing Markdown file into Safe Semantic Sections...")
    chunks = safe_semantic_chunking(raw_text)
    print(f"[*] Total valid sections to process after filtering noise: {len(chunks)}")
    
    start_index = 0
    if os.path.exists(CHECKPOINT_FILE):
        with open(CHECKPOINT_FILE, 'r') as f:
            try: start_index = int(f.read().strip())
            except ValueError: start_index = 0
            
    master_checklist = []
    if os.path.exists(OUTPUT_JSON_FILE):
        with open(OUTPUT_JSON_FILE, 'r', encoding='utf-8') as f:
            try: master_checklist = json.load(f)
            except Exception as e: print(f"[!] Warning: Starting fresh JSON. ({e})")

    print(f"[*] Starting extraction at chunk {start_index} of {len(chunks)}...")
    
    for i in range(start_index, len(chunks)):
        print(f"  -> Processing block {i+1}/{len(chunks)}")
        extracted = process_chunk(chunks[i])
        
        if extracted:
            master_checklist.extend(extracted)
            
        temp_file = OUTPUT_JSON_FILE + ".tmp"
        with open(temp_file, 'w', encoding='utf-8') as f:
            json.dump(master_checklist, f, indent=4)
        os.replace(temp_file, OUTPUT_JSON_FILE)
        
        with open(CHECKPOINT_FILE, 'w') as f:
            f.write(str(i + 1))
            
        time.sleep(1.5) 

    print(f"\n[*] Generating flat CSV for manual review...")
    export_to_csv(master_checklist, OUTPUT_CSV_FILE)
    print(f"[+] SUCCESS! {OUTPUT_JSON_FILE} and {OUTPUT_CSV_FILE} generated securely.")

if __name__ == "__main__":
    main()