import os
import json
import re
import string
import difflib
import pandas as pd
from openai import OpenAI
from dotenv import load_dotenv
from private_prompts_multi import get_formatter_prompt

load_dotenv()

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

def run_formatter_agent(rule_data):
    """Sends the raw extracted rule to Agent 3 for CPA formatting."""
    toc_section = rule_data.get("toc_section", "Unknown Section")
    is_boilerplate = rule_data.get("is_boilerplate", False)
    raw_text = rule_data.get("raw_requirement_text", "")
    table_markdown = rule_data.get("illustrative_table_markdown", None)

    system_prompt = get_formatter_prompt(toc_section, is_boilerplate)
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Format this requirement:\n\n{raw_text}"}
            ],
            response_format={"type": "json_object"},
            temperature=0.0
        )
        
        formatted_json = json.loads(response.choices[0].message.content)
        
        # Inject the table markdown securely
        formatted_json["Illustrative_Table"] = table_markdown
        formatted_json["Illustrative_Figure_Path"] = None
        
        if "Granular_Sub_Questions" in formatted_json:
            for sub in formatted_json["Granular_Sub_Questions"]:
                sub["Illustrative_Table"] = None
                sub["Illustrative_Figure_Path"] = None

        return formatted_json
        
    except Exception as e:
        print(f"[!] Agent 3 Error: {e}")
        return None

def get_resume_index(log_file_path):
    if not os.path.exists(log_file_path):
        return 0
    with open(log_file_path, 'r', encoding='utf-8') as f:
        return sum(1 for line in f)

def get_toc_sort_key(toc_str):
    """
    Custom sorting logic to handle OMB TOC hierarchy correctly.
    Ensures 'II.3.8.10' comes AFTER 'II.3.8.9'.
    """
    if not isinstance(toc_str, str) or not toc_str: 
        return (99, tuple(), "")
    
    # Extract the Roman numeral prefix
    roman_map = {'I': 1, 'II': 2, 'III': 3, 'IV': 4, 'V': 5, 'VI': 6}
    roman_match = re.match(r'^([IVX]+)\.', toc_str)
    roman_val = roman_map.get(roman_match.group(1), 99) if roman_match else 99
    
    # Extract all the subsequent numbers and wrap them in a tuple!
    nums = tuple(int(n) for n in re.findall(r'\.(\d+)', toc_str.split(':')[0]))
    
    # By grouping 'nums' into a single tuple element, we prevent type-comparison crashes
    return (roman_val, nums, toc_str)

