import os
import json
import re
import csv
import time
from openai import OpenAI
from dotenv import load_dotenv
from private_prompts import get_omb_prompt

load_dotenv()
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

INPUT_MARKDOWN_FILE = "OMB_A136_FY25_Raw.md" # OMB A-136 MD format
OUTPUT_JSON_FILE = "OMB_A136_Checklist_FY25.json"
OUTPUT_CSV_FILE = "OMB_A136_Checklist_FY25.csv"
CHECKPOINT_FILE = "omb_checkpoint.txt"
TOC_FILE = "OMB_TOC.txt" # NEW: The Table of Contents reference file

def load_toc():
    """Loads the Table of Contents to feed to the AI for Semantic Mapping."""
    if not os.path.exists(TOC_FILE):
        print(f"[!] Warning: {TOC_FILE} not found. AI will attempt to guess sections without a map.")
        return "No TOC provided."
    with open(TOC_FILE, 'r', encoding='utf-8') as f:
        return f.read().strip()

def clean_markdown_text(text):
    """
    Cleans up markdown formatting anomalies to ensure lists and colons 
    stay attached to their parent paragraphs.
    """
    text = re.sub(r':\s*\n\n', ':\n', text)
    text = re.sub(r'\n\n(?=\s*[\·\*\-])', '\n', text)
    return text

def smart_chunking(text, max_chars=3500):
    text = clean_markdown_text(text)
    
    # ROBUST SPLIT: Only split on headers that start with an OMB Roman Numeral (e.g., "## II.3.8.1")
    # This prevents sub-topics (### Budgetary Terms) from being severed from Note 1!
    raw_sections = re.split(r'\n(?=#+\s+(?:I|II|III|IV|V|VI|VII|VIII|IX|X)\.)', "\n" + text)
    
    chunks = []
    for section in raw_sections:
        if not section.strip(): continue
            
        # Get the clean header text (e.g., "II.3.2. Balance Sheet")
        first_line = section.strip().split('\n')[0].strip('# ').strip()
        lower_sec = section.lower()
        
        # --- THE TOKEN SAVER FILTER ---
        # 1. Regex to catch ALL of Part I (I.1, I.2) but SPARE lettered sub-sections like "I. Admin Expenses"
        is_part_one = re.match(r'^I\.\d+', first_line)
        
        # 2. Keyword check for non-actionable fluff and appendices
        is_fluff = any(kw in lower_sec[:200] for kw in [
            "table of contents", "executive office of the president", 
            "summary of changes", "how to use this circular", 
            "abbreviations", "appendix"
        ])
        
        if is_part_one or is_fluff:
            continue  # Silently drop the text and save your tokens!
            
        # --- THE SMART PARAGRAPH CHUNKER UPDATE ---
        paragraphs = section.split('\n\n')
        
        current_chunk = ""
        for p in paragraphs:
            is_list_item = re.match(r'^\s*([a-zA-Z]\.|[ivxIVX]+\.|\d+\.|\*|\-)\s', p.strip())
            
            # NEW: Detect if the paragraph is part of a Markdown table (starts with a pipe | )
            is_table_row = p.strip().startswith('|')
            
            if len(current_chunk) + len(p) < max_chars:
                current_chunk += p + "\n\n"
            else:
                # THE OVERRIDE: Do not split if we are in the middle of a list OR a table!
                if (is_list_item or is_table_row) and current_chunk.strip():
                    current_chunk += p + "\n\n"
                    continue
                
                if current_chunk.strip():
                    # Inject the section header at the top of the split chunk!
                    if not current_chunk.startswith(first_line):
                        final_text = f"SECTION: {first_line}\n\n{current_chunk.strip()}"
                    else:
                        final_text = current_chunk.strip()
                    chunks.append(final_text)
                    
                current_chunk = p + "\n\n"
                
        # Catch any leftover text
        if current_chunk.strip():
            if not current_chunk.startswith(first_line):
                final_text = f"SECTION: {first_line}\n\n{current_chunk.strip()}"
            else:
                final_text = current_chunk.strip()
            chunks.append(final_text)
            
    return chunks

#Location for get_system_prompt