def get_sub_letter(idx):
    """Generates a, b, c... for sub-questions safely."""
    alphabet = string.ascii_lowercase
    if idx < 26:
        return alphabet[idx]
    else:
        return alphabet[(idx // 26) - 1] + alphabet[idx % 26]

def generate_final_exports(jsonl_filepath, final_json_path, final_csv_path):
    """Converts the JSONL tracker into the perfectly formatted Excel Checklist."""
    print("\n[Post-Processing] Generating UX-Optimized deliverables...")
    master_checklist = []
    
    with open(jsonl_filepath, 'r', encoding='utf-8') as f:
        for line in f:
            if not line.strip(): continue
            data = json.loads(line)
            formatted_rule = data.get("formatted_rule")
            if formatted_rule:
                master_checklist.append(formatted_rule)

    # 1. Save the Master JSON (Untouched, for software ingestion)
    with open(final_json_path, 'w', encoding='utf-8') as f:
        json.dump({"Checklist": master_checklist}, f, indent=4)

    # 2. Sort the Master Checklist by Official TOC Order
    master_checklist.sort(key=lambda x: get_toc_sort_key(x.get("Section", "")))

    # 3. Build the UX-Optimized CSV
    csv_rows = []
    main_counter = 1

    for item in master_checklist:
        main_q = item.get("Main_Requirement_Question", {}).get("Audit_Question", "")
        orig_text = item.get("Original_Requirement_Text", "")
        table = item.get("Illustrative_Table", "")
        subs = item.get("Granular_Sub_Questions", [])
        
        # Add the Main Question Row
        csv_rows.append({
            "TOC Section": item.get("Section", ""),
            "Category": item.get("Category", ""),
            "Original Requirement Text": orig_text,
            "Audit Question": f"{main_counter}. {main_q}",
            "Illustrative Table": table if table else ""
        })
        
        # Add the Sub-Question Rows
        if subs:
            for sub_idx, sub in enumerate(subs):
                letter = get_sub_letter(sub_idx)
                sub_q = sub.get("Audit_Question", "")
                sub_orig = sub.get("Original_Requirement_Text", "")
                
                csv_rows.append({
                    "TOC Section": item.get("Section", ""), # Repeated for easy filtering
                    "Category": "", # Blank to show hierarchy
                    "Original Requirement Text": sub_orig, 
                    "Audit Question": f"    {letter}. {sub_q}", # 4-space indent
                    "Illustrative Table": "" 
                })
        
        main_counter += 1 # Increment only for the next Main Question

    df = pd.DataFrame(csv_rows)
    df.to_csv(final_csv_path, index=False, encoding='utf-8-sig')
    print(f"-> Saved UX-Optimized Review CSV to: {os.path.basename(final_csv_path)}")

def run_formatter_pipeline(extraction_jsonl_path, formatter_jsonl_path, final_json_path, final_csv_path):
    print(f"Loading Extracted Rules from: {extraction_jsonl_path}")
    
    raw_rules_to_process = []
    seen_texts = [] # <-- Changed from a set to a list
    
    with open(extraction_jsonl_path, 'r', encoding='utf-8') as f:
        for line in f:
            if not line.strip(): continue
            data = json.loads(line)
            rules_array = data.get("extracted_data", {}).get("extracted_rules", [])
            
            for rule in rules_array:
                raw_text = rule.get("raw_requirement_text", "").strip()
                if not raw_text:
                    continue
                
                # THE "SMART BOUNCER" (FUZZY MATCHING)
                is_duplicate = False
                for seen in seen_texts:
                    # Calculate similarity ratio. If it's over 90% identical, it's a duplicate.
                    similarity = difflib.SequenceMatcher(None, raw_text, seen).ratio()
                    if similarity > 0.90:
                        is_duplicate = True
                        break
                
                if not is_duplicate:
                    seen_texts.append(raw_text)
                    raw_rules_to_process.append(rule)
                else:
                    # Silently block the fuzzy duplicate
                    pass
                
    total_rules = len(raw_rules_to_process)
    print(f"Agent 2 provided {total_rules} distinct, fuzzy-deduplicated rules for formatting.")

    start_index = get_resume_index(formatter_jsonl_path)

    if start_index >= total_rules:
        print("All rules have already been formatted!")
        # Rerun the export function to apply the new formatting to your existing data immediately
        generate_final_exports(formatter_jsonl_path, final_json_path, final_csv_path)
        return
    elif start_index > 0:
        print(f"Resuming safely at rule {start_index + 1} of {total_rules}...")

    with open(formatter_jsonl_path, 'a', encoding='utf-8') as outfile:
        for i in range(start_index, total_rules):
            rule = raw_rules_to_process[i]
            print(f"Agent 3 formatting rule {i+1} of {total_rules}...")
            
            formatted_data = run_formatter_agent(rule)
            
            if formatted_data:
                log_entry = {
                    "rule_index": i,
                    "raw_input": rule,
                    "formatted_rule": formatted_data
                }
                outfile.write(json.dumps(log_entry) + "\n")
                outfile.flush()

    generate_final_exports(formatter_jsonl_path, final_json_path, final_csv_path)

if __name__ == "__main__":
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
    EXTRACTION_JSONL = os.path.join(SCRIPT_DIR, "extraction_log.jsonl")
    FORMATTER_JSONL = os.path.join(SCRIPT_DIR, "formatter_log.jsonl")
    FINAL_JSON = os.path.join(SCRIPT_DIR, "omb_a136_checklist.json")
    FINAL_CSV = os.path.join(SCRIPT_DIR, "omb_a136_checklist.csv")
    
    run_formatter_pipeline(EXTRACTION_JSONL, FORMATTER_JSONL, FINAL_JSON, FINAL_CSV)