def process_chunk(chunk_text, toc_text, retries=3):
    for attempt in range(retries):
        try:
            response = client.chat.completions.create(
                model="gpt-4o", 
                temperature=0.0,
                max_tokens=4096,
                response_format={ "type": "json_object" },
                messages=[
                    {"role": "system", "content": get_omb_prompt(toc_text)},
                    {"role": "user", "content": f"Extract the structured checklist and map it to the TOC:\n\n{chunk_text}"}
                ]
            )
            raw_output = response.choices[0].message.content
            try:
                return json.loads(raw_output).get("Checklist", [])
            except json.JSONDecodeError:
                return []
        except Exception as e:
            time.sleep(2)
            if attempt == retries - 1: return []

def scrub_omb_fluff(checklist):
    cleaned_population = []
    for item in checklist:
        main_q = item.get("Main_Requirement_Question", {}).get("Audit_Question", "").strip()
        if not main_q: continue
        cleaned_population.append(item)
    return cleaned_population

def get_excel_column_name(n):
    result = ""
    while n >= 0:
        result = chr((n % 26) + 97) + result
        n = (n // 26) - 1
    return result

def export_to_csv(checklist, output_path):
    headers = ["Section", "No.", "Original Text", "Audit Question", "Category", "Detailed Ref", "Has Table/Figure", "Table Content"]
    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        
        global_counter = 1
        for item in checklist:
            main_q = item.get("Main_Requirement_Question", {}).get("Audit_Question", "")
            if not main_q: continue
            
            table = item.get("Illustrative_Table")
            figure = item.get("Illustrative_Figure_Path")
            has_visual = "Yes" if (table and str(table).lower() != "null") or (figure and str(figure).lower() != "null") else "No"
            
            writer.writerow({
                "Section": item.get("Section", ""),
                "No.": str(global_counter),
                "Original Text": item.get("Original_Requirement_Text", ""),
                "Audit Question": main_q,
                "Category": item.get("Category", ""),
                "Detailed Ref": item.get("Detailed_Reference", ""),
                "Has Table/Figure": has_visual,
                "Table Content": item.get("Illustrative_Table", "")
            })
            
            for sub_idx, sub in enumerate(item.get("Granular_Sub_Questions", [])):
                letter = get_excel_column_name(sub_idx)
                writer.writerow({
                    "Section": item.get("Section", ""),
                    "No.": f"    {global_counter}{letter}",
                    "Original Text": sub.get("Original_Requirement_Text", item.get("Original_Requirement_Text", "")),
                    "Audit Question": f"    • {sub.get('Audit_Question', '')}",
                    "Category": item.get("Category", ""),
                    "Detailed Ref": item.get("Detailed_Reference", ""),
                    "Has Table/Figure": "N/A"
                })
            global_counter += 1

def main():
    if not os.path.exists(INPUT_MARKDOWN_FILE): 
        print(f"[!] Error: {INPUT_MARKDOWN_FILE} not found.")
        return

    with open(INPUT_MARKDOWN_FILE, 'r', encoding='utf-8') as f:
        raw_text = f.read()
        
    toc_text = load_toc()
        
    print("[*] Parsing Markdown file into Simple Chunks...")
    chunks = smart_chunking(raw_text)
    
    start_index = 0
    if os.path.exists(CHECKPOINT_FILE):
        with open(CHECKPOINT_FILE, 'r') as f:
            try: start_index = int(f.read().strip())
            except ValueError: start_index = 0
            
    master_checklist = []
    if os.path.exists(OUTPUT_JSON_FILE):
        with open(OUTPUT_JSON_FILE, 'r', encoding='utf-8') as f:
            try: master_checklist = json.load(f)
            except Exception: pass

    print(f"[*] Starting extraction at chunk {start_index} of {len(chunks)}...")
    for i in range(start_index, len(chunks)):
        print(f"  -> Processing block {i+1}/{len(chunks)}...")
        
        extracted = process_chunk(chunks[i], toc_text)
        if extracted: master_checklist.extend(extracted)
            
        temp_file = OUTPUT_JSON_FILE + ".tmp"
        with open(temp_file, 'w', encoding='utf-8') as f:
            json.dump(master_checklist, f, indent=4)
        os.replace(temp_file, OUTPUT_JSON_FILE)
        
        with open(CHECKPOINT_FILE, 'w') as f: f.write(str(i + 1))
        time.sleep(0.5)

    master_checklist = scrub_omb_fluff(master_checklist)
    with open(OUTPUT_JSON_FILE, 'w', encoding='utf-8') as f:
        json.dump(master_checklist, f, indent=4)

    export_to_csv(master_checklist, OUTPUT_CSV_FILE)
    print(f"[+] SUCCESS! Clean files generated using Semantic Routing.")

if __name__ == "__main__":
    main()